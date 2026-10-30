"""Endpoints públicos (sin login) que usa la carta QR del cliente.

La seguridad se apoya en tres cosas: el código de la mesa es largo y aleatorio, cada pedido
queda "por confirmar" hasta que un mesero lo aprueba, y todo está acotado a una mesa y a su restaurante.
"""
import json

from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from inventory.models import MenuItem
from restaurant.models import DiningTable, RestaurantAccount, TableRequest
from restaurant.services import release_expired_tables
from sales.models import CustomerOrder, CustomerOrderItem, Order
from sales.services import expire_old_customer_orders, stock_shortages

MAX_LINES = 25
MAX_QUANTITY = 20

ORDER_STATUS_FOR_CUSTOMER = {
    Order.Status.OPEN: 'Tu pedido está en cocina',
    Order.Status.SENT: 'Tu pedido está en cocina',
    Order.Status.PREPARING: 'Estamos preparando tu pedido',
    Order.Status.READY: 'Tu pedido está listo y va para tu mesa',
    Order.Status.SERVED: 'Tu pedido fue servido. ¡Buen provecho!',
    Order.Status.PAID: 'Pedido pagado. ¡Gracias por tu visita!',
    Order.Status.CANCELLED: 'Tu pedido fue cancelado',
}


def public_table(token):
    table = get_object_or_404(DiningTable.objects.select_related('zone__branch__restaurant'), qr_token=token, is_active=True)
    branch = table.zone.branch
    restaurant = branch.restaurant if branch else None
    if restaurant is None or restaurant.status in (RestaurantAccount.Status.SUSPENDED, RestaurantAccount.Status.CANCELLED):
        raise Http404
    return table, restaurant


def touch_table(table):
    """El cliente está activo en la mesa: queda pendiente y se renueva su tiempo de espera."""
    table.refresh_from_db()
    if table.status == DiningTable.Status.AVAILABLE:
        table.status = DiningTable.Status.PENDING
        table.save(update_fields=['status'])
    elif table.status == DiningTable.Status.PENDING:
        DiningTable.objects.filter(pk=table.pk).update(status_changed_at=timezone.now())


def bad_request(message, status=400):
    return JsonResponse({'ok': False, 'error': message}, status=status)


def customer_order_state(customer_order):
    status = customer_order.status
    if status == CustomerOrder.Status.PENDING:
        label, final = 'Esperando que el mesero confirme tu pedido', False
    elif status == CustomerOrder.Status.REJECTED:
        reason = f': {customer_order.reject_reason}' if customer_order.reject_reason else ''
        label, final = f'El mesero no pudo confirmar tu pedido{reason}', True
    elif status == CustomerOrder.Status.EXPIRED:
        label, final = 'Tu pedido venció sin confirmación. Llama al mesero.', True
    else:
        order = customer_order.order
        label = ORDER_STATUS_FOR_CUSTOMER.get(order.status, 'Pedido confirmado') if order else 'Pedido confirmado'
        final = bool(order and order.status in (Order.Status.PAID, Order.Status.CANCELLED))
    return {'id': customer_order.id, 'status': status, 'label': label, 'final': final}


@require_POST
def public_order_create(request, token):
    table, restaurant = public_table(token)
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return bad_request('Solicitud inválida.')
    if not isinstance(data, dict):
        return bad_request('Solicitud inválida.')

    raw_items = data.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        return bad_request('Agrega al menos un producto.')
    if len(raw_items) > MAX_LINES:
        return bad_request('El pedido tiene demasiados productos. Llama al mesero.')

    merged = {}
    for row in raw_items:
        if not isinstance(row, dict):
            return bad_request('Solicitud inválida.')
        try:
            item_id, quantity = int(row.get('menu_item')), int(row.get('quantity'))
        except (TypeError, ValueError):
            return bad_request('Solicitud inválida.')
        if quantity < 1:
            return bad_request('La cantidad debe ser al menos 1.')
        entry = merged.setdefault(item_id, {'quantity': 0, 'notes': ''})
        entry['quantity'] += quantity
        entry['notes'] = entry['notes'] or str(row.get('notes') or '')[:255]
        if entry['quantity'] > MAX_QUANTITY:
            return bad_request(f'Máximo {MAX_QUANTITY} unidades por producto. Llama al mesero para pedidos grandes.')

    expire_old_customer_orders(CustomerOrder.objects.filter(table=table))
    if CustomerOrder.objects.filter(table=table, status=CustomerOrder.Status.PENDING).exists():
        return bad_request('Ya hay un pedido esperando confirmación en esta mesa.', status=409)

    menu_items = {m.pk: m for m in MenuItem.objects.filter(restaurant=restaurant, pk__in=merged.keys(), is_available=True)}
    if len(menu_items) != len(merged):
        return bad_request('Algunos productos ya no están disponibles. Actualiza la carta.')
    if stock_shortages([(menu_items[i], entry['quantity']) for i, entry in merged.items()]):
        return bad_request('Algunos productos se agotaron en este momento. Llama al mesero.')

    with transaction.atomic():
        customer_order = CustomerOrder.objects.create(
            restaurant=restaurant, table=table, note=str(data.get('note') or '')[:255],
        )
        CustomerOrderItem.objects.bulk_create([
            CustomerOrderItem(customer_order=customer_order, menu_item=menu_items[i], quantity=e['quantity'], notes=e['notes'])
            for i, e in merged.items()
        ])
    touch_table(table)
    return JsonResponse({'ok': True, **customer_order_state(customer_order)}, status=201)


@require_POST
def public_request(request, token):
    table, _ = public_table(token)
    try:
        data = json.loads(request.body or b'{}')
        kind = data.get('kind') if isinstance(data, dict) else None
    except ValueError:
        kind = None
    if kind not in TableRequest.Kind.values:
        return bad_request('Solicitud inválida.')

    already = TableRequest.objects.filter(table=table, kind=kind, attended_at__isnull=True).exists()
    if not already:
        TableRequest.objects.create(table=table, kind=kind)
    touch_table(table)
    return JsonResponse({'ok': True, 'already': already})


@never_cache
@require_GET
def public_status(request, token):
    table, _ = public_table(token)
    release_expired_tables(DiningTable.objects.filter(pk=table.pk))
    expire_old_customer_orders(CustomerOrder.objects.filter(table=table))
    table.refresh_from_db()

    order_info = None
    order_id = request.GET.get('order', '')
    if order_id.isdigit():
        customer_order = CustomerOrder.objects.select_related('order').filter(pk=int(order_id), table=table).first()
        if customer_order:
            order_info = customer_order_state(customer_order)

    open_kinds = set(TableRequest.objects.filter(table=table, attended_at__isnull=True).values_list('kind', flat=True))
    return JsonResponse({
        'table_status': table.status,
        'order': order_info,
        'requests': {kind: kind in open_kinds for kind in TableRequest.Kind.values},
    })
