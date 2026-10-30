# Bemba POS

Sistema POS para restaurantes construido con Python, Django, Django REST Framework, JWT, Bootstrap, JavaScript y MySQL/SQLite.

## Módulos

- Login y autenticación con usuario personalizado (los empleados desactivados no pueden ingresar, ni por web ni por JWT).
- Roles: administrador, gerente, cajero, mesero y cocina, con permisos por módulo.
- Paneles separados por rol: dashboard completo (administrador/gerente), panel de caja, panel de mesero y tablero de cocina. Cada usuario inicia en su pantalla y no ve cifras que no le corresponden.
- Zonas y mesas con estados (disponible, ocupada, limpieza).
- Punto de venta con ticket visual, cobro y transferencia de mesa.
- Pedidos con estados operativos y comandas de cocina.
- Inventario: ingredientes, recetas, movimientos, alertas de stock bajo, proveedores y órdenes de compra.
- Reportes web y PDF de ventas con filtro por fechas.
- Carta digital por QR en cada mesa, con estados de mesa (pendiente, ocupada, limpieza) que se actualizan solos.
- API REST protegida con JWT y aislamiento de datos por restaurante.

## Inicio rápido (sin instalar MySQL)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # ya viene con DB_ENGINE=sqlite
python manage.py migrate
python manage.py seed_demo      # datos de demostración + un usuario por rol
python manage.py runserver
```

Abrir <http://127.0.0.1:8000/>. `seed_demo` crea **3 restaurantes de prueba** (Bemba Demo, Sabor Wayuu y Pizzería Don Luigi), cada uno con administrador, gerente, cajero, dos meseros y cocina, menú con recetas, inventario, una semana de ventas y un estado en vivo (pedidos en cocina, mesas ocupadas, un pedido de cliente por confirmar). Además crea el superusuario `superadmin_demo`, que crea y suspende restaurantes desde **Restaurantes**.

La lista completa de usuarios y de qué se puede probar con cada uno está en **DATOS_DE_PRUEBA.md**. Contraseña de todos: `Bemba2026*`. Ejemplos:

| Usuario | Rol | Inicio |
|---|---|---|
| `superadmin_demo` | Administrador de la plataforma | Restaurantes (crear, suspender) |
| `admin_demo` / `gerente_demo` | Administrador / gerente | Dashboard con ventas y gráficas |
| `cajero_demo` | Cajero | Panel de caja |
| `mesero_demo` | Mesero | Panel de mesero |
| `cocina_demo` | Cocina | Tablero de comandas |

`python manage.py seed_demo --reset` borra y recrea los datos de demostración.

### Usar MySQL

```powershell
pip install -r requirements-mysql.txt
mysql -u root -p < database.sql
# en .env: DB_ENGINE=mysql y los datos MYSQL_*
python manage.py migrate
python manage.py createsuperuser
```

## Carta digital por QR para el cliente

1. Entra como administrador o gerente a **Mesas → Códigos QR de las mesas** (`/restaurant/tables/qr/`) e imprime el código de cada mesa.
2. El cliente escanea el QR y ve la carta de su restaurante (solo productos disponibles), sin iniciar sesión.
3. Estados de la mesa:

```
Disponible → Pendiente (escanearon el QR) → Ocupada (se hizo un pedido) → Limpieza (se pagó) → Disponible
```

- *Pendiente* vence sola a los `TABLE_PENDING_MINUTES` (10 por defecto) si nadie pide, así nadie puede bloquear mesas por molestar.
- *Limpieza* pasa sola a disponible a los `TABLE_CLEANING_MINUTES` (5 por defecto); el personal también puede usar el botón **Marcar disponible**.
- Para que los celulares abran la carta, define `PUBLIC_BASE_URL` en `.env` con la IP de tu red (por ejemplo `http://192.168.1.20:8000`) o tu dominio. Con `127.0.0.1` solo funciona en el mismo computador; la página de QR lo avisa.
- El código de cada mesa es largo y aleatorio, no el número de mesa, para que no se pueda adivinar la carta de otra mesa.

### Qué puede hacer el cliente desde su celular

- **Pedir:** agrega productos con el botón **+**, escribe una nota para la cocina y envía. El pedido queda *por confirmar*: **no llega a cocina ni descuenta inventario hasta que un mesero lo confirma**. El cliente ve el avance en vivo (esperando confirmación, en cocina, preparando, listo, pagado).
- **Llamar al mesero** y **pedir la cuenta**: un toque; el personal ve el aviso y lo marca como atendido.

### Qué hace el personal

- El menú **Solicitudes** (con contador rojo) muestra los pedidos por confirmar y los llamados de mesa; se actualiza solo. Disponible para administrador, gerente, cajero y mesero.
- **Confirmar** crea el pedido real (a nombre del mesero que confirma) y lo manda directo a cocina; **Rechazar** deja un motivo que el cliente ve.
- En un llamado de *cuenta*, el tablero muestra los pedidos abiertos de la mesa con botón para cobrar.

### Protecciones contra abuso

- Un solo pedido pendiente por mesa, máximo 20 unidades por producto y 25 líneas por pedido.
- El precio siempre sale del menú del restaurante; el cliente no puede enviar precios.
- Se valida el stock al enviar y otra vez al confirmar. Si el pedido no se confirma en `CUSTOMER_ORDER_EXPIRY_MINUTES` (15 por defecto), vence.
- Los envíos públicos exigen token CSRF y solo funcionan sobre la mesa y el restaurante del código.

## Despliegue sin costo

Ver **DEPLOY.md**: las opciones gratuitas revisadas (Oracle Cloud Always Free, tu PC con túnel de Cloudflare y las que se descartaron), sus límites reales, cómo se crean los restaurantes y cómo restablecer la demostración.

## Pruebas automatizadas

```powershell
python manage.py test
```

Cubren el flujo completo (pedido, cocina, pago e inventario), permisos por rol, aislamiento entre restaurantes, autenticación JWT, inventario y compras, reportes/PDF y renderizado de las páginas.

## URLs principales

- Web: `http://127.0.0.1:8000/`
- Login: `http://127.0.0.1:8000/accounts/login/`
- Admin: `http://127.0.0.1:8000/admin/`
- API: `http://127.0.0.1:8000/api/`
- JWT: `POST http://127.0.0.1:8000/api/auth/token/`
- Reporte PDF: `http://127.0.0.1:8000/reports/sales.pdf`

## Arquitectura

- `accounts`: usuarios, roles, permisos y autenticación.
- `restaurant`: restaurantes (SaaS), sucursales, zonas y mesas.
- `inventory`: categorías, productos, ingredientes, recetas, stock, proveedores y compras.
- `sales`: pedidos, detalle, pagos, tickets y consumo automático de inventario.
- `kitchen`: comandas.
- `reports`: reportes HTML/PDF.
- `dashboard`: panel administrativo.

## Flujo operativo

1. El mesero crea el pedido en el POS (mesa y productos). El sistema valida que haya stock suficiente.
2. El pedido se envía a cocina y se genera la comanda.
3. Cocina marca el pedido como *preparando* y luego *listo*. Al pasar a *preparando* se descuenta el inventario según la receta.
4. Caja registra el pago (el valor debe coincidir con el total y el efectivo recibido debe cubrirlo).
5. El pedido queda pagado, la mesa pasa a limpieza y, si el inventario no se había descontado, se descuenta en ese momento. Nunca se descuenta dos veces.

## Reglas de seguridad aplicadas

- Cada usuario solo ve y modifica datos de su restaurante.
- Los pagos y los movimientos de stock son registros históricos: se crean y consultan, no se editan ni se eliminan por la API.
- Un pedido solo pasa a *pagado* registrando su pago; cocina solo puede marcar *preparando* o *listo*.
- Meseros y cajeros no pueden crear ni borrar zonas, mesas, planes ni restaurantes.
- Un gerente no puede crear administradores ni usuarios en otro restaurante.

## Próximos pasos posibles

- Formularios CRUD HTML completos para catálogo (hoy se administra por API y panel admin).
- Impresión térmica ESC/POS.
- WebSockets para cocina en tiempo real.
