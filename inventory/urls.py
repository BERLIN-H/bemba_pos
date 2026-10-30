from django.urls import path

from inventory.views import (
    alerts,
    alert_action,
    inventory,
    purchase_order_create,
    purchase_order_detail,
    purchase_orders,
    receive_purchase_order,
    suppliers,
)

urlpatterns = [
    path('', inventory, name='inventory'),
    path('alerts/', alerts, name='inventory_alerts'),
    path('alerts/action/', alert_action, name='inventory_alert_action'),
    path('suppliers/', suppliers, name='inventory_suppliers'),
    path('purchase-orders/', purchase_orders, name='inventory_purchase_orders'),
    path('purchase-orders/new/', purchase_order_create, name='inventory_purchase_order_create'),
    path('purchase-orders/<int:pk>/', purchase_order_detail, name='inventory_purchase_order_detail'),
    path('purchase-orders/<int:pk>/receive/', receive_purchase_order, name='inventory_purchase_order_receive'),
]
