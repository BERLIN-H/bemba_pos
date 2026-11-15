"""Superadministracion global de Bemba POS. Acceso exclusivo a superusuarios."""
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from inventory.models import StockAlert
from restaurant.models import (Branch, PlatformActivity, PlatformConfiguration,
    PlatformIntegration, RestaurantAccount, SubscriptionPayment, SubscriptionPlan,
    SubscriptionPlanChange, SupportTicket, Zone)
from sales.models import Order, Payment


def superuser_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            return render(request, 'error.html', {'message': 'Solo el administrador de la plataforma puede entrar aquí.'}, status=403)
        return view(request, *args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def _log(request, action, description, obj=None):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
    PlatformActivity.objects.create(actor=request.user, action=action,
        target_type=obj.__class__.__name__ if obj else '', target_id=str(obj.pk) if obj else '',
        description=description[:255], ip_address=ip or None)


class RestaurantCreateForm(forms.Form):
    business_name = forms.CharField(label='Nombre del restaurante', max_length=160)
    email = forms.EmailField(label='Correo de contacto')
    phone = forms.CharField(label='Teléfono', max_length=30, required=False)
    plan = forms.ModelChoiceField(label='Plan', queryset=SubscriptionPlan.objects.none())
    admin_username = forms.CharField(label='Usuario del administrador del restaurante', max_length=150)
    admin_first_name = forms.CharField(label='Nombre del administrador', max_length=150, required=False)
    admin_last_name = forms.CharField(label='Apellido del administrador', max_length=150, required=False)
    admin_password = forms.CharField(label='Contraseña inicial del administrador', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].queryset = SubscriptionPlan.objects.filter(is_active=True)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_business_name(self):
        name = self.cleaned_data['business_name'].strip()
        if RestaurantAccount.objects.filter(business_name__iexact=name).exists():
            raise ValidationError('Ya existe un restaurante con ese nombre.')
        return name

    def clean_admin_username(self):
        username = self.cleaned_data['admin_username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('Ese nombre de usuario ya existe.')
        return username

    def clean(self):
        data = super().clean()
        if data.get('admin_password'):
            try:
                validate_password(data['admin_password'])
            except ValidationError as exc:
                self.add_error('admin_password', exc)
        return data


class PlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ['name', 'description', 'monthly_price', 'annual_price', 'max_branches', 'max_users', 'max_products', 'trial_days', 'included_modules', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3}), 'included_modules': forms.TextInput(attrs={'placeholder': 'POS, inventario, reportes'})}


class RestaurantEditForm(forms.ModelForm):
    class Meta:
        model = RestaurantAccount
        fields = ['business_name', 'legal_name', 'tax_id', 'email', 'phone', 'status']


@superuser_required
def platform_dashboard(request):
    today = timezone.localdate()
    active = RestaurantAccount.objects.filter(status=RestaurantAccount.Status.ACTIVE)
    paid = SubscriptionPayment.objects.filter(status=SubscriptionPayment.Status.PAID)
    monthly_paid = paid.filter(paid_at__date__gte=today.replace(day=1)).aggregate(v=Sum('amount'))['v'] or Decimal('0')
    # MRR es una estimación basada en planes activos, no caja efectivamente recibida.
    mrr = active.aggregate(v=Sum('plan__monthly_price'))['v'] or Decimal('0')
    due_soon = RestaurantAccount.objects.filter(subscription_ends_at__range=(today, today + timedelta(days=30)))
    months = []
    for offset in range(5, -1, -1):
        start = (today.replace(day=1) - timedelta(days=offset * 28)).replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        months.append((start, end))
    labels = [s.strftime('%b %Y') for s, _ in months]
    chart = {
        'labels': labels,
        'restaurants': [RestaurantAccount.objects.filter(created_at__date__gte=s, created_at__date__lt=e).count() for s, e in months],
        'users': [User.objects.filter(is_superuser=False, date_joined__date__gte=s, date_joined__date__lt=e).count() for s, e in months],
        'revenue': [float(paid.filter(paid_at__date__gte=s, paid_at__date__lt=e).aggregate(v=Sum('amount'))['v'] or 0) for s, e in months],
        'transactions': [Payment.objects.filter(created_at__date__gte=s, created_at__date__lt=e).count() for s, e in months],
    }
    plan_rows = list(active.values('plan__name').annotate(total=Count('id')).order_by('plan__name'))
    chart['plan_labels'] = [r['plan__name'] for r in plan_rows]
    chart['plan_values'] = [r['total'] for r in plan_rows]
    alerts = list(StockAlert.objects.select_related('ingredient', 'restaurant').order_by('-created_at')[:5])
    context = {
        'active_restaurants': active.count(), 'total_restaurants': RestaurantAccount.objects.count(),
        'suspended_restaurants': RestaurantAccount.objects.filter(status=RestaurantAccount.Status.SUSPENDED).count(),
        'total_users': User.objects.filter(is_superuser=False).count(), 'mrr': mrr,
        'monthly_paid': monthly_paid, 'active_subscriptions': active.count(),
        'pending_payments': SubscriptionPayment.objects.filter(status=SubscriptionPayment.Status.PENDING).count(),
        'transactions': Payment.objects.count(), 'recent_restaurants': RestaurantAccount.objects.select_related('plan').order_by('-created_at')[:6],
        'recent_payments': SubscriptionPayment.objects.select_related('restaurant', 'plan').order_by('-created_at')[:6],
        'activity': PlatformActivity.objects.select_related('actor')[:7], 'due_soon': due_soon[:5], 'alerts': alerts,
        'chart_json': json.dumps(chart),
    }
    return render(request, 'restaurant/platform_dashboard.html', context)


@superuser_required
def platform_restaurants(request):
    restaurants = RestaurantAccount.objects.select_related('plan').annotate(
        user_count=Count('users', distinct=True), table_count=Count('branches__zones__tables', distinct=True),
        branch_count=Count('branches', distinct=True), order_count=Count('orders', distinct=True)).order_by('business_name')
    q = request.GET.get('q', '').strip()
    if q:
        restaurants = restaurants.filter(business_name__icontains=q) | restaurants.filter(email__icontains=q)
    created = RestaurantAccount.objects.filter(pk=request.GET.get('creado')).first() if request.GET.get('creado', '').isdigit() else None
    created_manager = created.users.filter(role=User.Role.RESTAURANT_ADMIN).first() if created else None
    return render(request, 'restaurant/platform_list.html', {'restaurants': restaurants,
        'created': created, 'created_manager': created_manager, 'plans': SubscriptionPlan.objects.filter(is_active=True),
        'q': q})


@superuser_required
def platform_restaurant_create(request):
    form = RestaurantCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            restaurant = RestaurantAccount.objects.create(plan=data['plan'], business_name=data['business_name'], email=data['email'], phone=data['phone'], status=RestaurantAccount.Status.ACTIVE)
            branch = Branch.objects.create(restaurant=restaurant, name='Sede Principal')
            zone = Zone.objects.create(branch=branch, name='Salón')
            manager = User(username=data['admin_username'], first_name=data['admin_first_name'], last_name=data['admin_last_name'], role=User.Role.RESTAURANT_ADMIN, restaurant=restaurant, branch=branch)
            manager.set_password(data['admin_password']); manager.save()
            _log(request, 'restaurant_created', f'Restaurante creado: {restaurant.business_name}', restaurant)
        return redirect(f"{reverse('platform_restaurant_list')}?creado={restaurant.pk}")
    return render(request, 'restaurant/platform_form.html', {'form': form}, status=400 if form.errors else 200)


@superuser_required
def platform_restaurant_edit(request, pk):
    restaurant = get_object_or_404(RestaurantAccount, pk=pk)
    form = RestaurantEditForm(request.POST or None, instance=restaurant)
    if request.method == 'POST' and form.is_valid():
        restaurant = form.save()
        _log(request, 'restaurant_updated', f'Restaurante actualizado: {restaurant.business_name}', restaurant)
        return redirect('platform_restaurant_list')
    return render(request, 'restaurant/platform_restaurant_edit.html', {'restaurant': restaurant, 'form': form})


@superuser_required
@require_POST
def platform_restaurant_status(request, pk):
    restaurant = get_object_or_404(RestaurantAccount, pk=pk)
    status = request.POST.get('status')
    if status not in (RestaurantAccount.Status.ACTIVE, RestaurantAccount.Status.SUSPENDED):
        return render(request, 'error.html', {'message': 'Estado no válido.'}, status=400)
    restaurant.status = status; restaurant.save(update_fields=['status'])
    _log(request, 'restaurant_status', f'{restaurant.business_name}: {restaurant.get_status_display()}', restaurant)
    return redirect('platform_restaurant_list')


@superuser_required
@require_POST
def platform_restaurant_plan(request, pk):
    restaurant = get_object_or_404(RestaurantAccount, pk=pk)
    plan = get_object_or_404(SubscriptionPlan, pk=request.POST.get('plan_id'), is_active=True)
    old = restaurant.plan
    if old.pk != plan.pk:
        SubscriptionPlanChange.objects.create(restaurant=restaurant, previous_plan=old, new_plan=plan, changed_by=request.user)
        restaurant.plan = plan; restaurant.save(update_fields=['plan'])
        _log(request, 'plan_changed', f'{restaurant.business_name}: {old.name} → {plan.name}', restaurant)
    return redirect('platform_restaurant_list')


@superuser_required
def platform_branches(request):
    return render(request, 'restaurant/platform_table.html', {'title': 'Sedes', 'subtitle': 'Ubicaciones de todos los restaurantes', 'headers': ['Sede', 'Restaurante', 'Ubicación', 'Teléfono', 'Estado'], 'rows': [[b.name, b.restaurant.business_name, b.address or '—', b.phone or '—', 'Activa' if b.is_active else 'Inactiva'] for b in Branch.objects.select_related('restaurant')]})


@superuser_required
def platform_plans(request):
    editing = get_object_or_404(SubscriptionPlan, pk=request.GET.get('edit')) if request.GET.get('edit', '').isdigit() else None
    if request.method == 'POST' and request.POST.get('plan_id', '').isdigit():
        editing = get_object_or_404(SubscriptionPlan, pk=request.POST['plan_id'])
    form = PlanForm(request.POST or None, instance=editing)
    if request.method == 'POST' and form.is_valid():
        plan = form.save(); _log(request, 'plan_updated' if editing else 'plan_created', f'Plan guardado: {plan.name}', plan); return redirect('platform_plans')
    return render(request, 'restaurant/platform_plans.html', {'plans': SubscriptionPlan.objects.annotate(restaurant_count=Count('restaurants')), 'form': form, 'editing': editing})


@superuser_required
@require_POST
def platform_plan_toggle(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk); plan.is_active = not plan.is_active; plan.save(update_fields=['is_active'])
    _log(request, 'plan_status', f'Plan {plan.name}: {"activo" if plan.is_active else "inactivo"}', plan)
    return redirect('platform_plans')


@superuser_required
def platform_payments(request):
    qs = SubscriptionPayment.objects.select_related('restaurant', 'plan', 'recorded_by')
    return render(request, 'restaurant/platform_payments.html', {'payments': qs, 'paid_total': qs.filter(status='paid').aggregate(v=Sum('amount'))['v'] or 0, 'pending_total': qs.filter(status='pending').count(), 'restaurants': RestaurantAccount.objects.all(), 'plans': SubscriptionPlan.objects.filter(is_active=True)})


@superuser_required
@require_POST
def platform_payment_create(request):
    restaurant = get_object_or_404(RestaurantAccount, pk=request.POST.get('restaurant'))
    plan = get_object_or_404(SubscriptionPlan, pk=request.POST.get('plan'))
    amount = Decimal(request.POST.get('amount', '0'))
    if amount <= 0: return redirect('platform_payments')
    payment = SubscriptionPayment.objects.create(restaurant=restaurant, plan=plan, amount=amount, status=request.POST.get('status') if request.POST.get('status') in ('pending', 'paid') else 'pending', payment_method=request.POST.get('method', ''), reference=request.POST.get('reference', ''), invoice_number=request.POST.get('invoice', ''), due_date=request.POST.get('due_date') or None, period_start=request.POST.get('period_start') or None, period_end=request.POST.get('period_end') or None, recorded_by=request.user, notes=request.POST.get('notes', ''))
    if payment.status == 'paid':
        payment.paid_at = timezone.now(); payment.save(update_fields=['paid_at'])
        if restaurant.plan_id != plan.pk:
            SubscriptionPlanChange.objects.create(restaurant=restaurant, previous_plan=restaurant.plan, new_plan=plan, changed_by=request.user, note=f'Actualización al confirmar pago #{payment.pk}')
        restaurant.plan = plan; restaurant.status = RestaurantAccount.Status.ACTIVE
        restaurant.subscription_started_at = payment.period_start or timezone.localdate()
        restaurant.subscription_ends_at = payment.period_end
        restaurant.save(update_fields=['plan', 'status', 'subscription_started_at', 'subscription_ends_at'])
    _log(request, 'subscription_payment_created', f'Pago #{payment.pk} registrado para {restaurant.business_name}', payment)
    return redirect('platform_payments')


@superuser_required
@require_POST
def platform_payment_status(request, pk):
    payment = get_object_or_404(SubscriptionPayment, pk=pk)
    status = request.POST.get('status')
    if status in ('paid', 'rejected', 'pending'):
        payment.status = status
        payment.paid_at = timezone.now() if status == 'paid' else None
        payment.save(update_fields=['status', 'paid_at'])
        if status == 'paid':
            if payment.restaurant.plan_id != payment.plan_id:
                SubscriptionPlanChange.objects.create(restaurant=payment.restaurant, previous_plan=payment.restaurant.plan, new_plan=payment.plan, changed_by=request.user, note=f'Actualización al confirmar pago #{payment.pk}')
            payment.restaurant.plan = payment.plan; payment.restaurant.status = RestaurantAccount.Status.ACTIVE
            payment.restaurant.subscription_started_at = payment.period_start or timezone.localdate()
            payment.restaurant.subscription_ends_at = payment.period_end
            payment.restaurant.save(update_fields=['plan', 'status', 'subscription_started_at', 'subscription_ends_at'])
        _log(request, 'subscription_payment_status', f'Pago #{payment.pk}: {payment.get_status_display()}', payment)
    return redirect('platform_payments')


@superuser_required
def platform_users(request):
    users = User.objects.filter(is_superuser=False).select_related('restaurant', 'branch').order_by('-date_joined')
    q = request.GET.get('q', '').strip()
    if q: users = users.filter(username__icontains=q) | users.filter(email__icontains=q)
    return render(request, 'restaurant/platform_users.html', {'users': users, 'q': q, 'roles': [(v, label) for v, label in User.Role.choices if v != User.Role.PLATFORM_ADMIN]})


@superuser_required
@require_POST
def platform_user_status(request, pk):
    user = get_object_or_404(User, pk=pk, is_superuser=False); user.is_active = not user.is_active; user.save(update_fields=['is_active'])
    _log(request, 'user_status', f'Usuario {user.username}: {"activo" if user.is_active else "bloqueado"}', user)
    return redirect('platform_users')


@superuser_required
@require_POST
def platform_user_role(request, pk):
    user = get_object_or_404(User, pk=pk, is_superuser=False)
    role = request.POST.get('role')
    allowed_roles = {value for value, _ in User.Role.choices if value != User.Role.PLATFORM_ADMIN}
    if role in allowed_roles and (role != User.Role.RESTAURANT_ADMIN or user.restaurant_id):
        user.role = role
        user.save(update_fields=['role'])
        _log(request, 'user_role_changed', f'Rol actualizado para {user.username}: {user.get_role_display()}', user)
    return redirect('platform_users')


@superuser_required
def platform_roles(request):
    roles = [{'name': 'Administrador de plataforma', 'scope': 'Global', 'description': 'Gestiona restaurantes, planes, suscripciones, usuarios, soporte y configuración.'}, {'name': 'Gerente', 'scope': 'Su restaurante', 'description': 'Administra equipo, menú, inventario, sedes y operación de su restaurante.'}, {'name': 'Cajero', 'scope': 'Su sede', 'description': 'Gestiona cobros y consulta cuentas abiertas de su sede.'}, {'name': 'Mesero', 'scope': 'Su sede', 'description': 'Toma pedidos, agrega productos y los envía a cocina.'}, {'name': 'Cocina', 'scope': 'Su sede', 'description': 'Consulta pedidos enviados y actualiza su preparación.'}]
    return render(request, 'restaurant/platform_table.html', {'title': 'Roles y permisos', 'subtitle': 'Alcance de acceso por perfil', 'headers': ['Rol', 'Alcance', 'Permisos principales'], 'rows': [[r['name'], r['scope'], r['description']] for r in roles]})


@superuser_required
def platform_support(request):
    if request.method == 'POST':
        ticket = get_object_or_404(SupportTicket, pk=request.POST.get('ticket_id'))
        ticket.status = request.POST.get('status', ticket.status); ticket.priority = request.POST.get('priority', ticket.priority)
        ticket.assigned_to = request.user; ticket.closed_at = timezone.now() if ticket.status in ('resolved', 'closed') else None
        ticket.save(); _log(request, 'support_updated', f'Ticket {ticket.ticket_number}: {ticket.get_status_display()}', ticket)
        return redirect('platform_support')
    return render(request, 'restaurant/platform_support.html', {'tickets': SupportTicket.objects.select_related('restaurant', 'reporter', 'assigned_to'), 'restaurants': RestaurantAccount.objects.all()})


@superuser_required
@require_POST
def platform_support_create(request):
    restaurant = get_object_or_404(RestaurantAccount, pk=request.POST.get('restaurant'))
    ticket = SupportTicket.objects.create(restaurant=restaurant, reporter=request.user, category=request.POST.get('category', 'General'), title=request.POST.get('title', '')[:180], description=request.POST.get('description', ''), priority=request.POST.get('priority', 'normal'))
    _log(request, 'support_created', f'Ticket {ticket.ticket_number} creado', ticket)
    return redirect('platform_support')


@superuser_required
def platform_notifications(request):
    return render(request, 'restaurant/platform_notifications.html', {'due_soon': RestaurantAccount.objects.filter(subscription_ends_at__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30))).select_related('plan'), 'pending': SubscriptionPayment.objects.filter(status='pending').select_related('restaurant'), 'alerts': StockAlert.objects.select_related('ingredient', 'restaurant').order_by('-created_at')[:50], 'suspended': RestaurantAccount.objects.filter(status='suspended')})


@superuser_required
def platform_settings(request):
    config = PlatformConfiguration.objects.first() or PlatformConfiguration()
    if request.method == 'POST':
        for field in ('site_name', 'currency', 'timezone', 'support_email', 'whatsapp_number', 'mail_from', 'payment_gateway'):
            setattr(config, field, request.POST.get(field, getattr(config, field)))
        try: config.default_tax_rate = Decimal(request.POST.get('default_tax_rate', config.default_tax_rate))
        except Exception: pass
        config.save(); _log(request, 'settings_updated', 'Configuración global actualizada', config); return redirect('platform_settings')
    return render(request, 'restaurant/platform_settings.html', {'config': config})


@superuser_required
def platform_integrations(request):
    if request.method == 'POST' and request.POST.get('action') == 'create':
        item = PlatformIntegration.objects.create(name=request.POST.get('name', ''), provider=request.POST.get('provider', ''), endpoint=request.POST.get('endpoint', ''), description=request.POST.get('description', ''))
        _log(request, 'integration_created', f'Integración creada: {item.name}', item); return redirect('platform_integrations')
    return render(request, 'restaurant/platform_integrations.html', {'integrations': PlatformIntegration.objects.all()})


@superuser_required
@require_POST
def platform_integration_toggle(request, pk):
    item = get_object_or_404(PlatformIntegration, pk=pk); item.enabled = not item.enabled; item.save(update_fields=['enabled'])
    _log(request, 'integration_status', f'Integración {item.name}: {"activa" if item.enabled else "inactiva"}', item)
    return redirect('platform_integrations')


@superuser_required
def platform_audit(request):
    return render(request, 'restaurant/platform_table.html', {'title': 'Auditoría y actividad', 'subtitle': 'Registro de acciones administrativas', 'headers': ['Fecha', 'Administrador', 'Acción', 'Detalle', 'Objeto'], 'rows': [[a.created_at.strftime('%d/%m/%Y %H:%M'), a.actor.username if a.actor else 'Sistema', a.action, a.description, f'{a.target_type} #{a.target_id}'] for a in PlatformActivity.objects.select_related('actor')[:200]]})


@superuser_required
def platform_sessions(request):
    sessions = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()).order_by('-expire_date')[:250]:
        data = session.get_decoded(); user = User.objects.filter(pk=data.get('_auth_user_id')).first()
        if user: sessions.append({'key': session.session_key, 'user': user, 'expires': session.expire_date})
    return render(request, 'restaurant/platform_sessions.html', {'sessions': sessions})


@superuser_required
@require_POST
def platform_session_revoke(request, key):
    Session.objects.filter(session_key=key).delete(); _log(request, 'session_revoked', 'Sesión revocada', None)
    return redirect('platform_sessions')


@superuser_required
def platform_backups(request):
    backup_dir = Path(settings.BASE_DIR) / 'backups'
    files = sorted(backup_dir.glob('bemba-*.json'), reverse=True) if backup_dir.exists() else []
    return render(request, 'restaurant/platform_backups.html', {'files': files})


@superuser_required
@require_POST
def platform_backup_create(request):
    from django.core.management import call_command
    backup_dir = Path(settings.BASE_DIR) / 'backups'; backup_dir.mkdir(exist_ok=True)
    path = backup_dir / f"bemba-{timezone.now().strftime('%Y%m%d-%H%M%S')}.json"
    with path.open('w', encoding='utf-8') as output: call_command('dumpdata', '--natural-foreign', '--natural-primary', exclude=['contenttypes', 'auth.permission', 'sessions'], indent=2, stdout=output)
    _log(request, 'backup_created', f'Respaldo de datos creado: {path.name}')
    return redirect('platform_backups')


@superuser_required
def platform_backup_download(request, filename):
    backup_dir = (Path(settings.BASE_DIR) / 'backups').resolve(); path = (backup_dir / filename).resolve()
    if path.parent != backup_dir or not path.name.startswith('bemba-') or path.suffix != '.json' or not path.exists(): raise Http404
    return FileResponse(path.open('rb'), as_attachment=True, filename=path.name)
