from django.db import migrations, models


def preserve_previous_inventory_deductions(apps, schema_editor):
    Order = apps.get_model('sales', 'Order')
    OrderItem = apps.get_model('sales', 'OrderItem')
    consumed_orders = Order.objects.filter(inventory_consumed=True).values_list('pk', flat=True)
    OrderItem.objects.filter(order_id__in=consumed_orders).update(inventory_consumed=True)
    completed_orders = Order.objects.filter(status__in=['served', 'paid', 'cancelled']).values_list('pk', flat=True)
    OrderItem.objects.filter(order_id__in=completed_orders).update(kitchen_delivered=True)


class Migration(migrations.Migration):
    dependencies = [('sales', '0004_customer_requests')]

    operations = [
        migrations.AddField(
            model_name='order',
            name='customer_name',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='order',
            name='customer_document',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='order',
            name='customer_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='inventory_consumed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='kitchen_delivered',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(preserve_previous_inventory_deductions, migrations.RunPython.noop),
    ]
