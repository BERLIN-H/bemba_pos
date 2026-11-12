from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('restaurant', '0004_customer_requests')]

    operations = [
        migrations.AddField(
            model_name='restaurantaccount',
            name='payment_instructions',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='restaurantaccount',
            name='payment_qr_url',
            field=models.URLField(blank=True),
        ),
    ]
