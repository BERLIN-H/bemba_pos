from decimal import Decimal

from django.test import TestCase

from bemba.test_utils import api_as, make_restaurant
from inventory.models import Ingredient, StockMovement
from restaurant.models import DiningTable
from sales.models import Order


class POSFlowTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.waiter = api_as(self.a['users']['waiter'])
        self.chef = api_as(self.a['users']['chef'])
        self.cashier = api_as(self.a['users']['cashier'])

    def _create_order(self, qty=2, client=None):
        client = client or self.waiter
        return client.post('/api/orders/', {
            'table': self.a['tables'][0].id,
            'items': [{'menu_item': self.a['burger'].id, 'quantity': qty}],
        }, format='json')

    def test_chef_can_advance_order_status_from_kitchen(self):
        order_id = self._create_order().data['id']
        self.waiter.post(f'/api/orders/{order_id}/send_to_kitchen/')
        r = self.chef.patch(f'/api/orders/{order_id}/', {'status': 'preparing'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def test_waiter_cannot_mark_order_paid_without_payment(self):
        order_id = self._create_order().data['id']
        r = self.waiter.patch(f'/api/orders/{order_id}/', {'status': 'paid'}, format='json')
        self.assertIn(r.status_code, (400, 403))

    def test_waiter_cannot_modify_catalog_of_tables_or_plans(self):
        r = self.waiter.post('/api/zones/', {'branch': self.a['branch'].id, 'name': 'Hack'}, format='json')
        self.assertEqual(r.status_code, 403)
        r = self.waiter.delete(f'/api/tables/{self.a["tables"][1].id}/')
        self.assertEqual(r.status_code, 403)
        r = self.waiter.post('/api/plans/', {'name': 'Gratis', 'monthly_price': 0}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_order_without_items_is_rejected(self):
        r = self.waiter.post('/api/orders/', {'table': self.a['tables'][0].id, 'items': []}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_payment_amount_must_match_order_total(self):
        order_id = self._create_order().data['id']
        total = Order.objects.get(pk=order_id).total
        r = self.cashier.post('/api/payments/', {'order': order_id, 'method': 'cash', 'amount': '1.00', 'received': '1.00'}, format='json')
        self.assertEqual(r.status_code, 400, r.content)
        r = self.cashier.post('/api/payments/', {'order': order_id, 'method': 'cash', 'amount': str(total), 'received': str(total - 1)}, format='json')
        self.assertEqual(r.status_code, 400, r.content)

    def test_inventory_discounted_exactly_once(self):
        order_id = self._create_order(qty=2).data['id']
        self.waiter.post(f'/api/orders/{order_id}/send_to_kitchen/')
        self.chef.patch(f'/api/orders/{order_id}/', {'status': 'preparing'}, format='json')
        total = Order.objects.get(pk=order_id).total
        self.cashier.post('/api/payments/', {'order': order_id, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        ing = Ingredient.objects.get(pk=self.a['ingredient'].pk)
        self.assertEqual(ing.current_stock, Decimal('600'))
        self.assertEqual(StockMovement.objects.filter(ingredient=ing, movement_type='sale').count(), 1)

    def test_inventory_guard_does_not_confuse_order_1_and_12(self):
        """El pedido #1 no debe darse por descontado porque exista un movimiento del #12."""
        o1 = self._create_order(qty=1).data['id']
        StockMovement.objects.create(
            ingredient=self.a['ingredient'], movement_type='sale', quantity=1,
            note=f'Consumo automático pedido #{o1}2', created_by=self.a['users']['waiter'],
        )
        total = Order.objects.get(pk=o1).total
        self.cashier.post('/api/payments/', {'order': o1, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        sales = StockMovement.objects.filter(note=f'Consumo automático pedido #{o1}').count()
        self.assertEqual(sales, 1)

    def test_full_flow_table_states(self):
        table = self.a['tables'][0]
        order_id = self._create_order().data['id']
        table.refresh_from_db()
        self.assertEqual(table.status, DiningTable.Status.OCCUPIED)
        total = Order.objects.get(pk=order_id).total
        r = self.cashier.post('/api/payments/', {'order': order_id, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        table.refresh_from_db()
        self.assertEqual(table.status, DiningTable.Status.CLEANING)
        self.assertEqual(Order.objects.get(pk=order_id).status, 'paid')

    def test_insufficient_stock_blocks_order(self):
        r = self._create_order(qty=10)  # requiere 2000 g y hay 1000
        self.assertEqual(r.status_code, 400)

    def test_totals_include_tax(self):
        order = Order.objects.get(pk=self._create_order(qty=1).data['id'])
        self.assertEqual(order.subtotal, Decimal('20000.00'))
        self.assertEqual(order.tax, Decimal('1600.00'))
        self.assertEqual(order.total, Decimal('21600.00'))


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')

    def test_manager_a_does_not_see_orders_or_users_from_b(self):
        api_as(self.b['users']['waiter']).post('/api/orders/', {
            'table': self.b['tables'][0].id,
            'items': [{'menu_item': self.b['soda'].id, 'quantity': 1}],
        }, format='json')
        c = api_as(self.a['users']['manager'])
        self.assertEqual(c.get('/api/orders/').data['count'], 0)
        usernames = [u['username'] for u in c.get('/api/users/').data['results']]
        self.assertFalse(any(u.endswith('_b') for u in usernames))

    def test_waiter_a_cannot_use_table_or_item_of_b(self):
        r = api_as(self.a['users']['waiter']).post('/api/orders/', {
            'table': self.b['tables'][0].id,
            'items': [{'menu_item': self.b['soda'].id, 'quantity': 1}],
        }, format='json')
        self.assertEqual(r.status_code, 400, r.content)

    def test_cashier_a_cannot_pay_order_of_b(self):
        r = api_as(self.b['users']['waiter']).post('/api/orders/', {
            'table': self.b['tables'][0].id,
            'items': [{'menu_item': self.b['soda'].id, 'quantity': 1}],
        }, format='json')
        order_id = r.data['id']
        p = api_as(self.a['users']['cashier']).post('/api/payments/', {'order': order_id, 'method': 'cash', 'amount': '5000', 'received': '5000'}, format='json')
        self.assertEqual(p.status_code, 400, p.content)

    def test_user_without_restaurant_does_not_see_everything(self):
        from accounts.models import User
        orphan = User.objects.create_user(username='huerfano', password='x12345678', role='manager')
        self.assertEqual(api_as(orphan).get('/api/restaurants/').data['count'], 0)
