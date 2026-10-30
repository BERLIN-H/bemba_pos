from django.contrib import admin

from sales.models import Order, OrderItem, Payment
from restaurant.admin import TenantAdminMixin


@admin.register(Order)
class OrderAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'branch', 'table', 'waiter', 'status', 'total', 'created_at')
    list_filter = ('restaurant', 'branch', 'status')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'menu_item', 'quantity', 'unit_price')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.restaurant_id:
            return queryset
        return queryset.filter(order__restaurant=request.user.restaurant)


@admin.register(Payment)
class PaymentAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('order', 'restaurant', 'method', 'amount', 'cashier', 'created_at')
    list_filter = ('restaurant', 'method')

# Register your models here.
