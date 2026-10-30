from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsAdminOrManager, IsOrderStaff, IsPOSStaff
from kitchen.models import KitchenTicket
from restaurant.models import DiningTable
from restaurant.tenancy import same_tenant, scoped_queryset
from sales.models import Order, OrderItem, Payment
from sales.services import consume_order_inventory, stock_shortages

OPEN_STATUSES = [
    Order.Status.OPEN, Order.Status.SENT, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED,
]
CHEF_ALLOWED_STATUSES = {Order.Status.PREPARING, Order.Status.READY}
KITCHEN_STATUS_MAP = {
    Order.Status.SENT: KitchenTicket.Status.PENDING,
    Order.Status.PREPARING: KitchenTicket.Status.PREPARING,
    Order.Status.READY: KitchenTicket.Status.READY,
    Order.Status.SERVED: KitchenTicket.Status.DELIVERED,
}


def table_restaurant_id(table):
    branch = getattr(table.zone, 'branch', None)
    return getattr(branch, 'restaurant_id', None)


def release_table_if_free(table, excluding_order=None):
    """Libera la mesa si ya no le quedan pedidos abiertos."""
    others = table.orders.filter(status__in=OPEN_STATUSES)
    if excluding_order is not None:
        others = others.exclude(pk=excluding_order.pk)
    if not others.exists():
        table.status = DiningTable.Status.AVAILABLE
        table.save(update_fields=['status'])


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item', 'menu_item_name', 'quantity', 'unit_price', 'tax_rate', 'notes', 'sent_to_kitchen']
        read_only_fields = ['unit_price', 'tax_rate', 'sent_to_kitchen']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError('La cantidad debe ser al menos 1.')
        return value

    def validate(self, attrs):
        menu_item = attrs.get('menu_item') or getattr(self.instance, 'menu_item', None)
        if menu_item is not None and not menu_item.is_available:
            raise serializers.ValidationError('El producto no está disponible.')
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, allow_empty=False)
    table_number = serializers.CharField(source='table.number', read_only=True)
    waiter_name = serializers.CharField(source='waiter.get_full_name', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'table', 'table_number', 'waiter', 'waiter_name', 'status', 'subtotal', 'tax', 'discount', 'total', 'notes', 'created_at', 'closed_at', 'items']
        read_only_fields = ['waiter', 'subtotal', 'tax', 'total', 'created_at', 'closed_at']

    @property
    def _user(self):
        return self.context['request'].user

    def validate_table(self, value):
        if not value.is_active:
            raise serializers.ValidationError('La mesa seleccionada no está disponible.')
        if not same_tenant(self._user, table_restaurant_id(value)):
            raise serializers.ValidationError('La mesa seleccionada no existe.')
        return value

    def validate_discount(self, value):
        if value < 0:
            raise serializers.ValidationError('El descuento no puede ser negativo.')
        return value

    def validate_status(self, value):
        user = self._user
        if value == Order.Status.PAID:
            raise serializers.ValidationError('Un pedido solo pasa a pagado registrando su pago.')
        if not user.is_superuser and user.role == 'chef' and value not in CHEF_ALLOWED_STATUSES:
            raise serializers.ValidationError('Cocina solo puede marcar pedidos como preparando o listos.')
        return value

    def validate(self, attrs):
        user = self._user

        # Cocina solo puede tocar el estado del pedido.
        if self.instance is not None and not user.is_superuser and user.role == 'chef':
            extra = set(self.initial_data.keys()) - {'status'}
            if extra:
                raise serializers.ValidationError('Cocina solo puede cambiar el estado del pedido.')

        # Un pedido cerrado no se modifica.
        if self.instance is not None and self.instance.status in (Order.Status.PAID, Order.Status.CANCELLED):
            raise serializers.ValidationError('El pedido ya está cerrado y no se puede modificar.')

        items = attrs.get('items', [])
        rows = []
        for row in items:
            menu_item = row.get('menu_item')
            if not menu_item:
                continue
            if not same_tenant(user, menu_item.restaurant_id):
                raise serializers.ValidationError({'items': ['Hay productos que no existen en tu restaurante.']})
            rows.append((menu_item, row.get('quantity', 0)))

        shortages = stock_shortages(rows)
        if shortages:
            raise serializers.ValidationError({'items': shortages})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        user = self._user
        table = validated_data.get('table')
        order = Order.objects.create(
            waiter=user,
            restaurant=getattr(user, 'restaurant', None) or getattr(getattr(table.zone, 'branch', None), 'restaurant', None),
            branch=getattr(table.zone, 'branch', None),
            **validated_data,
        )
        for row in items_data:
            menu_item = row['menu_item']
            row.pop('unit_price', None)
            row.pop('tax_rate', None)
            OrderItem.objects.create(order=order, unit_price=menu_item.price, tax_rate=menu_item.tax_rate, **row)
        order.table.status = DiningTable.Status.OCCUPIED
        order.table.save(update_fields=['status'])
        order.recalculate()
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        new_table = validated_data.pop('table', None)
        old_table = instance.table
        old_status = instance.status

        if new_table and new_table != old_table:
            new_table.status = DiningTable.Status.OCCUPIED
            new_table.save(update_fields=['status'])
            release_table_if_free(old_table, excluding_order=instance)
            instance.table = new_table

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        new_status = instance.status
        if new_status != old_status:
            if new_status in KITCHEN_STATUS_MAP:
                KitchenTicket.objects.filter(order=instance).update(status=KITCHEN_STATUS_MAP[new_status])
            if new_status == Order.Status.PREPARING:
                consume_order_inventory(instance)
            if new_status == Order.Status.CANCELLED:
                release_table_if_free(instance.table, excluding_order=instance)

        if items_data is not None:
            instance.items.all().delete()
            for row in items_data:
                menu_item = row['menu_item']
                row.pop('unit_price', None)
                row.pop('tax_rate', None)
                OrderItem.objects.create(order=instance, unit_price=menu_item.price, tax_rate=menu_item.tax_rate, **row)
        instance.recalculate()
        return instance


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['cashier', 'change', 'created_at', 'restaurant', 'branch']

    def validate(self, attrs):
        user = self.context['request'].user
        order = attrs['order']
        if not same_tenant(user, order.restaurant_id):
            raise serializers.ValidationError({'order': 'El pedido no existe.'})
        if hasattr(order, 'payment'):
            raise serializers.ValidationError('Este pedido ya tiene un pago registrado.')
        if order.status == Order.Status.CANCELLED:
            raise serializers.ValidationError('No se puede cobrar un pedido cancelado.')
        if order.status == Order.Status.PAID:
            raise serializers.ValidationError('Este pedido ya está pagado.')
        if attrs['amount'] <= 0:
            raise serializers.ValidationError('El valor a pagar debe ser mayor que cero.')
        if attrs['amount'] != order.total:
            raise serializers.ValidationError({'amount': f'El valor a pagar debe ser igual al total del pedido ({order.total}).'})
        method = attrs.get('method')
        received = attrs.get('received') or Decimal('0')
        if method == Payment.Method.CASH and received < attrs['amount']:
            raise serializers.ValidationError({'received': 'El efectivo recibido no cubre el total del pedido.'})
        if method in (Payment.Method.CARD, Payment.Method.TRANSFER) and received < attrs['amount']:
            attrs['received'] = attrs['amount']
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        payment = Payment.objects.create(cashier=self.context['request'].user, **validated_data)
        order = payment.order
        order.status = Order.Status.PAID
        order.closed_at = timezone.now()
        order.save(update_fields=['status', 'closed_at'])
        KitchenTicket.objects.filter(order=order).update(status=KitchenTicket.Status.DELIVERED)
        # La mesa pasa a limpieza solo si ya no le quedan pedidos abiertos (puede haber más de uno).
        if not order.table.orders.filter(status__in=OPEN_STATUSES).exists():
            order.table.status = DiningTable.Status.CLEANING
            order.table.save(update_fields=['status'])
        return payment


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related('table', 'waiter').prefetch_related('items__menu_item')
    serializer_class = OrderSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'partial_update'):
            return [IsOrderStaff()]  # cocina necesita ver y avanzar pedidos
        if self.action == 'destroy':
            return [IsAdminOrManager()]
        return [IsPOSStaff()]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user)

    @action(detail=True, methods=['post'])
    def send_to_kitchen(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.OPEN:
            return Response({'detail': 'Solo se pueden enviar a cocina pedidos abiertos.'}, status=400)
        if not order.items.exists():
            return Response({'detail': 'El pedido no tiene productos.'}, status=400)
        order.status = Order.Status.SENT
        order.save(update_fields=['status'])
        order.items.update(sent_to_kitchen=True)
        KitchenTicket.objects.get_or_create(order=order)
        return Response({'status': order.status})


class PaymentViewSet(viewsets.ModelViewSet):
    """Los pagos son registros financieros: se crean y consultan, pero no se editan ni se borran por la API."""

    queryset = Payment.objects.select_related('order', 'cashier')
    serializer_class = PaymentSerializer
    permission_classes = [IsPOSStaff]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user)
