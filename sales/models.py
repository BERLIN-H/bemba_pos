from decimal import Decimal

from django.conf import settings
from django.db import models, transaction


class Order(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Abierta'
        SENT = 'sent', 'En cocina'
        PREPARING = 'preparing', 'Preparando'
        READY = 'ready', 'Lista'
        SERVED = 'served', 'Servida'
        PAID = 'paid', 'Pagada'
        CANCELLED = 'cancelled', 'Cancelada'

    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.PROTECT, related_name='orders', blank=True, null=True)
    branch = models.ForeignKey('restaurant.Branch', on_delete=models.PROTECT, related_name='orders', blank=True, null=True)
    table = models.ForeignKey('restaurant.DiningTable', on_delete=models.PROTECT, related_name='orders')
    waiter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    inventory_consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def recalculate(self):
        subtotal = sum((item.line_subtotal for item in self.items.all()), Decimal('0.00'))
        tax = sum((item.line_tax for item in self.items.all()), Decimal('0.00'))
        self.subtotal = subtotal
        self.tax = tax
        self.total = max(subtotal + tax - self.discount, Decimal('0.00'))
        self.save(update_fields=['subtotal', 'tax', 'total'])

    @transaction.atomic
    def consume_inventory(self):
        """Descuenta del stock los ingredientes de la receta. Es idempotente: solo actúa una vez por pedido.

        Devuelve True si descontó en esta llamada y False si ya estaba descontado.
        """
        from inventory.models import Ingredient, StockMovement

        order = Order.objects.select_for_update().get(pk=self.pk)
        if order.inventory_consumed:
            self.inventory_consumed = True
            return False

        for item in order.items.select_related('menu_item').prefetch_related('menu_item__recipe'):
            for recipe_item in item.menu_item.recipe.all():
                ingredient = Ingredient.objects.select_for_update().get(pk=recipe_item.ingredient_id)
                quantity = recipe_item.quantity * item.quantity
                ingredient.current_stock -= quantity
                ingredient.save(update_fields=['current_stock'])
                StockMovement.objects.create(
                    restaurant=order.restaurant or ingredient.restaurant,
                    ingredient=ingredient,
                    movement_type=StockMovement.Type.SALE,
                    quantity=quantity,
                    note=f'Consumo automático pedido #{self.id}',
                    created_by=self.waiter,
                )

        Order.objects.filter(pk=self.pk).update(inventory_consumed=True)
        self.inventory_consumed = True
        return True

    def __str__(self):
        return f'Pedido #{self.pk}'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey('inventory.MenuItem', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)
    sent_to_kitchen = models.BooleanField(default=False)

    @property
    def line_subtotal(self):
        return self.unit_price * self.quantity

    @property
    def line_tax(self):
        return self.line_subtotal * (self.tax_rate / Decimal('100.00'))

    def save(self, *args, **kwargs):
        if not self.unit_price:
            self.unit_price = self.menu_item.price
        if not self.tax_rate:
            self.tax_rate = self.menu_item.tax_rate
        super().save(*args, **kwargs)
        self.order.recalculate()


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Efectivo'
        CARD = 'card', 'Tarjeta'
        TRANSFER = 'transfer', 'Transferencia'
        MIXED = 'mixed', 'Mixto'

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name='payment')
    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.PROTECT, related_name='payments', blank=True, null=True)
    branch = models.ForeignKey('restaurant.Branch', on_delete=models.PROTECT, related_name='payments', blank=True, null=True)
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    received = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reference = models.CharField(max_length=80, blank=True)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payments')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.order_id:
            self.restaurant = self.order.restaurant
            self.branch = self.order.branch
        self.change = max(self.received - self.amount, Decimal('0.00'))
        super().save(*args, **kwargs)


class CustomerOrder(models.Model):
    """Pedido que el cliente envía desde la carta QR. No llega a cocina hasta que un mesero lo confirma."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Por confirmar'
        CONFIRMED = 'confirmed', 'Confirmado'
        REJECTED = 'rejected', 'Rechazado'
        EXPIRED = 'expired', 'Vencido'

    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.PROTECT, related_name='customer_orders', blank=True, null=True)
    table = models.ForeignKey('restaurant.DiningTable', on_delete=models.PROTECT, related_name='customer_orders')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=255, blank=True)
    reject_reason = models.CharField(max_length=160, blank=True)
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, blank=True, null=True, related_name='customer_origin')
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['created_at']

    @property
    def estimated_total(self):
        total = Decimal('0.00')
        for item in self.items.all():
            line = item.menu_item.price * item.quantity
            total += line + line * (item.menu_item.tax_rate / Decimal('100.00'))
        return total

    def __str__(self):
        return f'Pedido de cliente #{self.pk} - {self.table}'


class CustomerOrderItem(models.Model):
    customer_order = models.ForeignKey(CustomerOrder, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey('inventory.MenuItem', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    notes = models.CharField(max_length=255, blank=True)
