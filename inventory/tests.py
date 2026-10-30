from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from bemba.test_utils import api_as, make_restaurant
from inventory.models import Ingredient, PurchaseOrder, StockAlert, StockMovement, Supplier
from sales.models import Order


class InventoryAPITests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')
        self.manager = api_as(self.a['users']['manager'])

    def test_entry_movement_increases_stock(self):
        r = self.manager.post('/api/stock-movements/', {'ingredient': self.a['ingredient'].id, 'movement_type': 'in', 'quantity': '500'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Ingredient.objects.get(pk=self.a['ingredient'].pk).current_stock, Decimal('1500'))

    def test_non_positive_quantity_is_rejected(self):
        for qty in ('0', '-5'):
            r = self.manager.post('/api/stock-movements/', {'ingredient': self.a['ingredient'].id, 'movement_type': 'in', 'quantity': qty}, format='json')
            self.assertEqual(r.status_code, 400, qty)

    def test_cannot_move_stock_of_other_restaurant(self):
        r = self.manager.post('/api/stock-movements/', {'ingredient': self.b['ingredient'].id, 'movement_type': 'in', 'quantity': '5'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_stock_history_cannot_be_deleted(self):
        self.manager.post('/api/stock-movements/', {'ingredient': self.a['ingredient'].id, 'movement_type': 'in', 'quantity': '5'}, format='json')
        mid = StockMovement.objects.latest('id').id
        self.assertEqual(self.manager.delete(f'/api/stock-movements/{mid}/').status_code, 405)

    def test_waiter_cannot_access_inventory_api(self):
        w = api_as(self.a['users']['waiter'])
        self.assertEqual(w.get('/api/ingredients/').status_code, 403)
        self.assertEqual(w.get('/api/menu-items/').status_code, 403)

    def test_create_menu_item_with_recipe(self):
        r = self.manager.post('/api/menu-items/', {
            'category': self.a['category'].id, 'name': 'Combo', 'price': '30000', 'tax_rate': '8',
            'recipe': [{'ingredient': self.a['ingredient'].id, 'quantity': '150'}],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(len(r.data['recipe']), 1)

    def test_menu_item_cannot_use_category_or_ingredient_of_other_restaurant(self):
        r = self.manager.post('/api/menu-items/', {'category': self.b['category'].id, 'name': 'X', 'price': '1'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.manager.post('/api/menu-items/', {
            'category': self.a['category'].id, 'name': 'Y', 'price': '1',
            'recipe': [{'ingredient': self.b['ingredient'].id, 'quantity': '1'}],
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_negative_price_is_rejected(self):
        r = self.manager.post('/api/menu-items/', {'category': self.a['category'].id, 'name': 'Z', 'price': '-1'}, format='json')
        self.assertEqual(r.status_code, 400)


class LowStockAlertTests(TestCase):
    def test_selling_down_to_minimum_creates_one_alert(self):
        a = make_restaurant('Restaurante A', 'a')
        ing = a['ingredient']
        ing.current_stock = Decimal('450')   # mínimo 100; una hamburguesa usa 200
        ing.save()
        waiter, cashier = api_as(a['users']['waiter']), api_as(a['users']['cashier'])
        for table in a['tables'][:2]:
            oid = waiter.post('/api/orders/', {'table': table.id, 'items': [{'menu_item': a['burger'].id, 'quantity': 1}]}, format='json').data['id']
            total = Order.objects.get(pk=oid).total
            cashier.post('/api/payments/', {'order': oid, 'method': 'card', 'amount': str(total)}, format='json')
        self.assertEqual(Ingredient.objects.get(pk=ing.pk).current_stock, Decimal('50'))
        self.assertEqual(StockAlert.objects.filter(ingredient=ing, resolved=False).count(), 1)


class InventoryWebTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')
        self.supplier = Supplier.objects.create(restaurant=self.a['restaurant'], name='Proveedor A')
        self.client.force_login(self.a['users']['manager'])

    def test_all_inventory_pages_render(self):
        for name in ('inventory', 'inventory_alerts', 'inventory_suppliers', 'inventory_purchase_orders', 'inventory_purchase_order_create'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_purchase_order_create_and_receive_increases_stock(self):
        r = self.client.post(reverse('inventory_purchase_order_create'), {
            'supplier': self.supplier.id, 'branch': self.a['branch'].id, 'notes': 'x',
            'ingredient': self.a['ingredient'].id, 'quantity': '300', 'unit_cost': '25',
        })
        self.assertEqual(r.status_code, 302, r.content)
        po = PurchaseOrder.objects.get()
        self.assertEqual(po.total, Decimal('7500'))
        self.client.post(reverse('inventory_purchase_order_receive', args=[po.id]))
        self.assertEqual(Ingredient.objects.get(pk=self.a['ingredient'].pk).current_stock, Decimal('1300'))
        # recibir dos veces no duplica el stock
        self.client.post(reverse('inventory_purchase_order_receive', args=[po.id]))
        self.assertEqual(Ingredient.objects.get(pk=self.a['ingredient'].pk).current_stock, Decimal('1300'))

    def test_purchase_order_invalid_quantity_does_not_crash(self):
        r = self.client.post(reverse('inventory_purchase_order_create'), {
            'supplier': self.supplier.id, 'branch': self.a['branch'].id,
            'ingredient': self.a['ingredient'].id, 'quantity': '0', 'unit_cost': '25',
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_alert_create_po_works_and_resolve(self):
        alert = StockAlert.objects.create(restaurant=self.a['restaurant'], ingredient=self.a['ingredient'], message='bajo', created_by=self.a['users']['manager'])
        r = self.client.post(reverse('inventory_alert_action'), {'action': 'create_po', 'alert_id': alert.id, 'supplier_id': self.supplier.id, 'quantity': '100'})
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.post(reverse('inventory_alert_action'), {'action': 'resolve', 'alert_id': alert.id})
        self.assertEqual(r.status_code, 200)
        alert.refresh_from_db()
        self.assertTrue(alert.resolved)

    def test_cannot_resolve_alert_of_other_restaurant(self):
        alert = StockAlert.objects.create(restaurant=self.b['restaurant'], ingredient=self.b['ingredient'], message='bajo', created_by=self.b['users']['manager'])
        r = self.client.post(reverse('inventory_alert_action'), {'action': 'resolve', 'alert_id': alert.id})
        self.assertEqual(r.status_code, 404)
