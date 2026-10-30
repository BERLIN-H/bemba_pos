from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from bemba.test_utils import api_as, make_restaurant
from inventory.models import MenuItem
from restaurant.models import DiningTable, RestaurantAccount
from restaurant.services import release_expired_tables
from sales.models import Order


def age_table(table, minutes):
    DiningTable.objects.filter(pk=table.pk).update(status_changed_at=timezone.now() - timedelta(minutes=minutes))


class PublicMenuTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')
        self.table = self.a['tables'][0]

    def url(self, table=None):
        return reverse('public_menu', args=[(table or self.table).qr_token])

    def test_menu_opens_without_login_and_shows_available_products(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Restaurante A')
        self.assertContains(r, 'Mesa 1')
        self.assertContains(r, 'Hamburguesa')
        self.assertContains(r, 'Gaseosa')

    def test_hides_unavailable_products_and_other_restaurants(self):
        MenuItem.objects.filter(pk=self.a['soda'].pk).update(is_available=False)
        r = self.client.get(self.url())
        self.assertNotContains(r, 'Gaseosa')
        self.assertContains(r, 'Hamburguesa')
        MenuItem.objects.filter(pk=self.b['burger'].pk).update(name='Plato Secreto B')
        self.assertNotContains(self.client.get(self.url()), 'Plato Secreto B')

    def test_does_not_expose_internal_data(self):
        r = self.client.get(self.url())
        self.assertNotContains(r, 'Carne')      # ingrediente de la receta
        self.assertNotContains(r, 'current_stock')
        self.assertNotContains(r, self.a['users']['manager'].username)

    def test_unknown_token_inactive_table_and_suspended_restaurant_give_404(self):
        self.assertEqual(self.client.get(reverse('public_menu', args=['no-existe'])).status_code, 404)
        DiningTable.objects.filter(pk=self.table.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        DiningTable.objects.filter(pk=self.table.pk).update(is_active=True)
        RestaurantAccount.objects.filter(pk=self.a['restaurant'].pk).update(status='suspended')
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_html_in_product_name_is_escaped(self):
        MenuItem.objects.filter(pk=self.a['soda'].pk).update(name='<script>alert(1)</script>')
        self.assertNotContains(self.client.get(self.url()), '<script>alert(1)</script>')

    def test_page_is_not_cached(self):
        r = self.client.get(self.url())
        self.assertIn('no-cache', r['Cache-Control'])

    def test_tokens_are_long_unique_and_not_guessable_from_number(self):
        tokens = set(DiningTable.objects.values_list('qr_token', flat=True))
        self.assertEqual(len(tokens), DiningTable.objects.count())
        self.assertTrue(all(len(t) >= 20 for t in tokens))


class TableStatusLifecycleTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.table = self.a['tables'][0]
        self.waiter = api_as(self.a['users']['waiter'])
        self.cashier = api_as(self.a['users']['cashier'])

    def scan(self):
        return self.client.get(reverse('public_menu', args=[self.table.qr_token]))

    def reload(self):
        self.table.refresh_from_db()
        return self.table.status

    def test_scanning_marks_available_table_as_pending(self):
        self.assertEqual(self.reload(), 'available')
        self.scan()
        self.assertEqual(self.reload(), 'pending')

    def test_scanning_does_not_change_an_occupied_table(self):
        self.waiter.post('/api/orders/', {'table': self.table.id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, format='json')
        self.assertEqual(self.reload(), 'occupied')
        self.scan()
        self.assertEqual(self.reload(), 'occupied')

    def test_ordering_turns_pending_into_occupied(self):
        self.scan()
        self.waiter.post('/api/orders/', {'table': self.table.id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, format='json')
        self.assertEqual(self.reload(), 'occupied')

    def test_pending_expires_if_nobody_orders(self):
        self.scan()
        age_table(self.table, 5)
        release_expired_tables()
        self.assertEqual(self.reload(), 'pending')      # aún no vence
        age_table(self.table, 11)
        release_expired_tables()
        self.assertEqual(self.reload(), 'available')

    def test_full_cycle_available_pending_occupied_cleaning_available(self):
        self.scan()
        self.assertEqual(self.reload(), 'pending')
        oid = self.waiter.post('/api/orders/', {'table': self.table.id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, format='json').data['id']
        self.assertEqual(self.reload(), 'occupied')
        total = Order.objects.get(pk=oid).total
        self.cashier.post('/api/payments/', {'order': oid, 'method': 'cash', 'amount': str(total), 'received': str(total)}, format='json')
        self.assertEqual(self.reload(), 'cleaning')
        age_table(self.table, 3)
        release_expired_tables()
        self.assertEqual(self.reload(), 'cleaning')     # sigue en limpieza
        age_table(self.table, 6)
        release_expired_tables()
        self.assertEqual(self.reload(), 'available')

    def test_expired_states_are_released_when_staff_open_tables_or_api(self):
        self.scan()
        age_table(self.table, 30)
        self.client.force_login(self.a['users']['waiter'])
        self.client.get(reverse('tables'))
        self.assertEqual(self.reload(), 'available')
        self.scan()
        age_table(self.table, 30)
        self.waiter.get('/api/tables/')
        self.assertEqual(self.reload(), 'available')

    @override_settings(TABLE_PENDING_MINUTES=1, TABLE_CLEANING_MINUTES=1)
    def test_times_are_configurable(self):
        self.scan()
        age_table(self.table, 2)
        release_expired_tables()
        self.assertEqual(self.reload(), 'available')

    def test_staff_can_release_pending_or_cleaning_table(self):
        self.client.force_login(self.a['users']['waiter'])
        for state in ('pending', 'cleaning'):
            DiningTable.objects.filter(pk=self.table.pk).update(status=state)
            r = self.client.post(reverse('table_release', args=[self.table.id]))
            self.assertEqual(r.status_code, 302)
            self.assertEqual(self.reload(), 'available')

    def test_cannot_release_table_with_open_order(self):
        self.waiter.post('/api/orders/', {'table': self.table.id, 'items': [{'menu_item': self.a['soda'].id, 'quantity': 1}]}, format='json')
        self.client.force_login(self.a['users']['waiter'])
        r = self.client.post(reverse('table_release', args=[self.table.id]))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.reload(), 'occupied')

    def test_chef_cannot_release_tables(self):
        self.client.force_login(self.a['users']['chef'])
        self.assertEqual(self.client.post(reverse('table_release', args=[self.table.id])).status_code, 403)


class TableQRPagesTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')

    def test_only_admin_and_manager_can_see_qr_pages(self):
        expected = {'admin': 200, 'manager': 200, 'cashier': 403, 'waiter': 403, 'chef': 403}
        for role, status in expected.items():
            self.client.force_login(self.a['users'][role])
            self.assertEqual(self.client.get(reverse('tables_qr')).status_code, status, role)
            self.assertEqual(self.client.get(reverse('table_qr_svg', args=[self.a['tables'][0].id])).status_code, status, role)

    def test_qr_image_is_svg(self):
        self.client.force_login(self.a['users']['manager'])
        r = self.client.get(reverse('table_qr_svg', args=[self.a['tables'][0].id]))
        self.assertEqual(r['Content-Type'], 'image/svg+xml')
        self.assertIn(b'<svg', r.content)

    def test_manager_cannot_get_qr_of_other_restaurant(self):
        self.client.force_login(self.a['users']['manager'])
        self.assertEqual(self.client.get(reverse('table_qr_svg', args=[self.b['tables'][0].id])).status_code, 404)

    def test_qr_page_lists_only_own_tables_with_links_to_public_menu(self):
        self.client.force_login(self.a['users']['manager'])
        r = self.client.get(reverse('tables_qr'))
        self.assertEqual(len(r.context['rows']), 3)
        for row in r.context['rows']:
            self.assertIn(row['table'].qr_token, row['url'])
            self.assertIn('/m/', row['url'])
        self.assertNotContains(r, self.b['tables'][0].qr_token)

    @override_settings(PUBLIC_BASE_URL='http://192.168.1.20:8000')
    def test_qr_uses_public_base_url_and_warns_only_for_local_addresses(self):
        self.client.force_login(self.a['users']['manager'])
        r = self.client.get(reverse('tables_qr'))
        self.assertTrue(all(row['url'].startswith('http://192.168.1.20:8000/m/') for row in r.context['rows']))
        self.assertFalse(r.context['is_local_address'])

    @override_settings(PUBLIC_BASE_URL='')
    def test_warns_when_address_is_localhost(self):
        self.client.force_login(self.a['users']['manager'])
        self.assertTrue(self.client.get(reverse('tables_qr'), HTTP_HOST='127.0.0.1:8000').context['is_local_address'])

    def test_tables_page_shows_pending_and_release_button(self):
        DiningTable.objects.filter(pk=self.a['tables'][0].pk).update(status='pending')
        self.client.force_login(self.a['users']['waiter'])
        r = self.client.get(reverse('tables'))
        self.assertContains(r, 'Pendiente')
        self.assertContains(r, 'Marcar disponible')
