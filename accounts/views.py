from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from accounts.models import User
from restaurant.tenancy import scoped_queryset


def assignable_roles(user):
    """Roles que el usuario actual puede asignar. Solo un administrador (o superusuario) crea administradores."""
    roles = User.Role.choices
    if user.is_superuser or user.role == User.Role.ADMIN:
        return roles
    return [(value, label) for value, label in roles if value != User.Role.ADMIN]


class BembaLoginView(LoginView):
    template_name = 'accounts/login.html'


class BembaLogoutView(LogoutView):
    next_page = reverse_lazy('login')


@login_required
def staff_list(request):
    """Listar empleados del restaurante del usuario"""
    if not request.user.has_role('admin', 'manager'):
        return render(request, 'error.html', {'message': 'No tienes permiso para acceder aquí.'}, status=403)
    
    users = scoped_queryset(User.objects.all(), request.user).exclude(is_superuser=True).select_related('branch')
    
    context = {
        'users': users,
        'roles': User.Role.choices,
    }
    return render(request, 'accounts/staff_list.html', context)


@login_required
def staff_create(request):
    """Crear nuevo empleado"""
    if not request.user.has_role('admin', 'manager'):
        return render(request, 'error.html', {'message': 'No tienes permiso para acceder aquí.'}, status=403)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        password = request.POST.get('password')
        role = request.POST.get('role', User.Role.WAITER)
        phone = request.POST.get('phone', '')
        
        error = None
        valid_roles = [value for value, _ in assignable_roles(request.user)]
        if not username or not username.strip():
            error = 'El nombre de usuario es obligatorio.'
        elif User.objects.filter(username=username).exists():
            error = 'El nombre de usuario ya existe.'
        elif role not in valid_roles:
            error = 'El rol seleccionado no es válido.'
        else:
            try:
                validate_password(password or '')
            except ValidationError as exc:
                error = ' '.join(exc.messages)
        if error:
            return render(request, 'accounts/staff_form.html', {
                'error': error,
                'roles': assignable_roles(request.user),
            })

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
            role=role,
            phone=phone,
            restaurant=request.user.restaurant,
            branch=request.user.branch,
            is_active_employee=True,
        )
        return HttpResponseRedirect(reverse_lazy('staff_list'))
    
    return render(request, 'accounts/staff_form.html', {
        'roles': assignable_roles(request.user),
    })


@login_required
def staff_edit(request, pk):
    """Editar empleado"""
    if not request.user.has_role('admin', 'manager'):
        return render(request, 'error.html', {'message': 'No tienes permiso para acceder aquí.'}, status=403)
    
    user = get_object_or_404(
        scoped_queryset(User.objects.all(), request.user).exclude(is_superuser=True),
        pk=pk
    )
    
    if request.method == 'POST':
        new_role = request.POST.get('role', user.role)
        if new_role not in [value for value, _ in assignable_roles(request.user)] and new_role != user.role:
            return render(request, 'accounts/staff_form.html', {
                'user': user, 'roles': assignable_roles(request.user), 'is_edit': True,
                'error': 'El rol seleccionado no es válido.',
            })
        password = request.POST.get('password')
        if password:
            try:
                validate_password(password, user)
            except ValidationError as exc:
                return render(request, 'accounts/staff_form.html', {
                    'user': user, 'roles': assignable_roles(request.user), 'is_edit': True,
                    'error': ' '.join(exc.messages),
                })
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone)
        user.role = request.POST.get('role', user.role)
        user.is_active_employee = request.POST.get('is_active_employee') == 'on'
        
        password = request.POST.get('password')
        if password:
            user.set_password(password)
        
        user.save()
        return HttpResponseRedirect(reverse_lazy('staff_list'))
    
    return render(request, 'accounts/staff_form.html', {
        'user': user,
        'roles': assignable_roles(request.user),
        'is_edit': True,
    })


@login_required
@require_POST
def staff_delete(request, pk):
    """Eliminar empleado (desactivar)"""
    if not request.user.has_role('admin', 'manager'):
        return render(request, 'error.html', {'message': 'No tienes permiso para acceder aquí.'}, status=403)
    
    user = get_object_or_404(
        scoped_queryset(User.objects.all(), request.user).exclude(is_superuser=True),
        pk=pk
    )
    if user.pk == request.user.pk:
        return render(request, 'error.html', {'message': 'No puedes desactivar tu propia cuenta.'}, status=400)
    
    user.is_active_employee = False
    user.save(update_fields=['is_active_employee'])
    
    return HttpResponseRedirect(reverse_lazy('staff_list'))


@login_required
@require_POST
def staff_activate(request, pk):
    """Activar empleado"""
    if not request.user.has_role('admin', 'manager'):
        return render(request, 'error.html', {'message': 'No tienes permiso para acceder aquí.'}, status=403)
    
    user = get_object_or_404(
        scoped_queryset(User.objects.all(), request.user).exclude(is_superuser=True),
        pk=pk
    )
    
    user.is_active_employee = True
    user.save(update_fields=['is_active_employee'])
    
    return HttpResponseRedirect(reverse_lazy('staff_list'))

