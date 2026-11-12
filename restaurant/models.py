import secrets

from django.conf import settings
from django.core.validators import FileExtensionValidator
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
    description = models.TextField(blank=True)
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    annual_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_branches = models.PositiveSmallIntegerField(default=1)
    max_users = models.PositiveSmallIntegerField(default=5)
    max_products = models.PositiveIntegerField(default=100)
    trial_days = models.PositiveSmallIntegerField(default=0)
    included_modules = models.CharField(max_length=255, blank=True)
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
    payment_instructions = models.TextField(blank=True)
    payment_qr_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    subscription_started_at = models.DateField(blank=True, null=True)
    subscription_ends_at = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['business_name']

    def __str__(self):
        return self.business_name


class SubscriptionPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        PAID = 'paid', 'Pagado'
        REJECTED = 'rejected', 'Rechazado'

    restaurant = models.ForeignKey(RestaurantAccount, on_delete=models.PROTECT, related_name='subscription_payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscription_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_method = models.CharField(max_length=40, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    invoice_number = models.CharField(max_length=50, blank=True)
    period_start = models.DateField(blank=True, null=True)
    period_end = models.DateField(blank=True, null=True)
    due_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='subscription_payments_recorded')
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Suscripción #{self.pk} · {self.restaurant.business_name}'


class SubscriptionPlanChange(models.Model):
    restaurant = models.ForeignKey(RestaurantAccount, on_delete=models.PROTECT, related_name='plan_changes')
    previous_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='changes_from')
    new_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='changes_to')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='subscription_plan_changes')
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-changed_at']


class SupportTicket(models.Model):
    class Priority(models.TextChoices):
        LOW = 'low', 'Baja'
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'Alta'
        URGENT = 'urgent', 'Urgente'

    class Status(models.TextChoices):
        OPEN = 'open', 'Abierto'
        IN_PROGRESS = 'in_progress', 'En proceso'
        PENDING = 'pending', 'Pendiente'
        RESOLVED = 'resolved', 'Resuelto'
        CLOSED = 'closed', 'Cerrado'

    restaurant = models.ForeignKey(RestaurantAccount, on_delete=models.PROTECT, related_name='support_tickets')
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='support_tickets_reported')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='support_tickets_assigned')
    category = models.CharField(max_length=80)
    title = models.CharField(max_length=180)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def ticket_number(self):
        return f'SP-{self.pk:06d}' if self.pk else 'Nuevo'

    def __str__(self):
        return f'{self.ticket_number} · {self.title}'


class PlatformActivity(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='platform_activity')
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    description = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class PlatformConfiguration(models.Model):
    site_name = models.CharField(max_length=120, default='Bemba POS')
    currency = models.CharField(max_length=8, default='COP')
    timezone = models.CharField(max_length=60, default='America/Bogota')
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    support_email = models.EmailField(blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)
    mail_from = models.EmailField(blank=True)
    payment_gateway = models.CharField(max_length=80, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.site_name


class PlatformIntegration(models.Model):
    name = models.CharField(max_length=120)
    provider = models.CharField(max_length=80)
    endpoint = models.URLField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']


class RestaurantSettings(models.Model):
    """Información e identidad del negocio, aislada por cuenta de restaurante."""
    class Theme(models.TextChoices):
        RESTAURANT_PRO = 'restaurant_pro', 'Restaurant Pro · Azul y blanco'
        COFFEE = 'coffee', 'Coffee Style · Marrón y crema'
        FRESH = 'fresh', 'Fresh Green · Verde y blanco'
        LUXURY = 'luxury', 'Luxury · Negro y dorado'
        OCEAN = 'ocean', 'Océano · Azul petróleo'
        TERRACOTTA = 'terracotta', 'Terracota · Arcilla y crema'

    class Font(models.TextChoices):
        INTER = 'Inter', 'Inter'
        ROBOTO = 'Roboto', 'Roboto'
        POPPINS = 'Poppins', 'Poppins'
        MONTSERRAT = 'Montserrat', 'Montserrat'
        NUNITO = 'Nunito', 'Nunito'
        OPEN_SANS = 'Open Sans', 'Open Sans'

    class Size(models.TextChoices):
        SMALL = 'small', 'Pequeño'
        MEDIUM = 'medium', 'Mediano'
        LARGE = 'large', 'Grande'

    restaurant = models.OneToOneField(RestaurantAccount, on_delete=models.CASCADE, related_name='settings')
    trade_name = models.CharField(max_length=160, blank=True)
    short_name = models.CharField(max_length=50, blank=True)
    slogan = models.CharField(max_length=180, blank=True)
    logo_file = models.ImageField(upload_to='restaurants/branding/', blank=True, validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])])
    sidebar_logo_file = models.ImageField(upload_to='restaurants/branding/', blank=True, validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])])
    favicon_file = models.ImageField(upload_to='restaurants/branding/', blank=True, validators=[FileExtensionValidator(['png', 'ico'])])
    cover_image_file = models.ImageField(upload_to='restaurants/branding/', blank=True, validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])])
    login_background_file = models.ImageField(upload_to='restaurants/branding/', blank=True, validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])])
    logo_url = models.URLField(blank=True)
    sidebar_logo_url = models.URLField(blank=True)
    favicon_url = models.URLField(blank=True)
    cover_image_url = models.URLField(blank=True)
    login_background_url = models.URLField(blank=True)
    theme = models.CharField(max_length=30, choices=Theme.choices, default=Theme.RESTAURANT_PRO)
    primary_color = models.CharField(max_length=7, default='#17324D')
    secondary_color = models.CharField(max_length=7, default='#E8EEF3')
    button_color = models.CharField(max_length=7, default='#17324D')
    accent_color = models.CharField(max_length=7, default='#D4A857')
    background_color = models.CharField(max_length=7, default='#F5F7FA')
    sidebar_color = models.CharField(max_length=7, default='#142B42')
    text_color = models.CharField(max_length=7, default='#263445')
    selected_color = models.CharField(max_length=7, default='#DDEFEA')
    font_family = models.CharField(max_length=20, choices=Font.choices, default=Font.INTER)
    font_size = models.CharField(max_length=10, choices=Size.choices, default=Size.MEDIUM)
    title_weight = models.PositiveSmallIntegerField(default=700)
    square_corners = models.BooleanField(default=False)
    compact_tables = models.BooleanField(default=False)
    dark_mode = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Personalización · {self.restaurant.business_name}'


class RestaurantPreferences(models.Model):
    restaurant = models.OneToOneField(RestaurantAccount, on_delete=models.CASCADE, related_name='preferences')
    address = models.CharField(max_length=180, blank=True)
    city = models.CharField(max_length=100, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    business_type = models.CharField(max_length=100, blank=True)
    business_hours = models.JSONField(default=dict, blank=True)
    timezone = models.CharField(max_length=60, default='America/Bogota')
    currency = models.CharField(max_length=8, default='COP')
    table_service = models.BooleanField(default=True)
    takeaway = models.BooleanField(default=False)
    delivery = models.BooleanField(default=False)
    whatsapp_orders = models.BooleanField(default=False)
    cancellation_approval = models.BooleanField(default=True)
    manual_discounts = models.BooleanField(default=False)
    tips = models.BooleanField(default=False)
    split_bills = models.BooleanField(default=False)
    open_accounts = models.BooleanField(default=True)
    require_customer = models.BooleanField(default=False)
    inventory_enabled = models.BooleanField(default=True)
    cash_open_required = models.BooleanField(default=True)
    cash_withdrawals = models.BooleanField(default=False)
    cash_deposits = models.BooleanField(default=False)
    refunds_allowed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class RestaurantModules(models.Model):
    restaurant = models.OneToOneField(RestaurantAccount, on_delete=models.CASCADE, related_name='modules')
    tables = models.BooleanField(default=True)
    delivery = models.BooleanField(default=True)
    takeaway = models.BooleanField(default=True)
    kitchen_kds = models.BooleanField(default=True)
    inventory = models.BooleanField(default=True)
    recipes = models.BooleanField(default=True)
    customers = models.BooleanField(default=True)
    suppliers = models.BooleanField(default=True)
    reservations = models.BooleanField(default=False)
    reports = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class RestaurantReceiptSettings(models.Model):
    class PaperSize(models.TextChoices):
        THERMAL_58 = '58mm', 'Térmico 58 mm'
        THERMAL_80 = '80mm', 'Térmico 80 mm'
        A4 = 'A4', 'A4'

    restaurant = models.OneToOneField(RestaurantAccount, on_delete=models.CASCADE, related_name='receipt_settings')
    header = models.CharField(max_length=180, blank=True)
    logo_file = models.ImageField(upload_to='restaurants/receipts/', blank=True, validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])])
    logo_url = models.URLField(blank=True)
    address = models.CharField(max_length=180, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    thank_you_message = models.CharField(max_length=180, blank=True, default='¡Gracias por tu compra!')
    footer = models.CharField(max_length=255, blank=True)
    paper_size = models.CharField(max_length=10, choices=PaperSize.choices, default=PaperSize.THERMAL_80)
    show_customer = models.BooleanField(default=True)
    show_tax = models.BooleanField(default=True)
    show_cashier = models.BooleanField(default=True)
    kitchen_ticket_note = models.CharField(max_length=180, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class RestaurantNotificationSettings(models.Model):
    restaurant = models.OneToOneField(RestaurantAccount, on_delete=models.CASCADE, related_name='notification_settings')
    new_orders = models.BooleanField(default=True)
    delayed_orders = models.BooleanField(default=True)
    low_stock = models.BooleanField(default=True)
    cash_close = models.BooleanField(default=True)
    cancelled_sales = models.BooleanField(default=True)
    cash_discrepancies = models.BooleanField(default=True)
    new_employees = models.BooleanField(default=False)
    daily_reports = models.BooleanField(default=False)
    sales_summary = models.BooleanField(default=False)
    in_app = models.BooleanField(default=True)
    email = models.BooleanField(default=False)
    whatsapp = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class BranchSettings(models.Model):
    branch = models.OneToOneField('restaurant.Branch', on_delete=models.CASCADE, related_name='settings')
    inherit_restaurant = models.BooleanField(default=True)
    timezone = models.CharField(max_length=60, blank=True)
    currency = models.CharField(max_length=8, blank=True)
    primary_color = models.CharField(max_length=7, blank=True)
    logo_file = models.ImageField(upload_to='restaurants/branches/', blank=True, validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])])
    logo_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)


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
