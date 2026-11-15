from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.permissions import restaurant_module_required, role_required
from kitchen.models import KitchenTicket
from restaurant.tenancy import scoped_queryset


@login_required
@restaurant_module_required('kitchen_kds')
@role_required('manager', 'chef')
def kitchen_board(request):
    tickets = scoped_queryset(
        KitchenTicket.objects.exclude(status=KitchenTicket.Status.DELIVERED)
        .select_related('order__table').prefetch_related('order__items__menu_item'),
        request.user, 'order__restaurant',
    )
    return render(request, 'kitchen/board.html', {'tickets': tickets})

# Create your views here.
