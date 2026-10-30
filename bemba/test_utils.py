"""Datos de prueba compartidos por las pruebas automatizadas de Bemba POS."""
from decimal import Decimal

from rest_framework.test import APIClient

from accounts.models import User
from inventory.models import Category, Ingredient, MenuItem, RecipeItem
from restaurant.models import Branch, DiningTable, RestaurantAccount, SubscriptionPlan, Zone

PASSWORD = 'Clave-Segura-123'


def make_restaurant(name='Restaurante A', suffix='a'):
    """Crea un restaurante completo: sucursal, zona, mesas, usuarios por rol y menú con receta."""
    plan, _ = SubscriptionPlan.objects.get_or_create(name='Plan Pro', defaults={'monthly_price': 100000})
    restaurant = RestaurantAccount.objects.create(plan=plan, business_name=name, email=f'{suffix}@test.com', status='active')
    branch = Branch.objects.create(restaurant=restaurant, name='Principal')
    zone = Zone.objects.create(branch=branch, name='Salón')
    tables = [DiningTable.objects.create(zone=zone, number=str(i), seats=4) for i in range(1, 4)]

    users = {}
    for role in ('admin', 'manager', 'cashier', 'waiter', 'chef'):
        users[role] = User.objects.create_user(
            username=f'{role}_{suffix}', password=PASSWORD, role=role,
            restaurant=restaurant, branch=branch, first_name=role.capitalize(), last_name=suffix.upper(),
        )

    category = Category.objects.create(restaurant=restaurant, name='Platos')
    ingredient = Ingredient.objects.create(
        restaurant=restaurant, name='Carne', unit='g', current_stock=Decimal('1000'), min_stock=Decimal('100'),
    )
    burger = MenuItem.objects.create(
        restaurant=restaurant, category=category, name='Hamburguesa', price=Decimal('20000'), tax_rate=Decimal('8'),
    )
    RecipeItem.objects.create(menu_item=burger, ingredient=ingredient, quantity=Decimal('200'))
    soda = MenuItem.objects.create(
        restaurant=restaurant, category=category, name='Gaseosa', price=Decimal('5000'), tax_rate=Decimal('0'),
    )
    return {
        'restaurant': restaurant, 'branch': branch, 'zone': zone, 'tables': tables,
        'users': users, 'category': category, 'ingredient': ingredient, 'burger': burger, 'soda': soda,
    }


def api_as(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client
