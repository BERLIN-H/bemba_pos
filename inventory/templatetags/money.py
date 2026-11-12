from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter
def money(value):
    """Formato de pesos colombianos sin decimales: $200.000."""
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal('0')
    return '$' + f'{amount:,.0f}'.replace(',', '.')


@register.filter
def average_money(value, count):
    try:
        divisor = Decimal(str(count or 0))
        amount = Decimal(str(value or 0)) / divisor if divisor else Decimal('0')
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        amount = Decimal('0')
    return money(amount)
