import json
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from bemba.test_utils import api_as, make_restaurant
from inventory.models import Ingredient, MenuItem
from kitchen.models import KitchenTicket
from restaurant.models import DiningTable, RestaurantAccount, TableRequest
from sales.models import CustomerOrder, Order


class CustomerBase(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')
        self.table = self.a['tables'][0]
        self.token = self.table.qr_token

    def post(self, path, payload, token=None, client=None):
        client = client or self.client
        return client.post(reverse(path, args=[token or self.token]), data=json.dumps(payload), content_type='application/json')

    def order(self, items=None, **extra):
        items = items or [{'menu_item': self.a['soda'].id, 'quantity': 2}]
        return self.post('public_order', {'items': items, **extra})

    def status(self, order_id=None, token=None):
        url = reverse('public_status', args=[token or self.token])
        return self.client.get(url, {'order': order_id} if order_id else {}).json()

    def reload_table(self):
        self.table.refresh_from_db()
        return self.table.status


class PublicOrderTests(CustomerBase):
    def test_order_is_created_pending_and_does_not_reach_kitchen_or_stock(self):
        r = self.order([{'menu_item': self.a['burger'].id, 'quantity': 2, 'notes': 'sin cebolla'}], note='mesa del fondo')
        self.assertEqual(r.status_code, 201, r.content)
        co = CustomerOrder.objects.get()
        self.assertEqual(co.status, 'pending')
        self.assertEqual(co.restaurant, self.a['restaurant'])
        self.assertEqual(co.items.get().notes, 'sin cebolla')
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(KitchenTicket.objects.count(), 0)
        self.assertEqual(Ingredient.objects.get(pk=self.a['ingredient'].pk).current_stock, Decimal('1000'))
        self.assertEqual(self.reload_table(), 'pending')

    def test_csrf_is_enforced_for_public_posts(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post('public_order', {'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, client=strict).status_code, 403)
        self.assertEqual(self.post('public_request', {'kind': 'waiter'}, client=strict).status_code, 403)

    def test_menu_page_sets_csrf_cookie_so_the_page_can_post(self):
        strict = Client(enforce_csrf_checks=True)
        strict.get(reverse('public_menu', args=[self.token]))
        csrf = strict.cookies['csrftoken'].value
        r = strict.post(reverse('public_order', args=[self.token]), data=json.dumps({'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}),
                        content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.status_code, 201, r.content)

    def test_invalid_payloads_are_rejected(self):
        soda = self.a['soda'].id
        bad = [
            {}, {'items': []}, {'items': 'x'}, {'items': ['x']},
            {'items': [{'menu_item': soda, 'quantity': 0}]},
            {'items': [{'menu_item': soda, 'quantity': -3}]},
            {'items': [{'menu_item': soda, 'quantity': 'abc'}]},
            {'items': [{'menu_item': 'abc', 'quantity': 1}]},
            {'items': [{'menu_item': soda, 'quantity': 21}]},
            {'items': [{'menu_item': soda, 'quantity': 15}, {'menu_item': soda, 'quantity': 15}]},   # se suman
            {'items': [{'menu_item': 999999, 'quantity': 1}]},
        ]
        for payload in bad:
            self.assertEqual(self.post('public_order', payload).status_code, 400, payload)
        r = self.client.post(reverse('public_order', args=[self.token]), data='no es json', content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(CustomerOrder.objects.count(), 0)

    def test_cannot_order_products_of_other_restaurant_or_unavailable(self):
        self.assertEqual(self.order([{'menu_item': self.b['soda'].id, 'quantity': 1}]).status_code, 400)
        MenuItem.objects.filter(pk=self.a['soda'].pk).update(is_available=False)
        self.assertEqual(self.order().status_code, 400)
        self.assertEqual(CustomerOrder.objects.count(), 0)

    def test_client_cannot_set_prices(self):
        self.order([{'menu_item': self.a['burger'].id, 'quantity': 1, 'unit_price': 1, 'price': 1}])
        co = CustomerOrder.objects.get()
        co_item = co.items.get()
        self.assertEqual(co_item.menu_item.price, Decimal('20000'))   # el precio siempre sale del menú

    def test_only_one_pending_order_per_table(self):
        self.assertEqual(self.order().status_code, 201)
        r = self.order()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(CustomerOrder.objects.count(), 1)

    def test_stock_shortage_blocks_order_without_leaking_internal_names(self):
        r = self.order([{'menu_item': self.a['burger'].id, 'quantity': 10}])   # 2000 g y hay 1000
        self.assertEqual(r.status_code, 400)
        self.assertNotIn('Carne', r.content.decode())
        self.assertEqual(CustomerOrder.objects.count(), 0)

    def test_pending_order_expires_and_table_can_order_again(self):
        self.order()
        CustomerOrder.objects.update(created_at=timezone.now() - timedelta(minutes=20))
        data = self.status(CustomerOrder.objects.get().id)
        self.assertEqual(data['order']['status'], 'expired')
        self.assertTrue(data['order']['final'])
        self.assertEqual(self.order().status_code, 201)

    def test_endpoints_404_for_unknown_token_and_suspended_restaurant(self):
        self.assertEqual(self.post('public_order', {'items': []}, token='falso').status_code, 404)
        self.assertEqual(self.post('public_request', {'kind': 'waiter'}, token='falso').status_code, 404)
        self.assertEqual(self.client.get(reverse('public_status', args=['falso'])).status_code, 404)
        RestaurantAccount.objects.filter(pk=self.a['restaurant'].pk).update(status='suspended')
        self.assertEqual(self.order().status_code, 404)

    def test_get_not_allowed_on_post_endpoints(self):
        self.assertEqual(self.client.get(reverse('public_order', args=[self.token])).status_code, 405)
        self.assertEqual(self.client.get(reverse('public_request', args=[self.token])).status_code, 405)


class TableRequestTests(CustomerBase):
    def test_call_waiter_and_ask_bill_are_created_once(self):
        for kind in ('waiter', 'bill'):
            self.assertEqual(self.post('public_request', {'kind': kind}).status_code, 200)
            again = self.post('public_request', {'kind': kind}).json()
            self.assertTrue(again['already'])
        self.assertEqual(TableRequest.objects.count(), 2)
        self.assertEqual(self.status()['requests'], {'waiter': True, 'bill': True})
        self.assertEqual(self.reload_table(), 'pending')

    def test_invalid_kind_is_rejected(self):
        for kind in ('', 'pizza', None, 5):
            self.assertEqual(self.post('public_request', {'kind': kind}).status_code, 400)

    def test_staff_attend_clears_the_call_for_the_customer(self):
        self.post('public_request', {'kind': 'waiter'})
        req = TableRequest.objects.get()
        self.client.force_login(self.a['users']['waiter'])
        r = self.client.post(reverse('table_request_attend', args=[req.id]))
        self.assertEqual(r.status_code, 302)
        req.refresh_from_db()
        self.assertIsNotNone(req.attended_at)
        self.assertEqual(req.attended_by, self.a['users']['waiter'])
        self.assertFalse(self.client.get(reverse('public_status', args=[self.token])).json()['requests']['waiter'])

    def test_other_restaurant_cannot_attend_call(self):
        self.post('public_request', {'kind': 'waiter'})
        req = TableRequest.objects.get()
        self.client.force_login(self.b['users']['waiter'])
        self.assertEqual(self.client.post(reverse('table_request_attend', args=[req.id])).status_code, 404)

    def test_bill_call_on_board_links_to_open_orders_for_checkout(self):
        oid = api_as(self.a['users']['waiter']).post('/api/orders/', {'table': self.table.id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, format='json').data['id']
        self.post('public_request', {'kind': 'bill'})
        self.client.force_login(self.a['users']['cashier'])
        r = self.client.get(reverse('requests_board'))
        self.assertContains(r, reverse('checkout', args=[oid]))


class StaffConfirmationTests(CustomerBase):
    def make_pending(self, items=None):
        self.order(items or [{'menu_item': self.a['burger'].id, 'quantity': 2}, {'menu_item': self.a['soda'].id, 'quantity': 1}], note='con prisa')
        return CustomerOrder.objects.latest('id')

    def confirm(self, co, user=None):
        self.client.force_login(user or self.a['users']['waiter'])
        return self.client.post(reverse('customer_order_confirm', args=[co.id]))

    def test_confirm_creates_real_order_in_kitchen_and_occupies_table(self):
        co = self.make_pending()
        waiter = self.a['users']['waiter']
        self.assertEqual(self.confirm(co, waiter).status_code, 302)
        co.refresh_from_db()
        order = co.order
        self.assertEqual(co.status, 'confirmed')
        self.assertEqual(co.resolved_by, waiter)
        self.assertEqual((order.status, order.waiter, order.table), ('sent', waiter, self.table))
        self.assertEqual(order.subtotal, Decimal('45000.00'))      # 2 x 20000 + 5000
        self.assertEqual(order.tax, Decimal('3200.00'))            # 8 % sobre 40000
        self.assertTrue(all(i.sent_to_kitchen for i in order.items.all()))
        self.assertTrue(KitchenTicket.objects.filter(order=order).exists())
        self.assertEqual(self.reload_table(), 'occupied')
        self.assertIn('con prisa', order.notes)

    def test_confirm_twice_does_not_duplicate_orders(self):
        co = self.make_pending()
        self.confirm(co)
        self.assertEqual(self.confirm(co).status_code, 400)
        self.assertEqual(Order.objects.count(), 1)

    def test_confirm_fails_if_stock_ran_out_meanwhile(self):
        co = self.make_pending([{'menu_item': self.a['burger'].id, 'quantity': 4}])    # 800 g de 1000
        Ingredient.objects.filter(pk=self.a['ingredient'].pk).update(current_stock=Decimal('300'))
        r = self.confirm(co)
        self.assertEqual(r.status_code, 400)
        co.refresh_from_db()
        self.assertEqual(co.status, 'pending')
        self.assertEqual(Order.objects.count(), 0)

    def test_confirm_fails_if_product_became_unavailable(self):
        co = self.make_pending()
        MenuItem.objects.filter(pk=self.a['soda'].pk).update(is_available=False)
        self.assertEqual(self.confirm(co).status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_reject_shows_reason_to_customer_and_frees_the_table_to_order_again(self):
        co = self.make_pending()
        self.client.force_login(self.a['users']['cashier'])
        r = self.client.post(reverse('customer_order_reject', args=[co.id]), {'reason': 'Producto agotado'})
        self.assertEqual(r.status_code, 302)
        data = self.status(co.id)
        self.assertEqual(data['order']['status'], 'rejected')
        self.assertIn('Producto agotado', data['order']['label'])
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.order().status_code, 201)

    def test_permissions_and_tenant_isolation(self):
        co = self.make_pending()
        for role, status in (('chef', 403),):
            self.client.force_login(self.a['users'][role])
            self.assertEqual(self.client.post(reverse('customer_order_confirm', args=[co.id])).status_code, status)
        self.assertEqual(self.confirm(co, self.b['users']['waiter']).status_code, 404)
        anon = Client()
        self.assertEqual(anon.post(reverse('customer_order_confirm', args=[co.id])).status_code, 302)
        co.refresh_from_db()
        self.assertEqual(co.status, 'pending')

    def test_confirm_requires_post(self):
        co = self.make_pending()
        self.client.force_login(self.a['users']['waiter'])
        self.assertEqual(self.client.get(reverse('customer_order_confirm', args=[co.id])).status_code, 405)

    def test_board_lists_only_own_restaurant_and_shows_items(self):
        self.make_pending()
        other = self.b['tables'][0]
        self.post('public_order', {'items': [{'menu_item': self.b['soda'].id, 'quantity': 1}]}, token=other.qr_token)
        self.client.force_login(self.a['users']['waiter'])
        r = self.client.get(reverse('requests_board'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['pending']), 1)
        self.assertContains(r, 'Hamburguesa')
        self.assertContains(r, 'con prisa')

    def test_only_pos_staff_see_board(self):
        for role, status in {'admin': 200, 'manager': 200, 'cashier': 200, 'waiter': 200, 'chef': 403}.items():
            self.client.force_login(self.a['users'][role])
            self.assertEqual(self.client.get(reverse('requests_board')).status_code, status, role)

    def test_badge_counts_pending_orders_and_calls(self):
        self.make_pending()
        self.post('public_request', {'kind': 'waiter'})
        self.client.force_login(self.a['users']['waiter'])
        r = self.client.get(reverse('waiter_panel'))
        self.assertEqual(r.context['requests_badge'], 2)
        self.assertContains(r, 'solicitud(es) de clientes')
        self.client.force_login(self.b['users']['waiter'])
        self.assertEqual(self.client.get(reverse('waiter_panel')).context['requests_badge'], 0)


class CustomerJourneyTests(CustomerBase):
    def test_full_journey_scan_order_confirm_cook_pay_clean(self):
        # 1) escanea
        self.client.get(reverse('public_menu', args=[self.token]))
        self.assertEqual(self.reload_table(), 'pending')
        # 2) pide
        co_id = self.order([{'menu_item': self.a['burger'].id, 'quantity': 1}]).json()['id']
        self.assertIn('confirme', self.status(co_id)['order']['label'])
        # 3) el mesero confirma
        co = CustomerOrder.objects.get(pk=co_id)
        waiter_client = Client(); waiter_client.force_login(self.a['users']['waiter'])
        waiter_client.post(reverse('customer_order_confirm', args=[co.id]))
        self.assertEqual(self.reload_table(), 'occupied')
        self.assertIn('cocina', self.status(co_id)['order']['label'])
        # 4) cocina prepara y deja listo
        chef = api_as(self.a['users']['chef'])
        order_id = CustomerOrder.objects.get(pk=co_id).order_id
        chef.patch(f'/api/orders/{order_id}/', {'status': 'preparing'}, format='json')
        self.assertIn('preparando', self.status(co_id)['order']['label'])
        self.assertEqual(Ingredient.objects.get(pk=self.a['ingredient'].pk).current_stock, Decimal('800'))
        chef.patch(f'/api/orders/{order_id}/', {'status': 'ready'}, format='json')
        self.assertIn('listo', self.status(co_id)['order']['label'])
        # 5) pide la cuenta y caja cobra
        self.post('public_request', {'kind': 'bill'})
        total = Order.objects.get(pk=order_id).total
        api_as(self.a['users']['cashier']).post('/api/payments/', {'order': order_id, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        data = self.status(co_id)
        self.assertIn('pagado', data['order']['label'])
        self.assertTrue(data['order']['final'])
        self.assertEqual(self.reload_table(), 'cleaning')
        # 6) limpieza vence sola
        DiningTable.objects.filter(pk=self.table.pk).update(status_changed_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(self.status()['table_status'], 'available')

    def test_status_does_not_reveal_orders_from_other_tables(self):
        other = self.a['tables'][1]
        r = self.post('public_order', {'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, token=other.qr_token)
        other_id = r.json()['id']
        self.assertIsNone(self.status(other_id, token=self.token)['order'])
        self.assertIsNone(self.status('abc')['order'])

    def test_two_orders_on_same_table_keep_it_occupied_until_both_are_paid(self):
        waiter, cashier = api_as(self.a['users']['waiter']), api_as(self.a['users']['cashier'])
        ids = [waiter.post('/api/orders/', {'table': self.table.id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, format='json').data['id'] for _ in range(2)]
        pay = lambda oid: cashier.post('/api/payments/', {'order': oid, 'method': 'cash', 'amount': '5000', 'received': '5000'}, format='json')
        pay(ids[0])
        self.assertEqual(self.reload_table(), 'occupied')
        pay(ids[1])
        self.assertEqual(self.reload_table(), 'cleaning')
