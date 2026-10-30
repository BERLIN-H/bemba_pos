import django.utils.timezone
from django.db import migrations, models

import restaurant.models


def fill_tokens(apps, schema_editor):
    DiningTable = apps.get_model('restaurant', 'DiningTable')
    for table in DiningTable.objects.filter(qr_token__isnull=True):
        table.qr_token = restaurant.models.generate_qr_token()
        table.save(update_fields=['qr_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('restaurant', '0002_subscriptionplan_alter_zone_name_restaurantaccount_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='diningtable',
            name='qr_token',
            field=models.CharField(max_length=40, null=True, editable=False),
        ),
        migrations.AddField(
            model_name='diningtable',
            name='status_changed_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='diningtable',
            name='qr_token',
            field=models.CharField(default=restaurant.models.generate_qr_token, editable=False, max_length=40, unique=True),
        ),
        migrations.AlterField(
            model_name='diningtable',
            name='status',
            field=models.CharField(choices=[('available', 'Disponible'), ('pending', 'Pendiente'), ('occupied', 'Ocupada'), ('reserved', 'Reservada'), ('cleaning', 'Limpieza')], default='available', max_length=20),
        ),
    ]
