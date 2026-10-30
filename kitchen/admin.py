from django.contrib import admin

from kitchen.models import KitchenTicket


@admin.register(KitchenTicket)
class KitchenTicketAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'created_at', 'updated_at')
    list_filter = ('status',)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.restaurant_id:
            return queryset
        return queryset.filter(order__restaurant=request.user.restaurant)

# Register your models here.
