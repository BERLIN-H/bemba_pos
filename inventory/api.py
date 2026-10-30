from rest_framework import serializers, viewsets

from accounts.permissions import IsAdminOrManager
from inventory.models import Category, Ingredient, MenuItem, RecipeItem, StockMovement
from restaurant.tenancy import same_tenant, scoped_queryset


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class IngredientSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Ingredient
        fields = '__all__'


class RecipeItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source='ingredient.name', read_only=True)

    class Meta:
        model = RecipeItem
        fields = ['id', 'ingredient', 'ingredient_name', 'quantity']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError('La cantidad de la receta debe ser mayor que cero.')
        return value

    def validate_ingredient(self, value):
        if not same_tenant(self.context['request'].user, value.restaurant_id):
            raise serializers.ValidationError('El ingrediente no existe.')
        return value


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    recipe = RecipeItemSerializer(many=True, required=False)

    class Meta:
        model = MenuItem
        fields = ['id', 'category', 'category_name', 'name', 'description', 'price', 'tax_rate', 'image_url', 'is_available', 'is_kitchen_item', 'recipe']

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError('El precio no puede ser negativo.')
        return value

    def validate_category(self, value):
        if not same_tenant(self.context['request'].user, value.restaurant_id):
            raise serializers.ValidationError('La categoría no existe.')
        return value

    def create(self, validated_data):
        recipe_data = validated_data.pop('recipe', [])
        menu_item = MenuItem.objects.create(**validated_data)
        for row in recipe_data:
            RecipeItem.objects.create(menu_item=menu_item, **row)
        return menu_item

    def update(self, instance, validated_data):
        recipe_data = validated_data.pop('recipe', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if recipe_data is not None:
            instance.recipe.all().delete()
            for row in recipe_data:
                RecipeItem.objects.create(menu_item=instance, **row)
        return instance


class StockMovementSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source='ingredient.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = StockMovement
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError('La cantidad debe ser mayor que cero.')
        return value

    def validate_ingredient(self, value):
        if not same_tenant(self.context['request'].user, value.restaurant_id):
            raise serializers.ValidationError('El ingrediente no existe.')
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        movement = StockMovement.objects.create(
            created_by=user,
            restaurant=getattr(user, 'restaurant', None) or validated_data['ingredient'].restaurant,
            **validated_data,
        )
        ingredient = movement.ingredient
        if movement.movement_type == StockMovement.Type.IN:
            ingredient.current_stock += movement.quantity
        else:
            ingredient.current_stock -= movement.quantity
        ingredient.save(update_fields=['current_stock'])
        return movement


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        serializer.save(restaurant=getattr(self.request.user, 'restaurant', None))


class IngredientViewSet(viewsets.ModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        serializer.save(restaurant=getattr(self.request.user, 'restaurant', None))


class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.select_related('category').prefetch_related('recipe__ingredient')
    serializer_class = MenuItemSerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        serializer.save(restaurant=getattr(self.request.user, 'restaurant', None))


class StockMovementViewSet(viewsets.ModelViewSet):
    queryset = StockMovement.objects.select_related('ingredient', 'created_by')
    serializer_class = StockMovementSerializer
    permission_classes = [IsAdminOrManager]
    http_method_names = ['get', 'post', 'head', 'options']  # historial inmodificable

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user)
