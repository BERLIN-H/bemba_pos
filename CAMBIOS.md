# Cambios realizados sobre el proyecto original

Se revisó el proyecto, se escribieron pruebas automatizadas y se corrigieron los fallos que estas encontraron.
El proyecto original no tenía ninguna prueba automatizada; ahora hay 139.

## Fallos corregidos

| # | Problema encontrado | Corrección |
|---|---|---|
| 1 | Cocina no podía cambiar el estado de un pedido (error 403), por lo que el flujo "preparando → listo" no funcionaba con el rol cocina | Permiso propio para cocina, limitado a marcar *preparando* o *listo* |
| 2 | Cualquier mesero podía marcar un pedido como *pagado* sin registrar pago, o cancelarlo y borrarlo | Un pedido solo pasa a pagado registrando su pago; borrar queda para administrador/gerente |
| 3 | Meseros y cajeros podían crear, editar y borrar zonas, mesas, planes y restaurantes por la API | Solo lectura para el personal; escritura solo administrador/gerente (planes y restaurantes: superusuario) |
| 4 | Se podía cobrar un valor distinto al total del pedido o un efectivo recibido menor al valor | Se valida que el pago iguale el total y que el efectivo lo cubra |
| 5 | Se podía pagar, ver o usar pedidos, mesas y productos de **otro restaurante** | Aislamiento por restaurante en pedidos, pagos, mesas, productos, ingredientes, usuarios y alertas |
| 6 | Un usuario sin restaurante veía los datos de todos los restaurantes | Ahora no ve nada (solo el superusuario ve todo) |
| 7 | El descuento de inventario podía confundir el pedido #1 con el #12 y dejar de descontar; además podía ejecutarse dos veces y los errores se ocultaban | Marca `inventory_consumed` por pedido (migración 0003); descuento único, con registro de errores |
| 8 | Se aceptaban pedidos sin productos (la mesa quedaba ocupada) | Validación: el pedido debe tener al menos un producto |
| 9 | Un empleado desactivado podía seguir iniciando sesión (web y JWT) | Backend de autenticación que bloquea empleados desactivados |
| 10 | La comanda de cocina nunca cambiaba de estado | La comanda sigue el estado del pedido |
| 11 | Al cancelar un pedido la mesa quedaba ocupada | La mesa se libera si no tiene más pedidos abiertos |
| 12 | Órdenes de compra: error 500 al crear una orden desde una alerta, error 500 con cantidades vacías y acceso a alertas/proveedores de otros restaurantes | Corregido y validado |
| 13 | Un gerente podía crear administradores, usuarios en otro restaurante y editar superusuarios; contraseñas débiles aceptadas | Validaciones de rol, restaurante y contraseña en personal y API |
| 14 | El reporte PDF solo mostraba 35 pagos y el total era parcial | PDF con todas las filas, varias páginas y total real |
| 15 | Nombres de productos con HTML se inyectaban en el POS (XSS) y los errores de la API no se mostraban | Se escapa el HTML y se muestra el motivo del error al usuario |
| 16 | Cantidades, precios y costos negativos o en cero aceptados | Validaciones en menú, recetas y movimientos de stock |
| 17 | Alertas de stock bajo enviaban el correo duplicado | Una sola notificación por alerta |
| 18 | Todos los roles veían el mismo dashboard con las ventas totales | Paneles por rol: dashboard solo para administrador/gerente, panel de caja, panel de mesero y cocina directo al tablero. Al iniciar sesión cada rol llega a su pantalla |

## Funciones nuevas

- **Paneles por rol:** dashboard completo solo para administrador/gerente; panel de caja; panel de mesero; cocina directo a su tablero.
- **Carta digital por QR:** código QR único por mesa (migración `restaurant/0003`), carta pública sin login, página imprimible de QR para administrador/gerente.
- **El cliente pide desde el QR:** pedido con confirmación del mesero (modelos `CustomerOrder`/`TableRequest`, migraciones `restaurant/0004` y `sales/0004`), seguimiento en vivo, llamar al mesero y pedir la cuenta; tablero **Solicitudes** para el personal.
- **Mesa con varios pedidos:** al pagar un pedido la mesa solo pasa a limpieza si no le quedan más pedidos abiertos.
- **Estados de mesa automáticos:** pendiente (al escanear) con vencimiento, ocupada (al pedir), limpieza con paso automático a disponible y botón "Marcar disponible".

## Restaurantes y datos de prueba

- **Creación de restaurantes:** pantalla de superusuario en `/plataforma/` para crear un restaurante (sede, zona, mesas con QR y administrador) y suspenderlo o activarlo. Un restaurante suspendido no puede iniciar sesión ni mostrar su carta.
- **`seed_demo` ampliado:** 3 restaurantes con personal por rol, menú con recetas, inventario, una semana de ventas y estado en vivo; superusuario `superadmin_demo`. Lista de usuarios en `DATOS_DE_PRUEBA.md`.

## Despliegue

- Configuración de producción: `whitenoise` para archivos estáticos, `gunicorn` (`deploy/gunicorn.conf.py`), cookies seguras con `DJANGO_HTTPS`, orígenes CSRF de confianza, conexiones reutilizadas a MySQL y error claro si se usa `DEBUG=False` sin clave secreta.
- `deploy/install.sh`: instalación completa en Ubuntu 24.04, x86 o Arm (MySQL, gunicorn, Caddy con HTTPS, firewall y copia diaria); incluye el ajuste de iptables que necesita Oracle Cloud. `deploy/reset_demo.sh` restablece la demostración.
- `deploy/windows/`: publicación gratuita desde un PC con Windows (waitress + túnel de Cloudflare).
- `DEPLOY.md`: comparación de opciones gratuitas y pasos.

## Mejoras para ejecutar y evaluar

- `python manage.py seed_demo`: restaurante de demostración con un usuario por rol, menú, recetas e inventario.
- `DB_ENGINE=sqlite` en `.env`: el proyecto corre sin instalar MySQL. `requirements-mysql.txt` agrega `mysqlclient` solo si se necesita.
- Se eliminó `create_test_data.py` (no funcionaba: creaba pedidos sin mesa ni mesero); lo reemplaza `seed_demo`.
- README actualizado con instalación, usuarios de demostración, pruebas y reglas de seguridad.
- Se quitó `.env` (credenciales) y `.venv` del paquete.

## Cómo ejecutar las pruebas

```
python manage.py test
```
