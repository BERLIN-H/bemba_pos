from django.db import migrations, models


def migrate_admin_roles(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    database = schema_editor.connection.alias
    User.objects.using(database).filter(role='admin', is_superuser=False).update(role='manager')
    User.objects.using(database).filter(is_superuser=True).update(role='platform_admin')
    User.objects.using(database).filter(role='platform_admin', is_superuser=False).update(role='manager')


class Migration(migrations.Migration):
    dependencies = [('accounts', '0002_user_branch_user_restaurant')]

    operations = [
        migrations.RunPython(migrate_admin_roles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('platform_admin', 'Administrador de plataforma'),
                    ('manager', 'Gerente'),
                    ('cashier', 'Cajero'),
                    ('waiter', 'Mesero'),
                    ('chef', 'Cocina'),
                ],
                default='waiter',
                max_length=20,
            ),
        ),
    ]
