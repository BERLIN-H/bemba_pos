from django.contrib.auth.decorators import login_required
from collections import defaultdict

from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from inventory.models import Category, MenuItem
from restaurant.models import DiningTable, TableRequest
from restaurant.services import release_expired_tables
from restaurant.tenancy import scoped_queryset
from sales.models import CustomerOrder, Order, Payment
from sales.services import CustomerOrderError, confirm_customer_order, expire_old_customer_orders


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
def pos(request):
    tables = scoped_queryset(DiningTable.objects.filter(is_active=True), request.user, 'zone__branch__restaurant')
    release_expired_tables(tables)
    categories = scoped_queryset(Category.objects.filter(is_active=True), request.user)
    items = scoped_queryset(MenuItem.objects.filter(is_available=True), request.user)
    open_orders = scoped_queryset(Order.objects.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED]), request.user)
    return render(request, 'sales/pos.html', {
        'tables': tables.select_related('zone__branch'),
        'categories': categories,
        'items': items.select_related('category'),
        'open_orders': open_orders.select_related('table', 'waiter')[:12],
    })


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
def ticket(request, pk):
    orders = scoped_queryset(Order.objects.select_related('table', 'waiter').prefetch_related('items__menu_item'), request.user)
    order = get_object_or_404(orders, pk=pk)
    return render(request, 'sales/ticket.html', {'order': order})


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
def checkout(request, pk):
    orders = scoped_queryset(Order.objects.select_related('table', 'waiter').prefetch_related('items__menu_item'), request.user)
    order = get_object_or_404(orders, pk=pk)
    tables = scoped_queryset(DiningTable.objects.filter(is_active=True), request.user, 'zone__branch__restaurant')
    return render(request, 'sales/checkout.html', {
        'order': order,
        'payment_methods': Payment.Method.choices,
        'tables': tables.select_related('zone__branch'),
    })


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
def requests_board(request):
    """Pedidos enviados por clientes desde el QR y llamados de mesa (mesero / cuenta)."""
    customer_orders = scoped_queryset(CustomerOrder.objects.all(), request.user)
    expire_old_customer_orders(customer_orders)
    pending = customer_orders.filter(status=CustomerOrder.Status.PENDING).select_related('table__zone').prefetch_related('items__menu_item')

    calls = list(scoped_queryset(
        TableRequest.objects.filter(attended_at__isnull=True).select_related('table__zone'),
        request.user, 'table__zone__branch__restaurant',
    ))
    open_orders = scoped_queryset(
        Order.objects.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED]), request.user,
    )
    orders_by_table = defaultdict(list)
    for order in open_orders:
        orders_by_table[order.table_id].append(order)
    for call in calls:
        call.open_orders = orders_by_table.get(call.table_id, [])

    return render(request, 'sales/requests.html', {'pending': pending, 'calls': calls})


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
@require_POST
def customer_order_confirm(request, pk):
    customer_order = get_object_or_404(scoped_queryset(CustomerOrder.objects.all(), request.user), pk=pk)
    try:
        confirm_customer_order(customer_order, request.user)
    except CustomerOrderError as exc:
        return render(request, 'error.html', {'message': str(exc)}, status=400)
    return redirect('requests_board')


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
@require_POST
def customer_order_reject(request, pk):
    customer_order = get_object_or_404(scoped_queryset(CustomerOrder.objects.all(), request.user), pk=pk)
    if customer_order.status != CustomerOrder.Status.PENDING:
        return render(request, 'error.html', {'message': 'Este pedido ya fue atendido o venció.'}, status=400)
    customer_order.status = CustomerOrder.Status.REJECTED
    customer_order.reject_reason = request.POST.get('reason', '').strip()[:160]
    customer_order.resolved_by = request.user
    customer_order.resolved_at = timezone.now()
    customer_order.save(update_fields=['status', 'reject_reason', 'resolved_by', 'resolved_at'])
    return redirect('requests_board')


@login_required
@role_required('admin', 'manager', 'cashier', 'waiter')
@require_POST
def table_request_attend(request, pk):
    table_request = get_object_or_404(
        scoped_queryset(TableRequest.objects.all(), request.user, 'table__zone__branch__restaurant'), pk=pk,
    )
    if table_request.attended_at is None:
        table_request.attended_at = timezone.now()
        table_request.attended_by = request.user
        table_request.save(update_fields=['attended_at', 'attended_by'])
    return redirect('requests_board')
