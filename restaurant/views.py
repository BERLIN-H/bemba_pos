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

from accounts.permissions import restaurant_module_required, role_required
from inventory.models import Category, MenuItem
from restaurant.models import DiningTable, RestaurantAccount, Zone
from restaurant import settings_forms as customization_forms
from restaurant.models import Branch, BranchSettings, PlatformActivity, RestaurantModules, RestaurantNotificationSettings, RestaurantPreferences, RestaurantReceiptSettings, RestaurantSettings
from restaurant.services import release_expired_tables
from restaurant.tenancy import scoped_queryset
from sales.models import Order

OPEN_ORDER_STATUSES = [
    Order.Status.OPEN, Order.Status.SENT, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED,
]


@login_required
def restaurant_customization(request):
    """Configuración de la cuenta, accesible solo por su administrador de restaurante."""
    if request.user.is_superuser or request.user.role != 'restaurant_admin' or not request.user.restaurant_id:
        return render(request, 'error.html', {'message': 'Solo el administrador de este restaurante puede cambiar su configuración.'}, status=403)
    restaurant = request.user.restaurant
    branding, _ = RestaurantSettings.objects.get_or_create(restaurant=restaurant)
    preferences, _ = RestaurantPreferences.objects.get_or_create(restaurant=restaurant)
    modules, _ = RestaurantModules.objects.get_or_create(restaurant=restaurant)
    receipt, _ = RestaurantReceiptSettings.objects.get_or_create(restaurant=restaurant)
    notifications, _ = RestaurantNotificationSettings.objects.get_or_create(restaurant=restaurant)
    tab = request.GET.get('tab', request.POST.get('tab', 'apariencia'))
    tabs = {'identidad', 'apariencia', 'operacion', 'modulos', 'comprobantes', 'notificaciones'}
    if tab not in tabs:
        tab = 'apariencia'
    forms_by_tab = {
        'apariencia': customization_forms.BrandingForm,
        'operacion': customization_forms.PreferencesForm,
        'modulos': customization_forms.ModulesForm,
        'comprobantes': customization_forms.ReceiptForm,
        'notificaciones': customization_forms.NotificationsForm,
    }
    instances = {'apariencia': branding, 'operacion': preferences, 'modulos': modules, 'comprobantes': receipt, 'notificaciones': notifications}
    form = forms_by_tab[tab](request.POST or None, request.FILES or None, instance=instances[tab]) if tab in forms_by_tab else None
    if tab == 'modulos' and form:
        allowed = {name.strip().lower() for name in (restaurant.plan.included_modules or '').split(',') if name.strip()}
        for field, aliases in {'tables': ('mesas','tables'), 'delivery': ('domicilios','delivery'), 'takeaway': ('para llevar','takeaway'), 'kitchen_kds': ('cocina kds','cocina','kds'), 'inventory': ('inventario','inventory'), 'recipes': ('recetas','recipes'), 'customers': ('clientes','customers'), 'suppliers': ('proveedores','suppliers'), 'reservations': ('reservaciones','reservas'), 'reports': ('reportes','reports')}.items():
            if allowed and not any(alias in allowed for alias in aliases):
                form.fields[field].disabled = True
                form.initial[field] = False
    account_form = customization_forms.RestaurantInfoForm(request.POST or None, instance=restaurant) if tab == 'identidad' else None
    identity_preferences = customization_forms.PreferencesForm(request.POST or None, instance=preferences) if tab == 'identidad' else None
    if request.method == 'POST':
        if request.POST.get('action') == 'restore_defaults':
            RestaurantSettings.objects.filter(restaurant=restaurant).delete()
            RestaurantPreferences.objects.filter(restaurant=restaurant).delete()
            RestaurantModules.objects.filter(restaurant=restaurant).delete()
            RestaurantReceiptSettings.objects.filter(restaurant=restaurant).delete()
            RestaurantNotificationSettings.objects.filter(restaurant=restaurant).delete()
            BranchSettings.objects.filter(branch__restaurant=restaurant).delete()
            return redirect(f"{request.path}?tab=apariencia")
        if tab == 'identidad' and account_form.is_valid() and identity_preferences.is_valid():
            account_form.save(); identity_preferences.save()
            PlatformActivity.objects.create(actor=request.user, action='tenant_identity_updated', target_type='RestaurantAccount', target_id=str(restaurant.pk), description=f'Identidad comercial actualizada: {restaurant.business_name}')
            return redirect(f"{request.path}?tab={tab}&guardado=1")
        if form and form.is_valid():
            if tab == 'modulos':
                allowed = {name.strip().lower() for name in (restaurant.plan.included_modules or '').split(',') if name.strip()}
                module_map = {'tables': ('mesas', 'tables'), 'delivery': ('domicilios', 'delivery'), 'takeaway': ('para llevar', 'takeaway'), 'kitchen_kds': ('cocina kds', 'cocina', 'kds'), 'inventory': ('inventario', 'inventory'), 'recipes': ('recetas', 'recipes'), 'customers': ('clientes', 'customers'), 'suppliers': ('proveedores', 'suppliers'), 'reservations': ('reservaciones', 'reservas'), 'reports': ('reportes', 'reports')}
                if allowed:
                    for field, aliases in module_map.items():
                        if not any(alias in allowed for alias in aliases):
                            setattr(form.instance, field, False)
            form.save()
            PlatformActivity.objects.create(actor=request.user, action=f'tenant_{tab}_updated', target_type='RestaurantAccount', target_id=str(restaurant.pk), description=f'Configuración {tab} actualizada para {restaurant.business_name}')
            return redirect(f"{request.path}?tab={tab}&guardado=1")
    available_modules = [name.strip() for name in (restaurant.plan.included_modules or '').split(',') if name.strip()]
    aliases = {'tables': ('mesas', 'tables'), 'delivery': ('domicilios', 'delivery'), 'takeaway': ('para llevar', 'takeaway'), 'kitchen_kds': ('cocina kds', 'cocina', 'kds'), 'inventory': ('inventario', 'inventory'), 'recipes': ('recetas', 'recipes'), 'customers': ('clientes', 'customers'), 'suppliers': ('proveedores', 'suppliers'), 'reservations': ('reservaciones', 'reservas'), 'reports': ('reportes', 'reports')}
    allowed_set = {value.lower() for value in available_modules}
    module_allowed = {field: (not available_modules or any(alias in allowed_set for alias in values)) for field, values in aliases.items()}
    return render(request, 'restaurant/customization.html', {
        'tab': tab, 'form': form, 'account_form': account_form, 'identity_preferences': identity_preferences,
        'available_modules': available_modules, 'modules_limited': bool(available_modules),
        'module_allowed': module_allowed,
        'saved': request.GET.get('guardado') == '1', 'restaurant': restaurant,
    })


@login_required
def branch_customization(request, pk):
    if request.user.is_superuser or request.user.role != 'restaurant_admin' or not request.user.restaurant_id:
        return render(request, 'error.html', {'message': 'Solo el administrador de este restaurante puede cambiar la configuración de sus sedes.'}, status=403)
    branch = get_object_or_404(scoped_queryset(Branch.objects.all(), request.user), pk=pk)
    from restaurant.models import BranchSettings
    branch_settings, _ = BranchSettings.objects.get_or_create(branch=branch)
    form = customization_forms.BranchSettingsForm(request.POST or None, request.FILES or None, instance=branch_settings)
    if request.method == 'POST' and form.is_valid():
        form.save()
        PlatformActivity.objects.create(actor=request.user, action='branch_settings_updated', target_type='Branch', target_id=str(branch.pk), description=f'Configuración de sede actualizada: {branch.name}')
        return redirect(f'{request.path}?guardado=1')
    return render(request, 'restaurant/branch_customization.html', {'branch': branch, 'form': form, 'saved': request.GET.get('guardado') == '1'})


@login_required
@restaurant_module_required('tables')
@role_required('manager', 'cashier', 'waiter')
def tables(request):
    error = ''
    tables_qs = scoped_queryset(DiningTable.objects.filter(is_active=True), request.user, 'zone__branch__restaurant')
    zones = scoped_queryset(Zone.objects.all(), request.user, 'branch__restaurant')
    branches = scoped_queryset(Branch.objects.filter(is_active=True), request.user)
    if request.method == 'POST' and request.user.role in ('manager', 'restaurant_admin'):
        action = request.POST.get('action')
        if action == 'create_zone':
            branch = branches.filter(pk=request.POST.get('branch_id') or None).first()
            name = request.POST.get('zone_name', '').strip()
            if branch and name:
                Zone.objects.get_or_create(branch=branch, name=name)
                return redirect('tables')
            error = 'Selecciona una sede y escribe el nombre de la zona.'
        elif action == 'create_table':
            zone = zones.filter(pk=request.POST.get('zone_id') or None).first()
            number = request.POST.get('number', '').strip()
            try:
                seats = int(request.POST.get('seats') or '4')
            except ValueError:
                seats = 0
            if not zone or not number or seats < 1 or seats > 100:
                error = 'Verifica la zona, el número y la capacidad de la mesa.'
            else:
                existing = DiningTable.objects.filter(zone=zone, number=number).first()
                if existing and existing.is_active:
                    error = 'Ya existe ese número de mesa en la zona seleccionada.'
                elif existing:
                    existing.seats = seats
                    existing.is_active = True
                    existing.status = DiningTable.Status.AVAILABLE
                    existing.save(update_fields=['seats', 'is_active', 'status'])
                    return redirect('tables')
                else:
                    DiningTable.objects.create(zone=zone, number=number, seats=seats)
                    return redirect('tables')
        elif action == 'remove_table':
            table = scoped_queryset(DiningTable.objects.all(), request.user, 'zone__branch__restaurant').filter(pk=request.POST.get('table_id') or None).first()
            if not table:
                error = 'No se encontró la mesa.'
            elif table.orders.filter(status__in=OPEN_ORDER_STATUSES).exists():
                error = f'No se puede quitar la mesa {table.number}: tiene una cuenta abierta.'
            else:
                # Se archiva para conservar los pedidos y pagos históricos.
                table.is_active = False
                table.save(update_fields=['is_active'])
                return redirect('tables')
    release_expired_tables(tables_qs)
    table_list = list(tables_qs.select_related('zone'))
    open_orders = scoped_queryset(
        Order.objects.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED]),
        request.user,
    ).select_related('table')

    orders_by_table = {}
    for order in open_orders:
        orders_by_table.setdefault(order.table_id, []).append(order)
    for table in table_list:
        table.open_orders = orders_by_table.get(table.id, [])
        table.open_order = table.open_orders[0] if table.open_orders else None

    return render(request, 'restaurant/tables.html', {
        'zones': zones.prefetch_related('tables'), 'branches': branches,
        'tables': table_list,
        'error': error, 'can_manage_tables': request.user.role in ('manager', 'restaurant_admin'),
    })


@login_required
@restaurant_module_required('tables')
@role_required('manager', 'cashier', 'waiter')
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
@restaurant_module_required('tables')
@role_required('manager')
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
@restaurant_module_required('tables')
@role_required('manager')
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
