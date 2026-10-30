from decimal import Decimal
from datetime import datetime, time

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.permissions import role_required
from inventory.models import Ingredient
from restaurant.models import DiningTable
from sales.models import Order, OrderItem, Payment
from restaurant.tenancy import scoped_queryset


def money_value(value):
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return float(value)
    return value


def day_range(day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = start + timezone.timedelta(days=1)
    return start, end


def filter_by_day(queryset, field_name, day):
    start, end = day_range(day)
    return queryset.filter(**{f'{field_name}__gte': start, f'{field_name}__lt': end})


ROLE_HOME = {
    'admin': 'dashboard',
    'manager': 'dashboard',
    'cashier': 'cashier_panel',
    'waiter': 'waiter_panel',
    'chef': 'kitchen',
}


@login_required
def home(request):
    """Lleva a cada usuario a la pantalla de inicio que le corresponde según su rol."""
    if request.user.is_superuser:
        return redirect('platform_restaurants')
    return redirect(ROLE_HOME.get(request.user.role, 'dashboard'))


@login_required
@role_required('admin', 'manager')
def dashboard(request):
    today = timezone.localdate()
    week_start = today - timezone.timedelta(days=6)

    payments = scoped_queryset(Payment.objects.select_related('order'), request.user)
    orders = scoped_queryset(Order.objects.select_related('table', 'waiter'), request.user)
    tables = scoped_queryset(DiningTable.objects.all(), request.user, 'zone__branch__restaurant')
    ingredients = scoped_queryset(Ingredient.objects.all(), request.user)
    order_items = OrderItem.objects.select_related('order', 'menu_item')
    order_items = scoped_queryset(order_items, request.user, 'order__restaurant')

    total_sales = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_payments = payments.count()
    payments_today = filter_by_day(payments, 'created_at', today)
    open_orders = orders.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED]).count()
    occupied_tables = tables.filter(status=DiningTable.Status.OCCUPIED).count()
    low_stock = ingredients.filter(current_stock__lte=F('min_stock')).count()
    paid_order_items = order_items.filter(order__status=Order.Status.PAID)
    products_sold = paid_order_items.aggregate(total=Sum('quantity'))['total'] or 0
    kitchen_orders = orders.filter(status__in=[Order.Status.SENT, Order.Status.PREPARING, Order.Status.READY]).count()
    average_ticket = Decimal('0.00')
    if total_payments:
        average_ticket = total_sales / total_payments

    daily_sales = []
    daily_labels = []
    for offset in range(7):
        day = week_start + timezone.timedelta(days=offset)
        daily_labels.append(day.strftime('%d/%m'))
        total = filter_by_day(payments, 'created_at', day).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        daily_sales.append(money_value(total))

    top_products = list(
        paid_order_items.values('menu_item__name')
        .annotate(total=Sum('quantity'))
        .order_by('-total')[:5]
    )
    payment_methods = list(
        payments.values('method')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('method')
    )
    order_statuses = list(
        orders.values('status')
        .annotate(total=Count('id'))
        .order_by('status')
    )
    table_statuses = list(
        tables.values('status')
        .annotate(total=Count('id'))
        .order_by('status')
    )

    status_labels = dict(Order.Status.choices)
    table_status_labels = dict(DiningTable.Status.choices)
    method_labels = dict(Payment.Method.choices)

    chart_data = {
        'dailySales': {
            'labels': daily_labels,
            'values': daily_sales,
        },
        'topProducts': {
            'labels': [row['menu_item__name'] or 'Sin nombre' for row in top_products],
            'values': [row['total'] or 0 for row in top_products],
        },
        'paymentMethods': {
            'labels': [method_labels.get(row['method'], row['method']) for row in payment_methods],
            'values': [money_value(row['total']) for row in payment_methods],
        },
        'orderStatuses': {
            'labels': [status_labels.get(row['status'], row['status']) for row in order_statuses],
            'values': [row['total'] for row in order_statuses],
        },
        'tableStatuses': {
            'labels': [table_status_labels.get(row['status'], row['status']) for row in table_statuses],
            'values': [row['total'] for row in table_statuses],
        },
    }

    context = {
        'sales_today': total_sales,
        'open_orders': open_orders,
        'occupied_tables': occupied_tables,
        'low_stock': low_stock,
        'average_ticket': average_ticket,
        'total_payments': total_payments,
        'products_sold_today': products_sold,
        'kitchen_orders': kitchen_orders,
        'total_tables': tables.count(),
        'chart_data': chart_data,
        'low_stock_items': ingredients.filter(current_stock__lte=F('min_stock'))[:6],
        'recent_orders': orders.order_by('-id').select_related('table', 'waiter')[:8],
    }
    return render(request, 'dashboard/index.html', context)


@login_required
@role_required('cashier')
def cashier_panel(request):
    """Inicio del cajero: lo que debe cobrar y lo que ha cobrado él hoy."""
    today = timezone.localdate()
    orders = scoped_queryset(Order.objects.select_related('table', 'waiter'), request.user)
    to_charge = orders.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED]).order_by('-status', 'created_at')
    my_payments = filter_by_day(
        scoped_queryset(Payment.objects.select_related('order__table'), request.user).filter(cashier=request.user),
        'created_at', today,
    )
    totals = my_payments.aggregate(total=Sum('amount'), count=Count('id'))
    methods = my_payments.values('method').annotate(total=Sum('amount'), count=Count('id')).order_by('method')
    method_labels = dict(Payment.Method.choices)
    return render(request, 'dashboard/cashier.html', {
        'to_charge': to_charge[:20],
        'ready_count': to_charge.filter(status=Order.Status.READY).count(),
        'pending_count': to_charge.count(),
        'collected_total': totals['total'] or Decimal('0.00'),
        'collected_count': totals['count'] or 0,
        'methods': [{'label': method_labels.get(m['method'], m['method']), 'total': m['total'], 'count': m['count']} for m in methods],
        'recent_payments': my_payments.order_by('-created_at')[:6],
    })


@login_required
@role_required('waiter')
def waiter_panel(request):
    """Inicio del mesero: sus pedidos abiertos y el estado de las mesas."""
    orders = scoped_queryset(Order.objects.select_related('table'), request.user)
    my_open = orders.filter(waiter=request.user).exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED]).order_by('-created_at')
    tables = scoped_queryset(DiningTable.objects.filter(is_active=True), request.user, 'zone__branch__restaurant')
    status_labels = dict(DiningTable.Status.choices)
    table_counts = [
        {'label': status_labels[row['status']], 'status': row['status'], 'total': row['total']}
        for row in tables.values('status').annotate(total=Count('id')).order_by('status')
    ]
    return render(request, 'dashboard/waiter.html', {
        'my_open': my_open[:20],
        'ready_orders': my_open.filter(status=Order.Status.READY),
        'table_counts': table_counts,
    })
