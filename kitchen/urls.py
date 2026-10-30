from django.urls import path

from kitchen.views import kitchen_board

urlpatterns = [
    path('', kitchen_board, name='kitchen'),
]
