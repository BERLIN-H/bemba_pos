"""Carga datos de demostración completos para que el equipo evaluador pueda probar todo.

Crea 3 restaurantes con sus sucursales, mesas, personal por rol, menú con recetas, inventario, proveedores,
una semana de ventas históricas y un estado "vivo" (pedidos en cocina, mesas ocupadas, un pedido de cliente
por confirmar y llamados de mesa). También crea el superusuario de la plataforma.

Uso:
    python manage.py seed_demo            # crea lo que falte (no duplica)
    python manage.py seed_demo --reset    # borra los datos demo y los recrea desde cero
"""
import os
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.test.utils import override_settings
from django.utils import timezone

from accounts.models import User
from inventory.models import (
    Category, Ingredient, MenuItem, PurchaseOrder, RecipeItem, StockAlert, StockMovement, Supplier,
)
from kitchen.models import KitchenTicket
from restaurant.models import Branch, DiningTable, RestaurantAccount, SubscriptionPlan, TableRequest, Zone
from sales.models import CustomerOrder, CustomerOrderItem, Order, OrderItem, Payment
from sales.services import consume_order_inventory

DEMO_PASSWORD = os.getenv('SEED_DEMO_PASSWORD', 'Bemba2026*')
SUPERUSER = 'superadmin_demo'

PLANS = [
    ('Plan Inicial', 60000, 1, 5),
    ('Plan Profesional', 120000, 3, 15),
    ('Plan Empresarial', 250000, 10, 50),
]

STAFF = [  # clave de usuario, rol, nombre, apellido
    ('admin', 'admin', 'Ana', 'Administradora'),
    ('gerente', 'manager', 'Gabriel', 'Gerente'),
    ('cajero', 'cashier', 'Carla', 'Cajera'),
    ('mesero', 'waiter', 'Mateo', 'Mesero'),
    ('mesero2', 'waiter', 'Lucía', 'Mesera'),
    ('cocina', 'chef', 'Camilo', 'Cocinero'),
]

# nombre, unidad, stock, mínimo, costo unitario
RESTAURANTS = [
    {
        'name': 'Bemba Demo', 'suffix': 'demo', 'email': 'demo@bemba.test', 'plan': 'Plan Profesional',
        'branches': [('Sede Principal', 'Calle 15 # 10-20, Riohacha', [('Salón', 6), ('Terraza', 4)])],
        'ingredients': [
            ('Carne de res', 'g', 20000, 2000, 0.03), ('Pan de hamburguesa', 'unit', 200, 30, 800),
            ('Queso', 'g', 8000, 1000, 0.025), ('Pollo', 'g', 15000, 2000, 0.02), ('Papa', 'g', 30000, 3000, 0.004),
            ('Arroz', 'g', 25000, 3000, 0.004), ('Gaseosa 400ml', 'unit', 150, 24, 1800),
            ('Jugo de naranja', 'ml', 20000, 3000, 0.003), ('Cerveza', 'unit', 120, 24, 2500),
        ],
        'menu': [  # categoría, nombre, precio, impuesto %, receta
            ('Platos fuertes', 'Hamburguesa clásica', 24000, 8, [('Carne de res', 180), ('Pan de hamburguesa', 1), ('Queso', 30)]),
            ('Platos fuertes', 'Pollo con arroz', 22000, 8, [('Pollo', 250), ('Arroz', 200)]),
            ('Entradas', 'Papas fritas', 9000, 8, [('Papa', 250)]),
            ('Bebidas', 'Gaseosa', 5000, 0, [('Gaseosa 400ml', 1)]),
            ('Bebidas', 'Jugo natural', 7000, 0, [('Jugo de naranja', 300)]),
            ('Bebidas', 'Cerveza', 8000, 19, [('Cerveza', 1)]),
        ],
        'supplier': ('Distribuidora La Guajira', 'Pedro Gómez', '3000000000'),
    },
    {
        'name': 'Sabor Wayuu', 'suffix': 'sabor', 'email': 'contacto@saborwayuu.test', 'plan': 'Plan Inicial',
        'branches': [('Sede Centro', 'Carrera 7 # 12-45, Riohacha', [('Salón', 6), ('Patio', 4)])],
        'ingredients': [
            ('Chivo', 'g', 12000, 2000, 0.04), ('Carne de res', 'g', 15000, 2000, 0.03), ('Pollo', 'g', 15000, 2000, 0.02),
            ('Arroz', 'g', 25000, 3000, 0.004), ('Yuca', 'g', 20000, 3000, 0.003), ('Plátano verde', 'unit', 120, 20, 700),
            ('Arepa', 'unit', 150, 25, 600), ('Queso costeño', 'g', 6000, 800, 0.03),
            ('Pulpa de fruta', 'ml', 18000, 3000, 0.004), ('Gaseosa 400ml', 'unit', 120, 24, 1800),
        ],
        'menu': [
            ('Platos típicos', 'Chivo guisado', 32000, 8, [('Chivo', 250), ('Arroz', 180), ('Yuca', 150)]),
            ('Platos típicos', 'Carne asada', 29000, 8, [('Carne de res', 280), ('Yuca', 150)]),
            ('Platos típicos', 'Pollo a la brasa', 24000, 8, [('Pollo', 300), ('Arroz', 180)]),
            ('Entradas', 'Arepa con queso', 8000, 8, [('Arepa', 1), ('Queso costeño', 60)]),
            ('Entradas', 'Patacón', 9000, 8, [('Plátano verde', 2)]),
            ('Bebidas', 'Jugo de frutas', 7000, 0, [('Pulpa de fruta', 300)]),
            ('Bebidas', 'Gaseosa', 5000, 0, [('Gaseosa 400ml', 1)]),
        ],
        'supplier': ('Carnes y Víveres del Cesar', 'Marta Pérez', '3010000000'),
    },
    {
        'name': 'Pizzería Don Luigi', 'suffix': 'luigi', 'email': 'hola@donluigi.test', 'plan': 'Plan Empresarial',
        'branches': [
            ('Sede Centro', 'Calle 10 # 8-30, Valledupar', [('Salón', 6), ('Terraza', 4)]),
            ('Sede Norte', 'Avenida Simón Bolívar # 20-15, Valledupar', [('Salón', 3)]),
        ],
        'ingredients': [
            ('Masa de pizza', 'unit', 150, 25, 1500), ('Salsa de tomate', 'ml', 15000, 2000, 0.005),
            ('Queso mozzarella', 'g', 12000, 1500, 0.03), ('Pepperoni', 'g', 6000, 800, 0.05),
            ('Jamón', 'g', 6000, 800, 0.035), ('Piña', 'g', 5000, 600, 0.008), ('Pasta', 'g', 15000, 2000, 0.006),
            ('Carne molida', 'g', 10000, 1500, 0.028), ('Gaseosa 400ml', 'unit', 120, 24, 1800), ('Cerveza', 'unit', 100, 24, 2500),
        ],
        'menu': [
            ('Pizzas', 'Pizza margarita', 28000, 8, [('Masa de pizza', 1), ('Salsa de tomate', 80), ('Queso mozzarella', 150)]),
            ('Pizzas', 'Pizza pepperoni', 34000, 8, [('Masa de pizza', 1), ('Salsa de tomate', 80), ('Queso mozzarella', 150), ('Pepperoni', 80)]),
            ('Pizzas', 'Pizza hawaiana', 33000, 8, [('Masa de pizza', 1), ('Salsa de tomate', 80), ('Queso mozzarella', 150), ('Jamón', 70), ('Piña', 60)]),
            ('Pastas', 'Pasta boloñesa', 26000, 8, [('Pasta', 200), ('Carne molida', 120), ('Salsa de tomate', 100)]),
            ('Bebidas', 'Gaseosa', 5000, 0, [('Gaseosa 400ml', 1)]),
            ('Bebidas', 'Cerveza', 8000, 19, [('Cerveza', 1)]),
        ],
        'supplier': ('Importadora Italia Sur', 'Giovanni Rossi', '3020000000'),
    },
]


class Command(BaseCommand):
    help = 'Carga datos de demostración de Bemba POS (3 restaurantes con personal, ventas y movimientos).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Elimina los datos demo existentes antes de crearlos.')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend')  # no enviar correos al cargar datos
    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self._reset()

        plans = {}
        for name, price, branches, users in PLANS:
            plans[name], _ = SubscriptionPlan.objects.get_or_create(
                name=name, defaults={'monthly_price': Decimal(price), 'max_branches': branches, 'max_users': users},
            )

        summary = []
        for index, spec in enumerate(RESTAURANTS):
            summary.append(self._seed_restaurant(spec, plans[spec['plan']], random.Random(2026 + index)))

        superuser, created = User.objects.get_or_create(
            username=SUPERUSER,
            defaults={'role': 'admin', 'first_name': 'Super', 'last_name': 'Administrador', 'email': 'super@bemba.test',
                      'is_staff': True, 'is_superuser': True},
        )
        if created:
            superuser.set_password(DEMO_PASSWORD)
            superuser.save()

        self.stdout.write(self.style.SUCCESS('Datos de demostración listos.'))
        self.stdout.write(f'Contraseña de todos los usuarios: {DEMO_PASSWORD}')
        self.stdout.write(f'  - {SUPERUSER:20s} superusuario (crea y administra restaurantes)')
        for restaurant, usernames in summary:
            self.stdout.write(f'  {restaurant}')
            for username, role in usernames:
                self.stdout.write(f'    - {username:20s} {role}')

    # ------------------------------------------------------------------ restaurante
    def _seed_restaurant(self, spec, plan, rng):
        restaurant, created = RestaurantAccount.objects.get_or_create(
            business_name=spec['name'],
            defaults={'plan': plan, 'email': spec['email'], 'status': RestaurantAccount.Status.ACTIVE,
                      'phone': '3000000000', 'subscription_started_at': timezone.localdate()},
        )
        main_branch = None
        tables = []
        for branch_name, address, zones in spec['branches']:
            branch, _ = Branch.objects.get_or_create(restaurant=restaurant, name=branch_name, defaults={'address': address})
            main_branch = main_branch or branch
            for zone_name, count in zones:
                zone, _ = Zone.objects.get_or_create(branch=branch, name=zone_name)
                for number in range(1, count + 1):
                    table, _ = DiningTable.objects.get_or_create(zone=zone, number=str(number), defaults={'seats': 4})
                    if branch == main_branch:
                        tables.append(table)

        users = {}
        for key, role, first, last in STAFF:
            username = f'{key}_{spec["suffix"]}'
            user, user_created = User.objects.get_or_create(
                username=username,
                defaults={'role': role, 'first_name': first, 'last_name': last, 'email': f'{username}@bemba.test',
                          'restaurant': restaurant, 'branch': main_branch},
            )
            if user_created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            users[key] = user

        ingredients = {}
        for name, unit, stock, minimum, cost in spec['ingredients']:
            ingredients[name], _ = Ingredient.objects.get_or_create(
                restaurant=restaurant, name=name,
                defaults={'unit': unit, 'current_stock': Decimal(stock), 'min_stock': Decimal(minimum), 'unit_cost': Decimal(str(cost))},
            )

        menu_items = []
        for category_name, name, price, tax, recipe in spec['menu']:
            category, _ = Category.objects.get_or_create(restaurant=restaurant, name=category_name)
            item, item_created = MenuItem.objects.get_or_create(
                restaurant=restaurant, name=name,
                defaults={'category': category, 'price': Decimal(price), 'tax_rate': Decimal(tax)},
            )
            if item_created:
                for ingredient_name, quantity in recipe:
                    RecipeItem.objects.create(menu_item=item, ingredient=ingredients[ingredient_name], quantity=Decimal(quantity))
            menu_items.append(item)

        supplier_name, contact, phone = spec['supplier']
        Supplier.objects.get_or_create(restaurant=restaurant, name=supplier_name, defaults={'contact_name': contact, 'phone': phone})

        if not Order.objects.filter(restaurant=restaurant).exists():
            ctx = {'restaurant': restaurant, 'branch': main_branch, 'tables': tables, 'users': users,
                   'menu': menu_items, 'ingredients': ingredients, 'supplier': Supplier.objects.get(restaurant=restaurant)}
            self._history(ctx, rng)
            self._live_state(ctx, rng)

        return restaurant.business_name, [(u.username, u.get_role_display()) for u in users.values()]

    # ------------------------------------------------------------------ ventas de la última semana
    def _history(self, ctx, rng, days=7):
        now = timezone.now()
        waiters = [ctx['users']['mesero'], ctx['users']['mesero2']]
        cashier = ctx['users']['cajero']
        for days_ago in range(days, -1, -1):
            for _ in range(rng.randint(3, 6) if days_ago else rng.randint(2, 4)):
                moment = now - timedelta(days=days_ago, hours=rng.randint(0, 5), minutes=rng.randint(0, 59))
                if moment > now:
                    moment = now - timedelta(minutes=rng.randint(5, 90))
                order = Order.objects.create(
                    restaurant=ctx['restaurant'], branch=ctx['branch'], table=rng.choice(ctx['tables']),
                    waiter=rng.choice(waiters), status=Order.Status.PAID, inventory_consumed=True,
                )
                for item in rng.sample(ctx['menu'], k=rng.randint(1, min(3, len(ctx['menu'])))):
                    OrderItem.objects.create(
                        order=order, menu_item=item, quantity=rng.randint(1, 3),
                        unit_price=item.price, tax_rate=item.tax_rate, sent_to_kitchen=True,
                    )
                order.recalculate()
                method = rng.choice(['cash', 'cash', 'card', 'transfer'])
                received = order.total + Decimal(rng.choice([0, 1000, 2000, 5000])) if method == 'cash' else order.total
                payment = Payment.objects.create(order=order, method=method, amount=order.total, received=received, cashier=cashier)
                closed = moment + timedelta(minutes=rng.randint(25, 70))
                Order.objects.filter(pk=order.pk).update(created_at=moment, closed_at=closed)
                Payment.objects.filter(pk=payment.pk).update(created_at=closed)

    # ------------------------------------------------------------------ estado "vivo" para probar cocina, mesas y solicitudes
    def _live_state(self, ctx, rng):
        tables, users, menu = ctx['tables'], ctx['users'], ctx['menu']
        waiter = users['mesero']

        def live_order(table, status, ticket_status, picks):
            order = Order.objects.create(
                restaurant=ctx['restaurant'], branch=ctx['branch'], table=table, waiter=waiter,
                status=status, notes='Pedido de ejemplo',
            )
            for item, qty in picks:
                OrderItem.objects.create(order=order, menu_item=item, quantity=qty, unit_price=item.price,
                                         tax_rate=item.tax_rate, sent_to_kitchen=True)
            order.recalculate()
            KitchenTicket.objects.create(order=order, status=ticket_status)
            table.status = DiningTable.Status.OCCUPIED
            table.save(update_fields=['status'])
            if status in (Order.Status.PREPARING, Order.Status.READY):
                consume_order_inventory(order)
            return order

        pick = lambda n: [(menu[i % len(menu)], 1 + i % 2) for i in range(n, n + 2)]
        live_order(tables[0], Order.Status.SENT, KitchenTicket.Status.PENDING, pick(0))
        live_order(tables[1], Order.Status.PREPARING, KitchenTicket.Status.PREPARING, pick(1))
        live_order(tables[2], Order.Status.READY, KitchenTicket.Status.READY, pick(2))

        tables[3].status = DiningTable.Status.PENDING          # alguien escaneó el QR y aún no pide
        tables[3].save(update_fields=['status'])
        tables[4].status = DiningTable.Status.CLEANING         # recién pagada, en limpieza
        tables[4].save(update_fields=['status'])

        customer_order = CustomerOrder.objects.create(
            restaurant=ctx['restaurant'], table=tables[5], note='Sin cebolla, por favor')
        for item, qty in pick(3):
            CustomerOrderItem.objects.create(customer_order=customer_order, menu_item=item, quantity=qty)
        tables[5].status = DiningTable.Status.PENDING
        tables[5].save(update_fields=['status'])

        TableRequest.objects.create(table=tables[1], kind=TableRequest.Kind.WAITER)
        TableRequest.objects.create(table=tables[2], kind=TableRequest.Kind.BILL)

        # Un ingrediente en stock bajo con su alerta, para probar inventario.
        low = next(iter(ctx['ingredients'].values()))
        low.current_stock = low.min_stock - Decimal('1')
        low.save(update_fields=['current_stock'])
        StockAlert.objects.get_or_create(
            ingredient=low, resolved=False, defaults={
                'restaurant': ctx['restaurant'], 'created_by': users['gerente'],
                'message': f'Stock bajo: {low.current_stock} {low.unit} (mínimo: {low.min_stock})',
            })

    # ------------------------------------------------------------------ reinicio
    def _reset(self):
        names = [spec['name'] for spec in RESTAURANTS]
        for restaurant in RestaurantAccount.objects.filter(business_name__in=names):
            Payment.objects.filter(restaurant=restaurant).delete()
            KitchenTicket.objects.filter(order__restaurant=restaurant).delete()
            CustomerOrder.objects.filter(restaurant=restaurant).delete()
            Order.objects.filter(restaurant=restaurant).delete()
            StockAlert.objects.filter(restaurant=restaurant).delete()
            StockMovement.objects.filter(ingredient__restaurant=restaurant).delete()
            PurchaseOrder.objects.filter(restaurant=restaurant).delete()
            MenuItem.objects.filter(restaurant=restaurant).delete()
            Ingredient.objects.filter(restaurant=restaurant).delete()
            Category.objects.filter(restaurant=restaurant).delete()
            Supplier.objects.filter(restaurant=restaurant).delete()
            User.objects.filter(restaurant=restaurant).delete()
            DiningTable.objects.filter(zone__branch__restaurant=restaurant).delete()
            Zone.objects.filter(branch__restaurant=restaurant).delete()
            Branch.objects.filter(restaurant=restaurant).delete()
            restaurant.delete()
