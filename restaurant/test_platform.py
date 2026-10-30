from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bemba.test_utils import PASSWORD, api_as, make_restaurant
from restaurant.models import Branch, DiningTable, RestaurantAccount, SubscriptionPlan


class PlatformTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.super = User.objects.create_superuser(username='root', password=PASSWORD, email='r@r.com')
        self.plan = SubscriptionPlan.objects.first()

    def payload(self, **extra):
        data = {
            'business_name': 'Café del Parque', 'email': 'cafe@test.com', 'phone': '3001112233', 'plan': self.plan.id,
            'table_count': 4, 'admin_username': 'admin_cafe', 'admin_first_name': 'Cecilia', 'admin_last_name': 'Mora',
            'admin_password': 'Clave-Muy-Segura-9',
        }
        data.update(extra)
        return data

    def test_only_superuser_can_open_platform_pages(self):
        for user, expected in ((self.super, 200), (self.a['users']['admin'], 403), (self.a['users']['manager'], 403), (self.a['users']['waiter'], 403)):
            self.client.force_login(user)
            for name in ('platform_restaurants', 'platform_restaurant_create'):
                self.assertEqual(self.client.get(reverse(name)).status_code, expected, f'{user.username} {name}')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('platform_restaurants')).status_code, 302)

    def test_superuser_lands_on_platform_after_login(self):
        r = self.client.post(reverse('login'), {'username': 'root', 'password': PASSWORD}, follow=True)
        self.assertEqual(r.redirect_chain[-1][0], reverse('platform_restaurants'))

    def test_create_restaurant_builds_branch_zone_tables_and_admin(self):
        self.client.force_login(self.super)
        r = self.client.post(reverse('platform_restaurant_create'), self.payload())
        restaurant = RestaurantAccount.objects.get(business_name='Café del Parque')
        self.assertRedirects(r, f"{reverse('platform_restaurants')}?creado={restaurant.pk}")
        self.assertEqual(restaurant.status, 'active')
        branch = Branch.objects.get(restaurant=restaurant)
        self.assertEqual(DiningTable.objects.filter(zone__branch=branch).count(), 4)
        tokens = list(DiningTable.objects.filter(zone__branch=branch).values_list('qr_token', flat=True))
        self.assertEqual(len(set(tokens)), 4)
        admin = User.objects.get(username='admin_cafe')
        self.assertEqual((admin.role, admin.restaurant, admin.branch), ('admin', restaurant, branch))
        self.assertContains(self.client.get(f"{reverse('platform_restaurants')}?creado={restaurant.pk}"), 'admin_cafe')

    def test_new_restaurant_admin_can_log_in_and_sees_only_own_data(self):
        self.client.force_login(self.super)
        self.client.post(reverse('platform_restaurant_create'), self.payload())
        self.client.logout()
        r = self.client.post(reverse('login'), {'username': 'admin_cafe', 'password': 'Clave-Muy-Segura-9'}, follow=True)
        self.assertEqual(r.redirect_chain[-1][0], reverse('dashboard'))
        self.assertEqual(self.client.get(reverse('tables')).context['tables'].count(), 4)
        self.assertEqual(api_as(User.objects.get(username='admin_cafe')).get('/api/orders/').data['count'], 0)
        self.assertEqual(self.client.get(reverse('platform_restaurants')).status_code, 403)

    def test_invalid_data_creates_nothing(self):
        self.client.force_login(self.super)
        bad = [
            self.payload(admin_username='admin_a'),               # usuario repetido
            self.payload(business_name='restaurante a'),          # nombre repetido (sin importar mayúsculas)
            self.payload(admin_password='123'),                   # contraseña débil
            self.payload(table_count=0), self.payload(table_count=500),
            self.payload(email='no-es-correo'),
        ]
        for data in bad:
            r = self.client.post(reverse('platform_restaurant_create'), data)
            self.assertEqual(r.status_code, 400, data)
        self.assertFalse(RestaurantAccount.objects.filter(business_name='Café del Parque').exists())
        self.assertEqual(RestaurantAccount.objects.count(), 1)

    def test_suspended_restaurant_blocks_staff_login_and_public_menu_until_reactivated(self):
        self.client.force_login(self.super)
        self.client.post(reverse('platform_restaurant_status', args=[self.a['restaurant'].id]), {'status': 'suspended'})
        self.client.logout()
        r = self.client.post(reverse('login'), {'username': 'waiter_a', 'password': PASSWORD})
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.post('/api/auth/token/', {'username': 'waiter_a', 'password': PASSWORD}).status_code, 401)
        self.assertEqual(self.client.get(reverse('public_menu', args=[self.a['tables'][0].qr_token])).status_code, 404)

        self.client.force_login(self.super)
        self.client.post(reverse('platform_restaurant_status', args=[self.a['restaurant'].id]), {'status': 'active'})
        self.client.logout()
        self.client.post(reverse('login'), {'username': 'waiter_a', 'password': PASSWORD})
        self.assertIn('_auth_user_id', self.client.session)

    def test_status_change_requires_superuser_post_and_valid_value(self):
        url = reverse('platform_restaurant_status', args=[self.a['restaurant'].id])
        self.client.force_login(self.a['users']['admin'])
        self.assertEqual(self.client.post(url, {'status': 'suspended'}).status_code, 403)
        self.client.force_login(self.super)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'status': 'cancelled-por-error'}).status_code, 400)
        self.a['restaurant'].refresh_from_db()
        self.assertEqual(self.a['restaurant'].status, 'active')


class SeedDemoTests(TestCase):
    def run_seed(self, *args):
        call_command('seed_demo', *args, stdout=open('/dev/null', 'w'))

    def test_seed_creates_three_restaurants_with_staff_sales_and_live_state(self):
        from sales.models import CustomerOrder, Order, Payment
        from restaurant.models import TableRequest
        self.run_seed()
        self.assertEqual(RestaurantAccount.objects.filter(status='active').count(), 3)
        for restaurant in RestaurantAccount.objects.all():
            roles = set(restaurant.users.values_list('role', flat=True))
            self.assertEqual(roles, {'admin', 'manager', 'cashier', 'waiter', 'chef'})
            self.assertGreaterEqual(restaurant.users.filter(role='waiter').count(), 2)
            self.assertGreater(Payment.objects.filter(restaurant=restaurant).count(), 20)
            statuses = set(Order.objects.filter(restaurant=restaurant).values_list('status', flat=True))
            self.assertTrue({'paid', 'sent', 'preparing', 'ready'} <= statuses)
            self.assertTrue(CustomerOrder.objects.filter(restaurant=restaurant, status='pending').exists())
        self.assertTrue(TableRequest.objects.exists())
        self.assertTrue(User.objects.get(username='superadmin_demo').is_superuser)

    def test_every_demo_user_can_log_in_and_land_on_its_panel(self):
        self.run_seed()
        landing = {'admin': 'dashboard', 'manager': 'dashboard', 'cashier': 'cashier_panel', 'waiter': 'waiter_panel', 'chef': 'kitchen'}
        for user in User.objects.exclude(is_superuser=True):
            self.client.logout()
            r = self.client.post(reverse('login'), {'username': user.username, 'password': 'Bemba2026*'}, follow=True)
            self.assertEqual(r.redirect_chain[-1][0], reverse(landing[user.role]), user.username)
            self.assertEqual(r.status_code, 200, user.username)

    def test_demo_restaurants_are_isolated_and_dashboards_have_data(self):
        self.run_seed()
        self.client.post(reverse('login'), {'username': 'gerente_sabor', 'password': 'Bemba2026*'})
        orders = api_as(User.objects.get(username='gerente_sabor')).get('/api/orders/').data
        from sales.models import Order
        self.assertEqual(orders['count'], Order.objects.filter(restaurant__business_name='Sabor Wayuu').count())
        page = self.client.get(reverse('dashboard'))
        self.assertEqual(page.status_code, 200)
        self.assertGreater(page.context['sales_today'], 0)
        self.assertEqual(self.client.get(reverse('kitchen')).status_code, 200)
        self.assertEqual(self.client.get(reverse('reports')).status_code, 200)

    def test_seed_is_idempotent_and_reset_recreates(self):
        from sales.models import Order
        self.run_seed()
        counts = (User.objects.count(), Order.objects.count(), RestaurantAccount.objects.count())
        self.run_seed()
        self.assertEqual((User.objects.count(), Order.objects.count(), RestaurantAccount.objects.count()), counts)
        self.run_seed('--reset')
        self.assertEqual((User.objects.count(), RestaurantAccount.objects.count()), (counts[0], counts[2]))
        self.assertGreater(Order.objects.count(), 90)

    def test_seed_does_not_touch_restaurants_created_by_users(self):
        from restaurant.models import SubscriptionPlan
        own = RestaurantAccount.objects.create(plan=SubscriptionPlan.objects.create(name='X'), business_name='Mi Restaurante', email='m@m.com')
        self.run_seed('--reset')
        self.assertTrue(RestaurantAccount.objects.filter(pk=own.pk).exists())
