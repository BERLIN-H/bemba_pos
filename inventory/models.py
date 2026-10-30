from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


class Category(models.Model):
    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.CASCADE, related_name='categories', blank=True, null=True)
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=20, default='#0f766e')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('restaurant', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    class Unit(models.TextChoices):
        UNIT = 'unit', 'Unidad'
        GRAM = 'g', 'Gramo'
        KG = 'kg', 'Kilogramo'
        ML = 'ml', 'Mililitro'
        L = 'l', 'Litro'

    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.CASCADE, related_name='ingredients', blank=True, null=True)
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=10, choices=Unit.choices)
    current_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    min_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('restaurant', 'name')
        ordering = ['name']

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.CASCADE, related_name='menu_items', blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    image_url = models.URLField(blank=True)
    is_available = models.BooleanField(default=True)
    is_kitchen_item = models.BooleanField(default=True)

    class Meta:
        ordering = ['category__name', 'name']

    def __str__(self):
        return self.name


class RecipeItem(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='recipe')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='recipes')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        unique_together = ('menu_item', 'ingredient')


class StockMovement(models.Model):
    class Type(models.TextChoices):
        IN = 'in', 'Entrada'
        OUT = 'out', 'Salida'
        ADJUSTMENT = 'adjustment', 'Ajuste'
        SALE = 'sale', 'Venta'

    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.CASCADE, related_name='stock_movements', blank=True, null=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=Type.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Supplier(models.Model):
    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.CASCADE, related_name='suppliers', blank=True, null=True)
    name = models.CharField(max_length=120)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('restaurant', 'name')

    def __str__(self):
        return self.name


class StockAlert(models.Model):
    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.CASCADE, related_name='stock_alerts', blank=True, null=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='alerts')
    message = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Alert {self.ingredient} - {self.message}'

    def save(self, *args, **kwargs):
        created = self.pk is None
        super().save(*args, **kwargs)
        if created and not self.resolved:
            self.notify()

    def notify(self):
        recipients = getattr(settings, 'ALERT_EMAIL_RECIPIENTS', [])
        if not recipients:
            return
        subject = f'[Bemba] Alerta de stock: {self.ingredient.name}'
        message = f"Se ha generado una alerta de stock para {self.ingredient.name}:\n\n{self.message}\n\nStock actual: {self.ingredient.current_stock} {self.ingredient.unit}."
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Abierta'
        RECEIVED = 'received', 'Recibida'

    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.CASCADE, related_name='purchase_orders', blank=True, null=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    branch = models.ForeignKey('restaurant.Branch', on_delete=models.PROTECT, related_name='purchase_orders', blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Orden de compra #{self.pk} - {self.supplier.name}'

    def update_total(self):
        self.total = sum((item.line_total for item in self.items.all()), Decimal('0.00'))
        self.save(update_fields=['total'])

    def receive(self):
        if self.status != self.Status.OPEN:
            return
        for item in self.items.select_related('ingredient'):
            ingredient = item.ingredient
            ingredient.current_stock += item.quantity
            ingredient.save(update_fields=['current_stock'])
            StockMovement.objects.create(
                restaurant=self.restaurant,
                ingredient=ingredient,
                movement_type=StockMovement.Type.IN,
                quantity=item.quantity,
                note=f'Recepción orden {self.pk}',
                created_by=self.created_by,
            )
        self.status = self.Status.RECEIVED
        self.received_at = timezone.now()
        self.save(update_fields=['status', 'received_at'])


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='purchase_order_items')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('purchase_order', 'ingredient')

    @property
    def line_total(self):
        return self.quantity * self.unit_cost

# Create your models here.
