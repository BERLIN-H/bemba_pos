
#!/usr/bin/env python
import os
import django
import random
import traceback
from datetime import datetime, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bemba.settings")
django.setup()

from sales.models import Payment, Order
from restaurant.models import RestaurantAccount
from accounts.models import User
from django.utils import timezone

try:
    restaurant = RestaurantAccount.objects.first()

    if restaurant is None:
        print("Error: No hay restaurantes registrados en la base de datos.")
        print("Debes crear primero un restaurante.")
    else:
        branch = restaurant.branches.first()
        user = User.objects.filter(role="cashier").first()

        if branch is None:
            print("Error: El restaurante no tiene sucursales registradas.")
        elif user is None:
            print("Error: No hay usuarios con el rol 'cashier'.")
        else:
            created = 0

            for i in range(5):
                date = timezone.make_aware(
                    datetime(2026, 6, 1) + timedelta(hours=i * 2)
                )
                amount = round(random.uniform(10000, 100000), 2)

                order = Order.objects.create(
                    restaurant=restaurant,
                    branch=branch,
                    total=amount,
                    status="completed",
                )

                payment = Payment.objects.create(
                    order=order,
                    amount=amount,
                    method=random.choice(["cash", "card", "transfer"]),
                    cashier=user,
                    created_at=date,
                )

                print(f"Creado pago {i + 1}: {date} - ${amount}")
                created += 1

            june_count = Payment.objects.filter(
                created_at__gte=timezone.make_aware(
                    datetime(2026, 6, 1, 0, 0, 0)
                ),
                created_at__lt=timezone.make_aware(
                    datetime(2026, 6, 2, 0, 0, 0)
                ),
            ).count()

            print(f"\nTotal pagos creados: {created}")
            print(f"Total pagos del 1 de junio: {june_count}")
            print(f"Total pagos en BD: {Payment.objects.count()}")

except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
