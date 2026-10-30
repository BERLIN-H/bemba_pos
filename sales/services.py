import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from inventory.models import StockAlert
from kitchen.models import KitchenTicket
from restaurant.models import DiningTable

logger = logging.getLogger(__name__)


def consume_order_inventory(order):
    """Descuenta el inventario del pedido (una sola vez) y genera alertas de stock bajo."""
    if not order.consume_inventory():
        return False

    for item in order.items.select_related('menu_item').prefetch_related('menu_item__recipe__ingredient'):
        for recipe_item in item.menu_item.recipe.all():
            ingredient = recipe_item.ingredient
            ingredient.refresh_from_db(fields=['current_stock'])
            if ingredient.current_stock <= ingredient.min_stock:
                # StockAlert.save() ya envía la notificación al crearse.
                StockAlert.objects.get_or_create(
                    ingredient=ingredient,
                    resolved=False,
                    defaults={
                        'restaurant': ingredient.restaurant,
                        'message': f'Stock bajo: {ingredient.current_stock} {ingredient.unit} (mínimo: {ingredient.min_stock})',
                        'created_by': order.waiter,
                    },
                )
    return True


class CustomerOrderError(Exception):
    """Un pedido del cliente no se puede confirmar (producto agotado, ya resuelto, etc.)."""


def stock_shortages(rows):
    """rows: lista de (menu_item, cantidad). Devuelve los ingredientes que no alcanzan para prepararlos."""
    required = defaultdict(lambda: Decimal('0'))
    ingredients = {}
    for menu_item, quantity in rows:
        for recipe_item in menu_item.recipe.select_related('ingredient'):
            ingredients[recipe_item.ingredient_id] = recipe_item.ingredient
            required[recipe_item.ingredient_id] += recipe_item.quantity * quantity
    return [
        f'{ingredients[i].name}: requiere {qty} {ingredients[i].unit}, disponible {ingredients[i].current_stock}'
        for i, qty in required.items()
        if ingredients[i].current_stock < qty
    ]


def expire_old_customer_orders(queryset=None):
    """Marca como vencidos los pedidos del cliente que nadie confirmó a tiempo."""
    from sales.models import CustomerOrder

    now = timezone.now()
    orders = queryset if queryset is not None else CustomerOrder.objects.all()
    return orders.filter(
        status=CustomerOrder.Status.PENDING,
        created_at__lte=now - timedelta(minutes=settings.CUSTOMER_ORDER_EXPIRY_MINUTES),
    ).update(status=CustomerOrder.Status.EXPIRED, resolved_at=now)


@transaction.atomic
def confirm_customer_order(customer_order, user):
    """El mesero confirma el pedido del cliente: se crea el pedido real y va directo a cocina."""
    from sales.models import CustomerOrder, Order, OrderItem

    locked = CustomerOrder.objects.select_for_update().get(pk=customer_order.pk)
    if locked.status != CustomerOrder.Status.PENDING:
        raise CustomerOrderError('Este pedido ya fue atendido o venció.')

    rows = []
    for item in locked.items.select_related('menu_item'):
        if not item.menu_item.is_available:
            raise CustomerOrderError(f'"{item.menu_item.name}" ya no está disponible. Rechaza el pedido o avisa al cliente.')
        rows.append((item.menu_item, item.quantity))
    shortages = stock_shortages(rows)
    if shortages:
        raise CustomerOrderError('No hay stock suficiente: ' + '; '.join(shortages))

    table = locked.table
    branch = table.zone.branch
    order = Order.objects.create(
        waiter=user,
        restaurant=locked.restaurant or getattr(branch, 'restaurant', None),
        branch=branch,
        table=table,
        status=Order.Status.SENT,
        notes=f'Pedido del cliente por QR. {locked.note}'.strip(),
    )
    for item in locked.items.select_related('menu_item'):
        OrderItem.objects.create(
            order=order, menu_item=item.menu_item, quantity=item.quantity, notes=item.notes,
            unit_price=item.menu_item.price, tax_rate=item.menu_item.tax_rate, sent_to_kitchen=True,
        )
    order.recalculate()
    KitchenTicket.objects.get_or_create(order=order)

    table.status = DiningTable.Status.OCCUPIED
    table.save(update_fields=['status'])

    locked.status = CustomerOrder.Status.CONFIRMED
    locked.order = order
    locked.resolved_by = user
    locked.resolved_at = timezone.now()
    locked.save(update_fields=['status', 'order', 'resolved_by', 'resolved_at'])
    return order
