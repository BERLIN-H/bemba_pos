"""
URL configuration for bemba project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.api import UserViewSet
from inventory.api import CategoryViewSet, IngredientViewSet, MenuItemViewSet, StockMovementViewSet
from restaurant.api import BranchViewSet, DiningTableViewSet, RestaurantAccountViewSet, SubscriptionPlanViewSet, ZoneViewSet
from restaurant.public import public_order_create, public_request, public_status
from restaurant.platform import platform_restaurant_create, platform_restaurant_status, platform_restaurants
from restaurant.views import public_menu
from sales.api import OrderViewSet, PaymentViewSet

router = DefaultRouter()
router.register('users', UserViewSet)
router.register('plans', SubscriptionPlanViewSet)
router.register('restaurants', RestaurantAccountViewSet)
router.register('branches', BranchViewSet)
router.register('zones', ZoneViewSet)
router.register('tables', DiningTableViewSet)
router.register('categories', CategoryViewSet)
router.register('ingredients', IngredientViewSet)
router.register('menu-items', MenuItemViewSet)
router.register('stock-movements', StockMovementViewSet)
router.register('orders', OrderViewSet)
router.register('payments', PaymentViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('plataforma/', platform_restaurants, name='platform_restaurants'),
    path('plataforma/nuevo/', platform_restaurant_create, name='platform_restaurant_create'),
    path('plataforma/<int:pk>/estado/', platform_restaurant_status, name='platform_restaurant_status'),
    path('m/<str:token>/', public_menu, name='public_menu'),
    path('m/<str:token>/pedido/', public_order_create, name='public_order'),
    path('m/<str:token>/llamado/', public_request, name='public_request'),
    path('m/<str:token>/estado/', public_status, name='public_status'),
    path('', include('dashboard.urls')),
    path('accounts/', include('accounts.urls')),
    path('restaurant/', include('restaurant.urls')),
    path('pos/', include('sales.urls')),
    path('kitchen/', include('kitchen.urls')),
    path('inventory/', include('inventory.urls')),
    path('reports/', include('reports.urls')),
    path('api/', include(router.urls)),
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
