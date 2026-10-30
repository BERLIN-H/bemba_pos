from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from restaurant.models import DiningTable


def release_expired_tables(queryset=None):
    """Devuelve a "disponible" las mesas cuyo estado temporal ya venció.

    - Pendiente (alguien escaneó el QR pero no pidió): vence a los TABLE_PENDING_MINUTES.
    - Limpieza (el pedido se pagó): vence a los TABLE_CLEANING_MINUTES.
    Se llama al consultar las mesas, así no hace falta una tarea programada.
    """
    now = timezone.now()
    tables = queryset if queryset is not None else DiningTable.objects.all()
    rules = (
        (DiningTable.Status.PENDING, settings.TABLE_PENDING_MINUTES),
        (DiningTable.Status.CLEANING, settings.TABLE_CLEANING_MINUTES),
    )
    released = 0
    for status, minutes in rules:
        released += tables.filter(
            status=status, status_changed_at__lte=now - timedelta(minutes=minutes),
        ).update(status=DiningTable.Status.AVAILABLE, status_changed_at=now)
    return released
