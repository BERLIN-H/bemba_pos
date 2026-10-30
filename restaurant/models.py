import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_qr_token():
    """Código largo e impredecible para el QR de cada mesa."""
    return secrets.token_urlsafe(16)


class SubscriptionPlan(models.Model):
    class BillingCycle(models.TextChoices):
        MONTHLY = 'monthly', 'Mensual'
        YEARLY = 'yearly', 'Anual'

    name = models.CharField(max_length=80, unique=True)
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_branches = models.PositiveSmallIntegerField(default=1)
    max_users = models.PositiveSmallIntegerField(default=5)
    billing_cycle = models.CharField(max_length=20, choices=BillingCycle.choices, default=BillingCycle.MONTHLY)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['monthly_price', 'name']

    def __str__(self):
        return self.name


class RestaurantAccount(models.Model):
    class Status(models.TextChoices):
        TRIAL = 'trial', 'Prueba'
        ACTIVE = 'active', 'Activa'
        PAST_DUE = 'past_due', 'Pago vencido'
        SUSPENDED = 'suspended', 'Suspendida'
        CANCELLED = 'cancelled', 'Cancelada'

    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='restaurants')
    business_name = models.CharField(max_length=160)
    legal_name = models.CharField(max_length=160, blank=True)
    tax_id = models.CharField(max_length=40, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    subscription_started_at = models.DateField(blank=True, null=True)
    subscription_ends_at = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['business_name']

    def __str__(self):
        return self.business_name


class Branch(models.Model):
    restaurant = models.ForeignKey(RestaurantAccount, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=180, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('restaurant', 'name')
        ordering = ['restaurant__business_name', 'name']

    def __str__(self):
        return f'{self.restaurant} - {self.name}'


class Zone(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='zones', blank=True, null=True)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('branch', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class DiningTable(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Disponible'
        PENDING = 'pending', 'Pendiente'
        OCCUPIED = 'occupied', 'Ocupada'
        RESERVED = 'reserved', 'Reservada'
        CLEANING = 'cleaning', 'Limpieza'

    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name='tables')
    number = models.CharField(max_length=20)
    seats = models.PositiveSmallIntegerField(default=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    is_active = models.BooleanField(default=True)
    qr_token = models.CharField(max_length=40, unique=True, default=generate_qr_token, editable=False)
    status_changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('zone', 'number')
        ordering = ['zone__name', 'number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_status = self.__dict__.get('status')

    def save(self, *args, **kwargs):
        # Guarda cuándo cambió el estado para poder vencer "pendiente" y "limpieza" automáticamente.
        if self.pk is None or self.status != self._loaded_status:
            self.status_changed_at = timezone.now()
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'status_changed_at'}
        super().save(*args, **kwargs)
        self._loaded_status = self.status

    def __str__(self):
        return f'{self.zone} - Mesa {self.number}'

# Create your models here.


class TableRequest(models.Model):
    """Llamado del cliente desde la carta QR: pedir al mesero o pedir la cuenta."""

    class Kind(models.TextChoices):
        WAITER = 'waiter', 'Llamar al mesero'
        BILL = 'bill', 'Pedir la cuenta'

    table = models.ForeignKey(DiningTable, on_delete=models.CASCADE, related_name='requests')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    attended_at = models.DateTimeField(blank=True, null=True)
    attended_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='+')

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.get_kind_display()} - {self.table}'
