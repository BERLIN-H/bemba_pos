from functools import wraps

from django.shortcuts import render
from rest_framework.permissions import SAFE_METHODS, BasePermission


class RolePermission(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.role in self.allowed_roles))


class IsAdminOrManager(RolePermission):
    allowed_roles = ('admin', 'manager')


class IsPOSStaff(RolePermission):
    allowed_roles = ('admin', 'manager', 'cashier', 'waiter')


class IsKitchenStaff(RolePermission):
    allowed_roles = ('admin', 'manager', 'chef')


class IsOrderStaff(RolePermission):
    """Quien puede ver y avanzar pedidos: POS + cocina."""
    allowed_roles = ('admin', 'manager', 'cashier', 'waiter', 'chef')


class ReadPOSWriteManager(BasePermission):
    """Lectura para el personal; escritura solo administrador/gerente."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return user.role in IsOrderStaff.allowed_roles
        return user.role in IsAdminOrManager.allowed_roles


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
            if request.user.is_superuser or request.user.role in roles:
                return view_func(request, *args, **kwargs)
            return render(request, 'error.html', {
                'message': 'No tienes permiso para acceder aquí.'
            }, status=403)
        return _wrapped
    return decorator
