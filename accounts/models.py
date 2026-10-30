from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administrador'
        MANAGER = 'manager', 'Gerente'
        CASHIER = 'cashier', 'Cajero'
        WAITER = 'waiter', 'Mesero'
        CHEF = 'chef', 'Cocina'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WAITER)
    restaurant = models.ForeignKey('restaurant.RestaurantAccount', on_delete=models.PROTECT, related_name='users', blank=True, null=True)
    branch = models.ForeignKey('restaurant.Branch', on_delete=models.PROTECT, related_name='users', blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active_employee = models.BooleanField(default=True)

    def has_role(self, *roles):
        return self.is_superuser or self.role in roles

# Create your models here.
