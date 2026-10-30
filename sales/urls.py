from django.urls import path

from sales.views import (
    checkout, customer_order_confirm, customer_order_reject, pos, requests_board, table_request_attend, ticket,
)

urlpatterns = [
    path('', pos, name='pos'),
    path('checkout/<int:pk>/', checkout, name='checkout'),
    path('ticket/<int:pk>/', ticket, name='ticket'),
    path('solicitudes/', requests_board, name='requests_board'),
    path('solicitudes/pedido/<int:pk>/confirmar/', customer_order_confirm, name='customer_order_confirm'),
    path('solicitudes/pedido/<int:pk>/rechazar/', customer_order_reject, name='customer_order_reject'),
    path('solicitudes/llamado/<int:pk>/atender/', table_request_attend, name='table_request_attend'),
]
