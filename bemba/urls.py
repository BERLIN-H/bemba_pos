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
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.api import UserViewSet
from inventory.api import CategoryViewSet, IngredientViewSet, MenuItemViewSet, StockMovementViewSet
from restaurant.api import BranchViewSet, DiningTableViewSet, RestaurantAccountViewSet, SubscriptionPlanViewSet, ZoneViewSet
from restaurant.public import public_order_create, public_request, public_status
from restaurant import platform as p
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
    path('plataforma/', p.platform_dashboard, name='platform_restaurants'),
    path('plataforma/restaurantes/', p.platform_restaurants, name='platform_restaurant_list'),
    path('plataforma/nuevo/', p.platform_restaurant_create, name='platform_restaurant_create'),
    path('plataforma/restaurantes/<int:pk>/editar/', p.platform_restaurant_edit, name='platform_restaurant_edit'),
    path('plataforma/<int:pk>/estado/', p.platform_restaurant_status, name='platform_restaurant_status'),
    path('plataforma/<int:pk>/plan/', p.platform_restaurant_plan, name='platform_restaurant_plan'),
    path('plataforma/sedes/', p.platform_branches, name='platform_branches'),
    path('plataforma/planes/', p.platform_plans, name='platform_plans'),
    path('plataforma/planes/<int:pk>/estado/', p.platform_plan_toggle, name='platform_plan_toggle'),
    path('plataforma/pagos/', p.platform_payments, name='platform_payments'),
    path('plataforma/pagos/crear/', p.platform_payment_create, name='platform_payment_create'),
    path('plataforma/pagos/<int:pk>/estado/', p.platform_payment_status, name='platform_payment_status'),
    path('plataforma/usuarios/', p.platform_users, name='platform_users'),
    path('plataforma/usuarios/<int:pk>/estado/', p.platform_user_status, name='platform_user_status'),
    path('plataforma/usuarios/<int:pk>/rol/', p.platform_user_role, name='platform_user_role'),
    path('plataforma/roles/', p.platform_roles, name='platform_roles'),
    path('plataforma/soporte/', p.platform_support, name='platform_support'),
    path('plataforma/soporte/crear/', p.platform_support_create, name='platform_support_create'),
    path('plataforma/notificaciones/', p.platform_notifications, name='platform_notifications'),
    path('plataforma/configuracion/', p.platform_settings, name='platform_settings'),
    path('plataforma/integraciones/', p.platform_integrations, name='platform_integrations'),
    path('plataforma/integraciones/<int:pk>/estado/', p.platform_integration_toggle, name='platform_integration_toggle'),
    path('plataforma/auditoria/', p.platform_audit, name='platform_audit'),
    path('plataforma/sesiones/', p.platform_sessions, name='platform_sessions'),
    path('plataforma/sesiones/<str:key>/revocar/', p.platform_session_revoke, name='platform_session_revoke'),
    path('plataforma/respaldos/', p.platform_backups, name='platform_backups'),
    path('plataforma/respaldos/crear/', p.platform_backup_create, name='platform_backup_create'),
    path('plataforma/respaldos/<str:filename>/', p.platform_backup_download, name='platform_backup_download'),
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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
