import io
from urllib.parse import urlparse

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from inventory.models import Category, MenuItem
from restaurant.models import DiningTable, RestaurantAccount, Zone
from restaurant.services import release_expired_tables
from restaurant.tenancy import scoped_queryset
from sales.models import Order

OPEN_ORDER_STATUSES = [
    Order.Status.OPEN, Order.Status.SENT, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED,
]


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
def tables(request):
    tables_qs = scoped_queryset(DiningTable.objects.all(), request.user, 'zone__branch__restaurant')
    release_expired_tables(tables_qs)
    zones = scoped_queryset(Zone.objects.all(), request.user, 'branch__restaurant')
    open_orders = scoped_queryset(
        Order.objects.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED]),
        request.user,
    ).select_related('table')

    orders_by_table = {order.table_id: order for order in open_orders}
    for table in tables_qs:
        table.open_order = orders_by_table.get(table.id)

    return render(request, 'restaurant/tables.html', {
        'zones': zones.prefetch_related('tables'),
        'tables': tables_qs.select_related('zone'),
    })


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
@require_POST
def table_release(request, pk):
    """El personal marca una mesa pendiente o en limpieza como disponible."""
    table = get_object_or_404(
        scoped_queryset(DiningTable.objects.all(), request.user, 'zone__branch__restaurant'), pk=pk,
    )
    if table.orders.filter(status__in=OPEN_ORDER_STATUSES).exists():
        return render(request, 'error.html', {'message': 'La mesa tiene un pedido abierto; cóbralo o cancélalo primero.'}, status=400)
    table.status = DiningTable.Status.AVAILABLE
    table.save(update_fields=['status'])
    return redirect('tables')


def _public_base_url(request):
    return settings.PUBLIC_BASE_URL or request.build_absolute_uri('/').rstrip('/')


def _table_public_url(request, table):
    return _public_base_url(request) + reverse('public_menu', args=[table.qr_token])


@login_required
@role_required('admin', 'manager')
def tables_qr(request):
    """Página imprimible con el código QR de cada mesa."""
    tables_qs = scoped_queryset(
        DiningTable.objects.filter(is_active=True).select_related('zone'), request.user, 'zone__branch__restaurant',
    )
    base = _public_base_url(request)
    host = urlparse(base).hostname or ''
    rows = [{'table': t, 'url': _table_public_url(request, t)} for t in tables_qs]
    return render(request, 'restaurant/tables_qr.html', {
        'rows': rows,
        'base_url': base,
        'is_local_address': host in ('127.0.0.1', 'localhost', '0.0.0.0'),
    })


@login_required
@role_required('admin', 'manager')
def table_qr_svg(request, pk):
    table = get_object_or_404(
        scoped_queryset(DiningTable.objects.all(), request.user, 'zone__branch__restaurant'), pk=pk,
    )
    image = qrcode.make(_table_public_url(request, table), image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return HttpResponse(buffer.getvalue(), content_type='image/svg+xml')


@never_cache
@ensure_csrf_cookie
def public_menu(request, token):
    """Carta pública que ve el cliente al escanear el QR de su mesa (sin iniciar sesión)."""
    table = get_object_or_404(
        DiningTable.objects.select_related('zone__branch__restaurant'), qr_token=token, is_active=True,
    )
    branch = table.zone.branch
    restaurant = branch.restaurant if branch else None
    if restaurant is None or restaurant.status in (RestaurantAccount.Status.SUSPENDED, RestaurantAccount.Status.CANCELLED):
        return render(request, 'public/unavailable.html', status=404)

    release_expired_tables(DiningTable.objects.filter(pk=table.pk))
    table.refresh_from_db()
    if table.status == DiningTable.Status.AVAILABLE:
        # Alguien llegó a la mesa: queda "pendiente" hasta que pidan (o venza el tiempo).
        table.status = DiningTable.Status.PENDING
        table.save(update_fields=['status'])

    categories = [
        category for category in Category.objects.filter(restaurant=restaurant, is_active=True).prefetch_related(
            Prefetch('items', queryset=MenuItem.objects.filter(is_available=True).order_by('name'), to_attr='available_items'),
        )
        if category.available_items
    ]
    return render(request, 'public/menu.html', {
        'restaurant': restaurant,
        'branch': branch,
        'table': table,
        'categories': categories,
        'has_tax': any(item.tax_rate > 0 for category in categories for item in category.available_items),
    })
