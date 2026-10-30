from django.contrib.auth import get_user_model
from rest_framework import serializers, viewsets

from accounts.permissions import IsAdminOrManager
from restaurant.tenancy import scoped_queryset


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'restaurant', 'branch', 'role', 'phone', 'is_active_employee', 'password']

    def validate(self, attrs):
        request_user = self.context['request'].user
        if not request_user.is_superuser:
            # Un gerente/administrador solo trabaja dentro de su restaurante y no crea administradores.
            attrs['restaurant'] = request_user.restaurant
            branch = attrs.get('branch')
            if branch is not None and branch.restaurant_id != request_user.restaurant_id:
                raise serializers.ValidationError({'branch': 'La sucursal no existe.'})
            if attrs.get('role') == User.Role.ADMIN and request_user.role != User.Role.ADMIN:
                raise serializers.ValidationError({'role': 'No tienes permiso para crear administradores.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user).exclude(is_superuser=True) \
            if not self.request.user.is_superuser else super().get_queryset()
