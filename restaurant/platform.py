"""Administración de la plataforma (solo superusuario): crear y suspender restaurantes."""
from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import User
from restaurant.models import Branch, DiningTable, RestaurantAccount, SubscriptionPlan, Zone


def superuser_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            return render(request, 'error.html', {'message': 'Solo el administrador de la plataforma puede entrar aquí.'}, status=403)
        return view(request, *args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


class RestaurantCreateForm(forms.Form):
    business_name = forms.CharField(label='Nombre del restaurante', max_length=160)
    email = forms.EmailField(label='Correo de contacto')
    phone = forms.CharField(label='Teléfono', max_length=30, required=False)
    plan = forms.ModelChoiceField(label='Plan', queryset=SubscriptionPlan.objects.none())
    table_count = forms.IntegerField(label='Cantidad de mesas iniciales', min_value=1, max_value=60, initial=6)
    admin_username = forms.CharField(label='Usuario del administrador', max_length=150)
    admin_first_name = forms.CharField(label='Nombre del administrador', max_length=150, required=False)
    admin_last_name = forms.CharField(label='Apellido del administrador', max_length=150, required=False)
    admin_password = forms.CharField(label='Contraseña del administrador', widget=forms.PasswordInput)

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
        password = data.get('admin_password')
        if password:
            try:
                validate_password(password)
            except ValidationError as exc:
                self.add_error('admin_password', exc)
        return data


@superuser_required
def platform_restaurants(request):
    restaurants = RestaurantAccount.objects.select_related('plan').annotate(
        user_count=Count('users', distinct=True),
        table_count=Count('branches__zones__tables', distinct=True),
        branch_count=Count('branches', distinct=True),
        order_count=Count('orders', distinct=True),
    ).order_by('business_name')
    created = None
    created_id = request.GET.get('creado', '')
    if created_id.isdigit():
        created = RestaurantAccount.objects.filter(pk=int(created_id)).first()
        created_admin = created.users.filter(role='admin').first() if created else None
    else:
        created_admin = None
    return render(request, 'restaurant/platform_list.html', {
        'restaurants': restaurants, 'created': created, 'created_admin': created_admin,
    })


@superuser_required
def platform_restaurant_create(request):
    form = RestaurantCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            restaurant = RestaurantAccount.objects.create(
                plan=data['plan'], business_name=data['business_name'], email=data['email'], phone=data['phone'],
                status=RestaurantAccount.Status.ACTIVE,
            )
            branch = Branch.objects.create(restaurant=restaurant, name='Sede Principal')
            zone = Zone.objects.create(branch=branch, name='Salón')
            DiningTable.objects.bulk_create([
                DiningTable(zone=zone, number=str(i), seats=4) for i in range(1, data['table_count'] + 1)
            ])
            admin = User(
                username=data['admin_username'], first_name=data['admin_first_name'], last_name=data['admin_last_name'],
                role=User.Role.ADMIN, restaurant=restaurant, branch=branch,
            )
            admin.set_password(data['admin_password'])
            admin.save()
        return redirect(f"{reverse('platform_restaurants')}?creado={restaurant.pk}")
    return render(request, 'restaurant/platform_form.html', {'form': form}, status=400 if form.errors else 200)


@superuser_required
@require_POST
def platform_restaurant_status(request, pk):
    restaurant = get_object_or_404(RestaurantAccount, pk=pk)
    new_status = request.POST.get('status')
    if new_status not in (RestaurantAccount.Status.ACTIVE, RestaurantAccount.Status.SUSPENDED):
        return render(request, 'error.html', {'message': 'Estado no válido.'}, status=400)
    restaurant.status = new_status
    restaurant.save(update_fields=['status'])
    return redirect('platform_restaurants')
