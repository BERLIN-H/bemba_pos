from django.contrib import admin

from restaurant.models import Branch, DiningTable, RestaurantAccount, SubscriptionPlan, Zone


class TenantAdminMixin:
    tenant_lookup = 'restaurant'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.restaurant_id:
            return queryset
        return queryset.filter(**{self.tenant_lookup: request.user.restaurant})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and request.user.restaurant_id:
            if db_field.name == 'restaurant':
                kwargs['queryset'] = RestaurantAccount.objects.filter(pk=request.user.restaurant_id)
            if db_field.name == 'branch':
                kwargs['queryset'] = Branch.objects.filter(restaurant=request.user.restaurant)
            if db_field.name == 'zone':
                kwargs['queryset'] = Zone.objects.filter(branch__restaurant=request.user.restaurant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'monthly_price', 'max_branches', 'max_users', 'is_active')


@admin.register(RestaurantAccount)
class RestaurantAccountAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = 'id'
    list_display = ('business_name', 'plan', 'status', 'email', 'created_at')
    list_filter = ('plan', 'status')


@admin.register(Branch)
class BranchAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'is_active')
    list_filter = ('restaurant', 'is_active')


@admin.register(Zone)
class ZoneAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = 'branch__restaurant'
    list_display = ('name', 'branch', 'is_active')
    list_filter = ('branch__restaurant', 'branch', 'is_active')


@admin.register(DiningTable)
class DiningTableAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = 'zone__branch__restaurant'
    list_display = ('number', 'zone', 'seats', 'status', 'is_active')
    list_filter = ('zone__branch__restaurant', 'zone', 'status', 'is_active')

# Register your models here.
