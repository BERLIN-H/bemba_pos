from django.urls import path

from restaurant.views import table_qr_svg, table_release, tables, tables_qr

urlpatterns = [
    path('tables/', tables, name='tables'),
    path('tables/qr/', tables_qr, name='tables_qr'),
    path('tables/<int:pk>/qr.svg', table_qr_svg, name='table_qr_svg'),
    path('tables/<int:pk>/liberar/', table_release, name='table_release'),
]
