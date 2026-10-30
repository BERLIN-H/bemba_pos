from rest_framework import serializers, viewsets

from accounts.permissions import IsPOSStaff, ReadPOSWriteManager, ReadStaffWriteSuperuser
from restaurant.models import Branch, DiningTable, RestaurantAccount, SubscriptionPlan, Zone
from restaurant.services import release_expired_tables
from restaurant.tenancy import same_tenant, scoped_queryset


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'


class RestaurantAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantAccount
        fields = '__all__'


class BranchSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.business_name', read_only=True)

    class Meta:
        model = Branch
        fields = '__all__'


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = '__all__'

    def validate_branch(self, value):
        if value is not None and not same_tenant(self.context['request'].user, value.restaurant_id):
            raise serializers.ValidationError('La sucursal no existe.')
        return value


class DiningTableSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source='zone.name', read_only=True)
    branch_name = serializers.CharField(source='zone.branch.name', read_only=True)

    class Meta:
        model = DiningTable
        fields = ['id', 'zone', 'zone_name', 'branch_name', 'number', 'seats', 'status', 'is_active']

    def validate_zone(self, value):
        branch = value.branch
        if not same_tenant(self.context['request'].user, getattr(branch, 'restaurant_id', None)):
            raise serializers.ValidationError('La zona no existe.')
        return value

    def validate(self, attrs):
        # Meseros y cajeros solo pueden cambiar el estado de la mesa (p. ej. limpieza -> disponible).
        user = self.context['request'].user
        if self.instance is not None and not user.is_superuser and user.role not in ('admin', 'manager'):
            if set(self.initial_data.keys()) - {'status'}:
                raise serializers.ValidationError('Solo puedes cambiar el estado de la mesa.')
        return attrs


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [ReadStaffWriteSuperuser]


class RestaurantAccountViewSet(viewsets.ModelViewSet):
    queryset = RestaurantAccount.objects.select_related('plan')
    serializer_class = RestaurantAccountSerializer
    permission_classes = [ReadStaffWriteSuperuser]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user, 'id')


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.select_related('restaurant')
    serializer_class = BranchSerializer
    permission_classes = [ReadPOSWriteManager]

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_superuser:
            serializer.save()
        else:
            serializer.save(restaurant=user.restaurant)  # un gerente solo crea sucursales de su restaurante

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user)


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer
    permission_classes = [ReadPOSWriteManager]

    def get_queryset(self):
        return scoped_queryset(super().get_queryset(), self.request.user, 'branch__restaurant')


class DiningTableViewSet(viewsets.ModelViewSet):
    queryset = DiningTable.objects.select_related('zone__branch__restaurant')
    serializer_class = DiningTableSerializer

    def get_permissions(self):
        if self.action == 'partial_update':
            return [IsPOSStaff()]  # el personal de sala actualiza el estado de la mesa
        return [ReadPOSWriteManager()]

    def get_queryset(self):
        queryset = scoped_queryset(super().get_queryset(), self.request.user, 'zone__branch__restaurant')
        release_expired_tables(queryset)
        return queryset
