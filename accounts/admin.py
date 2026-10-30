from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class BembaUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'restaurant', 'branch', 'role', 'is_active_employee', 'is_staff')
    list_filter = ('restaurant', 'branch', 'role', 'is_active_employee', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (('Bemba', {'fields': ('restaurant', 'branch', 'role', 'phone', 'is_active_employee')}),)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.restaurant_id:
            return queryset
        return queryset.filter(restaurant=request.user.restaurant)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and request.user.restaurant_id:
            obj.restaurant = request.user.restaurant
        super().save_model(request, obj, form, change)

# Register your models here.
