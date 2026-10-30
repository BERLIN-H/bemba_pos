from django.urls import path

from reports.views import reports_home, sales_pdf

urlpatterns = [
    path('', reports_home, name='reports'),
    path('sales.pdf', sales_pdf, name='sales_pdf'),
]
