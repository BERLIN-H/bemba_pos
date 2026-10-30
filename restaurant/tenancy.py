def scoped_queryset(queryset, user, lookup='restaurant'):
    """Filtra por el restaurante del usuario.

    - Superusuario: ve todo.
    - Usuario con restaurante: solo ve lo de su restaurante.
    - Usuario sin restaurante (y sin ser superusuario): no ve nada.
    """
    if user.is_superuser:
        return queryset
    if not getattr(user, 'restaurant_id', None):
        return queryset.none()
    return queryset.filter(**{lookup: user.restaurant})


def same_tenant(user, restaurant_id):
    """True si el objeto con ese restaurant_id pertenece al restaurante del usuario."""
    if user.is_superuser:
        return True
    return bool(getattr(user, 'restaurant_id', None)) and user.restaurant_id == restaurant_id
