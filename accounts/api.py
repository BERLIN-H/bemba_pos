from django.contrib.auth import get_user_model
from rest_framework import serializers, viewsets

from accounts.permissions import IsManagerOrPlatformAdmin
from restaurant.tenancy import scoped_queryset


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'restaurant', 'branch', 'role', 'phone', 'is_active_employee', 'password']

    def validate(self, attrs):
        request_user = self.context['request'].user
        if attrs.get('role') == User.Role.PLATFORM_ADMIN:
            raise serializers.ValidationError({'role': 'El administrador de plataforma se configura de forma protegida.'})
        if not request_user.is_superuser:
            # El gerente solo crea y administra personal de su propio restaurante.
            attrs['restaurant'] = request_user.restaurant
            branch = attrs.get('branch')
            if branch is not None and branch.restaurant_id != request_user.restaurant_id:
                raise serializers.ValidationError({'branch': 'La sucursal no existe.'})
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
    permission_classes = [IsManagerOrPlatformAdmin]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user).exclude(is_superuser=True) \
            if not self.request.user.is_superuser else super().get_queryset()
