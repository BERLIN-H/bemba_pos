from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from bemba.test_utils import api_as, make_restaurant
from sales.models import Order


class RolePanelContentTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')
        self.waiter = api_as(self.a['users']['waiter'])
        self.cashier = api_as(self.a['users']['cashier'])
        self.oid = self.waiter.post('/api/orders/', {
            'table': self.a['tables'][0].id,
            'items': [{'menu_item': self.a['burger'].id, 'quantity': 1}],
        }, format='json').data['id']

    def test_cashier_panel_lists_orders_to_charge_and_own_collections(self):
        self.client.force_login(self.a['users']['cashier'])
        r = self.client.get(reverse('cashier_panel'))
        self.assertContains(r, f'#{self.oid}')
        self.assertEqual(r.context['pending_count'], 1)
        total = Order.objects.get(pk=self.oid).total
        self.cashier.post('/api/payments/', {'order': self.oid, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        r = self.client.get(reverse('cashier_panel'))
        self.assertEqual(r.context['pending_count'], 0)
        self.assertEqual(r.context['collected_total'], total)
        self.assertEqual(r.context['collected_count'], 1)

    def test_cashier_panel_only_counts_own_collections(self):
        total = Order.objects.get(pk=self.oid).total
        api_as(self.a['users']['manager']).post('/api/payments/', {'order': self.oid, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        self.client.force_login(self.a['users']['cashier'])
        r = self.client.get(reverse('cashier_panel'))
        self.assertEqual(r.context['collected_total'], Decimal('0.00'))

    def test_waiter_panel_shows_only_own_open_orders(self):
        other_waiter_order = api_as(self.a['users']['manager']).post('/api/orders/', {
            'table': self.a['tables'][1].id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}],
        }, format='json').data['id']
        self.client.force_login(self.a['users']['waiter'])
        r = self.client.get(reverse('waiter_panel'))
        ids = [o.id for o in r.context['my_open']]
        self.assertIn(self.oid, ids)
        self.assertNotIn(other_waiter_order, ids)

    def test_panels_do_not_leak_other_restaurant(self):
        api_as(self.b['users']['waiter']).post('/api/orders/', {
            'table': self.b['tables'][0].id, 'items': [{'menu_item': self.b['soda'].id, 'quantity': 1}],
        }, format='json')
        self.client.force_login(self.a['users']['cashier'])
        self.assertEqual(self.client.get(reverse('cashier_panel')).context['pending_count'], 1)

    def test_admin_dashboard_still_shows_sales(self):
        self.client.force_login(self.a['users']['admin'])
        self.assertContains(self.client.get(reverse('dashboard')), 'Ticket promedio')
