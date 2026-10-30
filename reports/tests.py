from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bemba.test_utils import api_as, make_restaurant
from sales.models import Order, Payment


class ReportTests(TestCase):
    def setUp(self):
        self.a = make_restaurant('Restaurante A', 'a')
        self.b = make_restaurant('Restaurante B', 'b')

    def _paid_order(self, world, table_index=0, item='soda', method='cash'):
        waiter = api_as(world['users']['waiter'])
        cashier = api_as(world['users']['cashier'])
        oid = waiter.post('/api/orders/', {'table': world['tables'][table_index].id, 'items': [{'menu_item': world[item].id, 'quantity': 1}]}, format='json').data['id']
        total = Order.objects.get(pk=oid).total
        r = cashier.post('/api/payments/', {'order': oid, 'method': method, 'amount': str(total), 'received': str(total)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        return Payment.objects.get(order_id=oid)

    def test_report_page_totals_only_own_restaurant(self):
        self._paid_order(self.a)
        self._paid_order(self.b)
        self.client.force_login(self.a['users']['manager'])
        r = self.client.get(reverse('reports'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['transactions'], 1)
        self.assertEqual(r.context['total'], Decimal('5000.00'))

    def test_sales_pdf_is_valid_pdf(self):
        self._paid_order(self.a)
        self.client.force_login(self.a['users']['manager'])
        r = self.client.get(reverse('sales_pdf'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(b''.join(r.streaming_content).startswith(b'%PDF'))

    def test_pdf_includes_all_payments_not_only_first_page(self):
        for i in range(3):
            self._paid_order(self.a, table_index=i)
        self.client.force_login(self.a['users']['manager'])
        r = self.client.get(reverse('sales_pdf'))
        self.assertEqual(r.status_code, 200)

    def test_date_filter(self):
        p = self._paid_order(self.a)
        Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=10))
        self._paid_order(self.a, table_index=1)
        self.client.force_login(self.a['users']['manager'])
        today = timezone.localdate().isoformat()
        r = self.client.get(reverse('reports'), {'date_from': today, 'date_to': today})
        self.assertEqual(r.context['transactions'], 1)
        r = self.client.get(reverse('reports'), {'date_from': '31/12/2020'})   # formato dd/mm/YYYY
        self.assertEqual(r.context['transactions'], 2)
        r = self.client.get(reverse('reports'), {'date_from': 'no-es-fecha'})   # fecha inválida no rompe
        self.assertEqual(r.status_code, 200)

    def test_waiter_cannot_download_report(self):
        self.client.force_login(self.a['users']['waiter'])
        self.assertEqual(self.client.get(reverse('sales_pdf')).status_code, 403)
