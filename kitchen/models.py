from django.db import models


class KitchenTicket(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        PREPARING = 'preparing', 'Preparando'
        READY = 'ready', 'Lista'
        DELIVERED = 'delivered', 'Entregada'

    order = models.OneToOneField('sales.Order', on_delete=models.CASCADE, related_name='kitchen_ticket')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

# Create your models here.
