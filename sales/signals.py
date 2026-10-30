import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from sales.models import Payment
from sales.services import consume_order_inventory

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Payment)
def consume_inventory_on_payment(sender, instance, created, **kwargs):
    """Al registrar un pago se asegura que el inventario del pedido esté descontado (sin duplicar)."""
    if not created:
        return
    try:
        with transaction.atomic():
            consume_order_inventory(instance.order)
    except Exception:  # el cobro no debe fallar por un problema de inventario
        logger.exception('Error al descontar inventario del pedido %s', instance.order_id)
