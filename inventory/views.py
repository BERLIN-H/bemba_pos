from decimal import Decimal, InvalidOperation
from PIL import Image, UnidentifiedImageError

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db import models, transaction

from accounts.permissions import restaurant_module_required, role_required
from inventory.forms import PurchaseOrderForm, SupplierForm
from inventory.models import (
    Category,
    Ingredient,
    RecipeItem,
    MenuItem,
    StockMovement,
    StockAlert,
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
)
from restaurant.tenancy import scoped_queryset


def _valid_menu_image(upload):
    if not upload:
        return True
    if upload.size > 5 * 1024 * 1024:
        return False
    try:
        image = Image.open(upload)
        if image.format not in ('PNG', 'JPEG', 'WEBP'):
            return False
        image.verify()
        upload.seek(0)
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
def inventory(request):
    ingredients = scoped_queryset(Ingredient.objects.all(), request.user)
    menu_items = scoped_queryset(MenuItem.objects.all(), request.user)
    movements = scoped_queryset(StockMovement.objects.all(), request.user)
    sale_movements = scoped_queryset(StockMovement.objects.filter(movement_type=StockMovement.Type.SALE), request.user)
    alerts = scoped_queryset(StockAlert.objects.filter(resolved=False), request.user).select_related('ingredient')
    low_stock_items = ingredients.filter(current_stock__lte=models.F('min_stock'))
    return render(request, 'inventory/index.html', {
        'ingredients': ingredients,
        'menu_items': menu_items.select_related('category'),
        'movements': movements.select_related('ingredient', 'created_by')[:10],
        'sale_movements_count': sale_movements.count(),
        'alerts': alerts,
        'low_stock_items': low_stock_items,
    })


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
def menu_management(request):
    """Permite que cada restaurante administre sus categorías, productos y recetas."""
    from django.shortcuts import redirect

    categories = scoped_queryset(Category.objects.all(), request.user)
    ingredients = scoped_queryset(Ingredient.objects.filter(is_active=True), request.user)
    items = scoped_queryset(MenuItem.objects.all(), request.user).select_related('category').prefetch_related('recipe__ingredient')
    error = ''
    editing_item = items.filter(pk=request.GET.get('editar') or None).first()
    if request.method == 'POST':
        action = request.POST.get('action')
        restaurant = getattr(request.user, 'restaurant', None)
        if action == 'payment':
            if restaurant:
                restaurant.payment_instructions = request.POST.get('payment_instructions', '').strip()
                restaurant.payment_qr_url = request.POST.get('payment_qr_url', '').strip()
                restaurant.save(update_fields=['payment_instructions', 'payment_qr_url'])
                return redirect('inventory_menu')
            error = 'Tu usuario no tiene un restaurante asociado.'
        elif action == 'category':
            name = request.POST.get('category_name', '').strip()
            if name and restaurant:
                Category.objects.get_or_create(restaurant=restaurant, name=name, defaults={'color': request.POST.get('color') or '#0f766e'})
                return redirect('inventory_menu')
            error = 'Escribe un nombre de categoría válido.'
        elif action in ('product', 'product_edit'):
            image_upload = request.FILES.get('image')
            if image_upload and not _valid_menu_image(image_upload):
                error = 'La imagen no es válida o supera el límite de 5 MB. Usa PNG, JPG o WEBP.'
            category = categories.filter(pk=request.POST.get('category_id') or None).first()
            name = request.POST.get('name', '').strip()
            try:
                price = Decimal(request.POST.get('price') or '0')
            except InvalidOperation:
                price = Decimal('-1')
            recipe_rows = []
            for ingredient in ingredients:
                raw = request.POST.get(f'recipe_qty_{ingredient.pk}', '').strip()
                if not raw:
                    continue
                try:
                    quantity = Decimal(raw)
                except InvalidOperation:
                    error = f'La cantidad para {ingredient.name} no es válida.'
                    break
                if quantity < 0:
                    error = f'La cantidad para {ingredient.name} no puede ser negativa.'
                    break
                if quantity > 0:
                    recipe_rows.append((ingredient, quantity))
            if not error and (not category or not name or price < 0):
                error = 'Verifica la categoría, el nombre y el precio del producto.'
            if not error and action == 'product_edit':
                product = items.filter(pk=request.POST.get('product_id') or None).first()
                if not product:
                    error = 'No se encontró el producto de este restaurante.'
                else:
                    with transaction.atomic():
                        product.category = category
                        product.name = name
                        product.description = request.POST.get('description', '').strip()
                        product.price = price
                        product.is_available = request.POST.get('is_available') == 'on'
                        if image_upload:
                            product.image = image_upload
                            product.image_url = ''
                        product.save()
                        product.recipe.all().delete()
                        RecipeItem.objects.bulk_create([RecipeItem(menu_item=product, ingredient=ingredient, quantity=quantity) for ingredient, quantity in recipe_rows])
                    return redirect('inventory_menu')
            elif not error:
                with transaction.atomic():
                    product = MenuItem.objects.create(
                        restaurant=restaurant or category.restaurant, category=category, name=name,
                        description=request.POST.get('description', '').strip(), price=price,
                        is_available=request.POST.get('is_available') == 'on', image=image_upload,
                    )
                    RecipeItem.objects.bulk_create([RecipeItem(menu_item=product, ingredient=ingredient, quantity=quantity) for ingredient, quantity in recipe_rows])
                return redirect('inventory_menu')
            if action == 'product_edit':
                editing_item = items.filter(pk=request.POST.get('product_id') or None).first()
        elif action in ('product_archive', 'product_restore'):
            product = items.filter(pk=request.POST.get('product_id') or None).first()
            if product:
                product.is_available = action == 'product_restore'
                product.save(update_fields=['is_available'])
                return redirect('inventory_menu')
    recipe_by_ingredient = {row.ingredient_id: row.quantity for row in editing_item.recipe.all()} if editing_item else {}
    return render(request, 'inventory/menu.html', {
        'categories': categories, 'ingredients': ingredients, 'menu_items': items, 'error': error,
        'restaurant': getattr(request.user, 'restaurant', None), 'editing_item': editing_item,
        'recipe_by_ingredient': recipe_by_ingredient,
    })


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
def alerts(request):
    alerts_qs = scoped_queryset(StockAlert.objects.filter(resolved=False).select_related('ingredient'), request.user)
    return render(request, 'inventory/alerts.html', {
        'alerts': alerts_qs,
    })


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
@require_POST
def alert_action(request):
    action = request.POST.get('action')
    alert = get_object_or_404(scoped_queryset(StockAlert.objects.select_related('ingredient'), request.user), pk=request.POST.get('alert_id'))

    if action == 'resolve':
        alert.resolved = True
        alert.save(update_fields=['resolved'])
        return JsonResponse({'ok': True, 'resolved': True})

    if action == 'create_po':
        try:
            item_quantity = Decimal(request.POST.get('quantity') or '0')
        except InvalidOperation:
            item_quantity = Decimal('0')
        if item_quantity <= 0:
            return JsonResponse({'ok': False, 'error': 'La cantidad debe ser mayor que cero.'}, status=400)
        supplier = get_object_or_404(scoped_queryset(Supplier.objects.all(), request.user), pk=request.POST.get('supplier_id'))

        po = PurchaseOrder.objects.create(
            restaurant=alert.restaurant,
            supplier=supplier,
            branch=alert.restaurant.branches.first() if alert.restaurant else None,
            created_by=request.user,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            ingredient=alert.ingredient,
            quantity=item_quantity,
            unit_cost=0,
        )
        po.update_total()
        return JsonResponse({'ok': True, 'purchase_order_id': po.id})

    return JsonResponse({'ok': False, 'error': 'Acción desconocida'}, status=400)


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
def suppliers(request):
    suppliers_qs = scoped_queryset(Supplier.objects.all(), request.user)
    form = SupplierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        supplier = form.save(commit=False)
        supplier.restaurant = getattr(request.user, 'restaurant', None)
        supplier.save()
        return HttpResponseRedirect(reverse('inventory_suppliers'))

    return render(request, 'inventory/suppliers.html', {
        'suppliers': suppliers_qs,
        'form': form,
    })


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
def purchase_orders(request):
    orders = scoped_queryset(PurchaseOrder.objects.select_related('supplier', 'branch'), request.user)
    return render(request, 'inventory/purchase_orders.html', {
        'orders': orders,
    })


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
def purchase_order_create(request):
    form = PurchaseOrderForm(request.POST or None, user=request.user)
    ingredients = scoped_queryset(Ingredient.objects.all(), request.user)
    error = None
    if request.method == 'POST' and form.is_valid():
        supplier = form.cleaned_data['supplier']
        branch = form.cleaned_data['branch']
        notes = form.cleaned_data['notes']
        ingredient = ingredients.filter(pk=request.POST.get('ingredient') or None).first()
        try:
            quantity = Decimal(request.POST.get('quantity') or '0')
            unit_cost = Decimal(request.POST.get('unit_cost') or '0')
        except InvalidOperation:
            quantity = unit_cost = Decimal('0')

        if ingredient is None:
            error = 'Selecciona un ingrediente válido.'
        elif quantity <= 0:
            error = 'La cantidad debe ser mayor que cero.'
        elif unit_cost < 0:
            error = 'El costo unitario no puede ser negativo.'
        else:
            po = PurchaseOrder.objects.create(
                restaurant=supplier.restaurant or getattr(request.user, 'restaurant', None),
                supplier=supplier,
                branch=branch,
                notes=notes,
                created_by=request.user,
            )
            PurchaseOrderItem.objects.create(
                purchase_order=po,
                ingredient=ingredient,
                quantity=quantity,
                unit_cost=unit_cost,
            )
            po.update_total()
            return HttpResponseRedirect(reverse('inventory_purchase_order_detail', args=[po.id]))

    return render(request, 'inventory/purchase_order_form.html', {
        'form': form,
        'ingredients': ingredients,
        'error': error,
    }, status=400 if error else 200)


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
def purchase_order_detail(request, pk):
    po = get_object_or_404(scoped_queryset(PurchaseOrder.objects.all(), request.user), pk=pk)
    return render(request, 'inventory/purchase_order_detail.html', {
        'po': po,
    })


@login_required
@restaurant_module_required('inventory')
@role_required('manager')
@require_POST
def receive_purchase_order(request, pk):
    po = get_object_or_404(scoped_queryset(PurchaseOrder.objects.all(), request.user), pk=pk, status=PurchaseOrder.Status.OPEN)
    po.receive()
    return HttpResponseRedirect(reverse('inventory_purchase_order_detail', args=[po.id]))
