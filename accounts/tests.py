from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bemba.test_utils import PASSWORD, api_as, make_restaurant


class LoginTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')

    def test_login_page_loads(self):
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)

    def test_login_sends_each_role_to_its_own_panel(self):
        expected = {
            'admin': 'dashboard', 'manager': 'dashboard', 'cashier': 'cashier_panel',
            'waiter': 'waiter_panel', 'chef': 'kitchen',
        }
        for role, panel in expected.items():
            self.client.logout()
            r = self.client.post(reverse('login'), {'username': f'{role}_a', 'password': PASSWORD}, follow=True)
            self.assertEqual(r.redirect_chain[-1][0], reverse(panel), role)
            self.assertEqual(r.status_code, 200, role)

    def test_wrong_password_is_rejected(self):
        r = self.client.post(reverse('login'), {'username': 'waiter_a', 'password': 'incorrecta'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Credenciales inválidas')

    def test_protected_pages_redirect_anonymous_users_to_login(self):
        for name in ('home', 'dashboard', 'pos', 'kitchen', 'inventory', 'reports', 'tables'):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn('/accounts/login/', r['Location'], name)

    def test_deactivated_employee_cannot_login(self):
        User.objects.filter(username='waiter_a').update(is_active_employee=False)
        r = self.client.post(reverse('login'), {'username': 'waiter_a', 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_deactivated_employee_cannot_get_jwt(self):
        User.objects.filter(username='waiter_a').update(is_active_employee=False)
        r = self.client.post('/api/auth/token/', {'username': 'waiter_a', 'password': PASSWORD})
        self.assertEqual(r.status_code, 401)

    def test_jwt_token_flow(self):
        r = self.client.post('/api/auth/token/', {'username': 'waiter_a', 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        token = r.json()['access']
        r = self.client.get('/api/orders/', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/orders/').status_code, 403)


class RoleAccessMatrixTests(TestCase):
    """Cada rol entra solo a los módulos que le corresponden."""

    EXPECTED = {
        #            pos  kitchen inventory reports staff
        'admin':   (200, 200, 200, 200, 200),
        'manager': (200, 200, 200, 200, 200),
        'cashier': (200, 403, 403, 403, 403),
        'waiter':  (200, 403, 403, 403, 403),
        'chef':    (403, 200, 403, 403, 403),
    }
    URLS = ('pos', 'kitchen', 'inventory', 'reports', 'staff_list')

    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')

    def test_matrix(self):
        for role, expected in self.EXPECTED.items():
            self.client.force_login(self.a['users'][role])
            for url_name, status in zip(self.URLS, expected):
                r = self.client.get(reverse(url_name))
                self.assertEqual(r.status_code, status, f'{role} -> {url_name}')

    def test_full_dashboard_with_sales_is_only_for_admin_and_manager(self):
        for role, user in self.a['users'].items():
            self.client.force_login(user)
            expected = 200 if role in ('admin', 'manager') else 403
            self.assertEqual(self.client.get(reverse('dashboard')).status_code, expected, role)

    def test_role_panels_are_not_shared(self):
        panels = {'cashier_panel': 'cashier', 'waiter_panel': 'waiter'}
        for url_name, owner in panels.items():
            for role, user in self.a['users'].items():
                self.client.force_login(user)
                expected = 200 if role == owner else 403
                self.assertEqual(self.client.get(reverse(url_name)).status_code, expected, f'{role} -> {url_name}')

    def test_waiter_and_chef_never_see_sales_figures(self):
        for role in ('waiter', 'chef', 'cashier'):
            self.client.force_login(self.a['users'][role])
            for url_name in ('home',):
                r = self.client.get(reverse(url_name), follow=True)
                self.assertNotContains(r, 'Ticket promedio', msg_prefix=role)
                self.assertNotContains(r, 'Ventas registradas', msg_prefix=role)

    def test_non_managers_cannot_use_users_api(self):
        for role in ('cashier', 'waiter', 'chef'):
            self.assertEqual(api_as(self.a['users'][role]).get('/api/users/').status_code, 403, role)


class StaffManagementTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')

    def _create(self, **extra):
        data = {'username': 'nuevo', 'password': 'Clave-Segura-123', 'role': 'waiter', 'first_name': 'N', 'last_name': 'U', 'email': 'n@u.com'}
        data.update(extra)
        return self.client.post(reverse('staff_create'), data)

    def test_manager_creates_employee_in_own_restaurant(self):
        self.client.force_login(self.a['users']['manager'])
        r = self._create()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(User.objects.get(username='nuevo').restaurant, self.a['restaurant'])

    def test_duplicate_username_is_rejected(self):
        self.client.force_login(self.a['users']['manager'])
        r = self._create(username='waiter_a')
        self.assertContains(r, 'ya existe')

    def test_weak_password_is_rejected(self):
        self.client.force_login(self.a['users']['manager'])
        r = self._create(password='123')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='nuevo').exists())

    def test_manager_cannot_create_admin(self):
        self.client.force_login(self.a['users']['manager'])
        r = self._create(role='admin')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='nuevo').exists())

    def test_manager_cannot_edit_employee_of_other_restaurant(self):
        self.client.force_login(self.a['users']['manager'])
        other = self.b['users']['waiter']
        r = self.client.post(reverse('staff_edit', args=[other.pk]), {'first_name': 'Hack'})
        self.assertEqual(r.status_code, 404)

    def test_deactivate_and_reactivate_employee(self):
        self.client.force_login(self.a['users']['manager'])
        waiter = self.a['users']['waiter']
        self.client.post(reverse('staff_delete', args=[waiter.pk]))
        waiter.refresh_from_db()
        self.assertFalse(waiter.is_active_employee)
        self.client.post(reverse('staff_activate', args=[waiter.pk]))
        waiter.refresh_from_db()
        self.assertTrue(waiter.is_active_employee)

    def test_manager_cannot_deactivate_self(self):
        self.client.force_login(self.a['users']['manager'])
        me = self.a['users']['manager']
        self.client.post(reverse('staff_delete', args=[me.pk]))
        me.refresh_from_db()
        self.assertTrue(me.is_active_employee)

    def test_api_manager_cannot_create_user_in_other_restaurant_or_as_admin(self):
        c = api_as(self.a['users']['manager'])
        r = c.post('/api/users/', {'username': 'x1', 'password': 'Clave-Segura-123', 'role': 'waiter', 'restaurant': self.b['restaurant'].id}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(User.objects.get(username='x1').restaurant, self.a['restaurant'])
        r = c.post('/api/users/', {'username': 'x2', 'password': 'Clave-Segura-123', 'role': 'admin'}, format='json')
        self.assertEqual(r.status_code, 400)
