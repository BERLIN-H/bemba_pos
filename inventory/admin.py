from django.contrib import admin

from inventory.models import Category, Ingredient, MenuItem, RecipeItem, StockMovement
from restaurant.admin import TenantAdminMixin


class InventoryTenantAdmin(TenantAdminMixin):
    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and request.user.restaurant_id and hasattr(obj, 'restaurant_id'):
            obj.restaurant = request.user.restaurant
        super().save_model(request, obj, form, change)


@admin.register(Category)
class CategoryAdmin(InventoryTenantAdmin, admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'is_active')
    list_filter = ('restaurant', 'is_active')


@admin.register(Ingredient)
class IngredientAdmin(InventoryTenantAdmin, admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'current_stock', 'min_stock', 'unit')
    list_filter = ('restaurant', 'unit', 'is_active')


@admin.register(MenuItem)
class MenuItemAdmin(InventoryTenantAdmin, admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'category', 'price', 'is_available')
    list_filter = ('restaurant', 'category', 'is_available')


@admin.register(RecipeItem)
class RecipeItemAdmin(admin.ModelAdmin):
    list_display = ('menu_item', 'ingredient', 'quantity')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.restaurant_id:
            return queryset
        return queryset.filter(menu_item__restaurant=request.user.restaurant)


@admin.register(StockMovement)
class StockMovementAdmin(InventoryTenantAdmin, admin.ModelAdmin):
    list_display = ('ingredient', 'restaurant', 'movement_type', 'quantity', 'created_by', 'created_at')
    list_filter = ('restaurant', 'movement_type')

# Register your models here.
