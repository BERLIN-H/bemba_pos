from django.urls import path

from accounts.views import (
    BembaLoginView, BembaLogoutView, staff_list, staff_create, 
    staff_edit, staff_delete, staff_activate
)

urlpatterns = [
    path('login/', BembaLoginView.as_view(), name='login'),
    path('logout/', BembaLogoutView.as_view(), name='logout'),
    path('staff/', staff_list, name='staff_list'),
    path('staff/nuevo/', staff_create, name='staff_create'),
    path('staff/<int:pk>/editar/', staff_edit, name='staff_edit'),
    path('staff/<int:pk>/eliminar/', staff_delete, name='staff_delete'),
    path('staff/<int:pk>/activar/', staff_activate, name='staff_activate'),
]
