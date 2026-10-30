CREATE DATABASE IF NOT EXISTS bemba_pos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'bemba_user'@'localhost' IDENTIFIED BY 'bemba_password';
GRANT ALL PRIVILEGES ON bemba_pos.* TO 'bemba_user'@'localhost';
FLUSH PRIVILEGES;

USE bemba_pos;

-- La estructura final se administra con migraciones Django:
-- python manage.py migrate
--
-- Apps normalizadas:
-- accounts_user: usuarios, roles y autenticación.
-- restaurant_zone / restaurant_diningtable: zonas y mesas.
-- inventory_category / inventory_ingredient / inventory_menuitem / inventory_recipeitem / inventory_stockmovement.
-- sales_order / sales_orderitem / sales_payment.
-- kitchen_kitchenticket.
