from functools import wraps

from django.shortcuts import render
from rest_framework.permissions import SAFE_METHODS, BasePermission

MODULE_ALIASES = {
    'tables': ('mesas', 'tables'), 'delivery': ('domicilios', 'delivery'),
    'takeaway': ('para llevar', 'takeaway'), 'kitchen_kds': ('cocina kds', 'cocina', 'kds'),
    'inventory': ('inventario', 'inventory'), 'recipes': ('recetas', 'recipes'),
    'customers': ('clientes', 'customers'), 'suppliers': ('proveedores', 'suppliers'),
    'reservations': ('reservaciones', 'reservas'), 'reports': ('reportes', 'reports'),
}


def tenant_has_module(restaurant, module_name):
    plan_modules = {value.strip().lower() for value in (restaurant.plan.included_modules or '').split(',') if value.strip()}
    if plan_modules and not any(alias in plan_modules for alias in MODULE_ALIASES.get(module_name, (module_name,))):
        return False
    try:
        preferences = restaurant.modules
    except AttributeError:
        preferences = None
    return preferences is None or getattr(preferences, module_name, True)


class RolePermission(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.role in self.allowed_roles))


class IsManagerOrPlatformAdmin(RolePermission):
    allowed_roles = ('manager', 'restaurant_admin')


class IsPOSStaff(RolePermission):
    allowed_roles = ('manager', 'restaurant_admin', 'cashier', 'waiter')


class IsKitchenStaff(RolePermission):
    allowed_roles = ('manager', 'restaurant_admin', 'chef')


class IsInventoryModuleEnabled(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        restaurant = getattr(user, 'restaurant', None)
        if not restaurant:
            return False
        return tenant_has_module(restaurant, 'inventory')


class IsOrderStaff(RolePermission):
    """Quien puede ver y avanzar pedidos: POS + cocina."""
    allowed_roles = ('manager', 'restaurant_admin', 'cashier', 'waiter', 'chef')


class ReadPOSWriteManager(BasePermission):
    """Lectura para el personal; escritura solo gerencia del restaurante o plataforma."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return user.role in IsOrderStaff.allowed_roles
        return user.role in IsManagerOrPlatformAdmin.allowed_roles


class ReadStaffWriteSuperuser(BasePermission):
    """Planes y restaurantes (nivel SaaS): lectura para el personal, escritura solo superusuario."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return request.method in SAFE_METHODS and user.role in IsOrderStaff.allowed_roles


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.is_superuser or request.user.role in roles or ('manager' in roles and request.user.role == 'restaurant_admin'):
                return view_func(request, *args, **kwargs)
            return render(request, 'error.html', {
                'message': 'No tienes permiso para acceder aquí.'
            }, status=403)
        return _wrapped
    return decorator


def restaurant_module_required(module_name):
    """Backend gate for plan-enabled tenant modules; platform admins bypass tenant gates."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            restaurant = getattr(user, 'restaurant', None)
            if not restaurant:
                return render(request, 'error.html', {'message': 'No tienes un restaurante asociado.'}, status=403)
            if not tenant_has_module(restaurant, module_name):
                return render(request, 'error.html', {'message': 'Este módulo está desactivado para el restaurante.'}, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
