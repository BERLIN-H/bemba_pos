from django.urls import path

from dashboard.views import cashier_panel, dashboard, home, waiter_panel

urlpatterns = [
    path('', home, name='home'),
    path('panel/', dashboard, name='dashboard'),
    path('panel/caja/', cashier_panel, name='cashier_panel'),
    path('panel/mesero/', waiter_panel, name='waiter_panel'),
]
