from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from restaurant.models import TableRequest
from restaurant.tenancy import scoped_queryset
from sales.models import CustomerOrder

POS_ROLES = ('manager', 'restaurant_admin', 'cashier', 'waiter')


def staff_alerts(request):
    """Cantidad de solicitudes de clientes pendientes, para el aviso del menú del personal."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not (user.is_superuser or user.role in POS_ROLES):
        return {}
    cutoff = timezone.now() - timedelta(minutes=settings.CUSTOMER_ORDER_EXPIRY_MINUTES)
    orders = scoped_queryset(CustomerOrder.objects.filter(status=CustomerOrder.Status.PENDING, created_at__gt=cutoff), user).count()
    calls = scoped_queryset(
        TableRequest.objects.filter(attended_at__isnull=True), user, 'table__zone__branch__restaurant',
    ).count()
    return {'pending_customer_orders': orders, 'open_table_requests': calls, 'requests_badge': orders + calls}


def tenant_customization(request):
    """Carga solo la personalización de la cuenta autenticada."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not getattr(user, 'restaurant_id', None):
        return {}
    restaurant = user.restaurant
    branding = getattr(restaurant, 'settings', None)
    preferences = getattr(restaurant, 'modules', None)
    from accounts.permissions import MODULE_ALIASES
    plan_modules = {value.strip().lower() for value in (restaurant.plan.included_modules or '').split(',') if value.strip()}
    enabled_modules = {}
    for name, aliases in MODULE_ALIASES.items():
        enabled = getattr(preferences, name, True) if preferences else True
        if plan_modules and not any(alias in plan_modules for alias in aliases):
            enabled = False
        enabled_modules[name] = enabled
    return {
        'restaurant_settings': branding,
        'restaurant_modules': enabled_modules,
        'restaurant_preferences': getattr(restaurant, 'preferences', None),
    }
