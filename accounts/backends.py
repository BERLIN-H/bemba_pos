from django.contrib.auth.backends import ModelBackend

BLOCKED_RESTAURANT_STATUSES = ('suspended', 'cancelled')


class ActiveEmployeeBackend(ModelBackend):
    """Impide el acceso (web y JWT) a empleados desactivados y al personal de restaurantes suspendidos o cancelados."""

    def user_can_authenticate(self, user):
        if not super().user_can_authenticate(user) or not getattr(user, 'is_active_employee', True):
            return False
        if not user.is_superuser and user.restaurant_id and user.restaurant.status in BLOCKED_RESTAURANT_STATUSES:
            return False
        return True
