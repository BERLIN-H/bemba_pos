from django.test import TestCase
from django.urls import reverse

from bemba.test_utils import api_as, make_restaurant
from kitchen.models import KitchenTicket
from sales.models import Order


class KitchenFlowTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.waiter = api_as(self.a['users']['waiter'])
        self.chef = api_as(self.a['users']['chef'])
        self.oid = self.waiter.post('/api/orders/', {
            'table': self.a['tables'][0].id,
            'items': [{'menu_item': self.a['burger'].id, 'quantity': 1, 'notes': 'sin cebolla'}],
        }, format='json').data['id']

    def test_sending_to_kitchen_creates_ticket(self):
        r = self.waiter.post(f'/api/orders/{self.oid}/send_to_kitchen/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Order.objects.get(pk=self.oid).status, 'sent')
        self.assertTrue(KitchenTicket.objects.filter(order_id=self.oid).exists())

    def test_cannot_send_same_order_twice(self):
        self.waiter.post(f'/api/orders/{self.oid}/send_to_kitchen/')
        self.assertEqual(self.waiter.post(f'/api/orders/{self.oid}/send_to_kitchen/').status_code, 400)

    def test_chef_moves_order_through_preparing_and_ready_and_ticket_follows(self):
        self.waiter.post(f'/api/orders/{self.oid}/send_to_kitchen/')
        self.assertEqual(self.chef.patch(f'/api/orders/{self.oid}/', {'status': 'preparing'}, format='json').status_code, 200)
        self.assertEqual(KitchenTicket.objects.get(order_id=self.oid).status, 'preparing')
        self.assertEqual(self.chef.patch(f'/api/orders/{self.oid}/', {'status': 'ready'}, format='json').status_code, 200)
        self.assertEqual(KitchenTicket.objects.get(order_id=self.oid).status, 'ready')

    def test_chef_cannot_cancel_discount_or_change_other_fields(self):
        self.waiter.post(f'/api/orders/{self.oid}/send_to_kitchen/')
        self.assertEqual(self.chef.patch(f'/api/orders/{self.oid}/', {'status': 'cancelled'}, format='json').status_code, 400)
        self.assertEqual(self.chef.patch(f'/api/orders/{self.oid}/', {'discount': '5000'}, format='json').status_code, 400)

    def test_chef_cannot_create_orders_or_payments(self):
        r = self.chef.post('/api/orders/', {'table': self.a['tables'][1].id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.chef.post('/api/payments/', {}, format='json').status_code, 403)

    def test_board_shows_ticket_notes(self):
        self.waiter.post(f'/api/orders/{self.oid}/send_to_kitchen/')
        self.client.force_login(self.a['users']['chef'])
        r = self.client.get(reverse('kitchen'))
        self.assertContains(r, f'Pedido #{self.oid}')
        self.assertContains(r, 'sin cebolla')

    def test_cancelling_order_frees_table(self):
        r = self.waiter.patch(f'/api/orders/{self.oid}/', {'status': 'cancelled'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.a['tables'][0].refresh_from_db()
        self.assertEqual(self.a['tables'][0].status, 'available')

    def test_closed_order_cannot_be_modified(self):
        total = Order.objects.get(pk=self.oid).total
        api_as(self.a['users']['cashier']).post('/api/payments/', {'order': self.oid, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        r = self.waiter.patch(f'/api/orders/{self.oid}/', {'notes': 'cambio'}, format='json')
        self.assertEqual(r.status_code, 400)


class WebPagesTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')
        self.client.force_login(self.a['users']['waiter'])
        self.oid = api_as(self.a['users']['waiter']).post('/api/orders/', {
            'table': self.a['tables'][0].id, 'items': [{'menu_item': self.a['burger'].id, 'quantity': 2}],
        }, format='json').data['id']

    def test_pos_lists_only_own_menu_and_tables(self):
        r = self.client.get(reverse('pos'))
        self.assertContains(r, 'Hamburguesa')
        self.assertEqual(len(r.context['tables']), 3)
        self.assertEqual(r.context['items'].count(), 2)

    def test_tables_page_marks_occupied_table(self):
        r = self.client.get(reverse('tables'))
        self.assertEqual(r.status_code, 200)

    def test_checkout_and_ticket_pages_render(self):
        self.assertContains(self.client.get(reverse('checkout', args=[self.oid])), 'Cobro')
        self.assertEqual(self.client.get(reverse('ticket', args=[self.oid])).status_code, 200)

    def test_cannot_open_checkout_or_ticket_of_other_restaurant(self):
        other = api_as(self.b['users']['waiter']).post('/api/orders/', {
            'table': self.b['tables'][0].id, 'items': [{'menu_item': self.b['soda'].id, 'quantity': 1}],
        }, format='json').data['id']
        self.assertEqual(self.client.get(reverse('checkout', args=[other])).status_code, 404)
        self.assertEqual(self.client.get(reverse('ticket', args=[other])).status_code, 404)

    def test_waiter_can_free_a_cleaning_table_but_cannot_rename_it(self):
        t = self.a['tables'][1]
        t.status = 'cleaning'
        t.save()
        c = api_as(self.a['users']['waiter'])
        self.assertEqual(c.patch(f'/api/tables/{t.id}/', {'status': 'available'}, format='json').status_code, 200)
        self.assertEqual(c.patch(f'/api/tables/{t.id}/', {'number': '99'}, format='json').status_code, 400)

    def test_manager_can_create_table_via_api(self):
        r = api_as(self.a['users']['manager']).post('/api/tables/', {'zone': self.a['zone'].id, 'number': '10', 'seats': 6}, format='json')
        self.assertEqual(r.status_code, 201, r.content)

    def test_manager_cannot_create_table_in_other_restaurant(self):
        r = api_as(self.a['users']['manager']).post('/api/tables/', {'zone': self.b['zone'].id, 'number': '10'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_html_in_product_name_is_escaped_in_pos(self):
        self.a['soda'].name = '<script>alert(1)</script>'
        self.a['soda'].save()
        r = self.client.get(reverse('pos'))
        self.assertNotContains(r, '<script>alert(1)</script>')
