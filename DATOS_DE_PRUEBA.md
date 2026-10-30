# Datos de prueba de Bemba POS

Se cargan en la base de datos con un solo comando (se puede repetir sin duplicar nada):

```
python manage.py seed_demo
```

`python manage.py seed_demo --reset` borra los datos de demostración y los recrea desde cero (no toca restaurantes creados a mano). Úsalo para volver al estado inicial después de una ronda de pruebas.

**Contraseña de todos los usuarios:** `Bemba2026*` (si en el servidor se definió otra con `DEMO_PASSWORD` o `SEED_DEMO_PASSWORD`, es esa).

## Usuarios

| Rol | Bemba Demo (hamburguesas) | Sabor Wayuu (comida típica) | Pizzería Don Luigi (2 sedes) |
|---|---|---|---|
| Administrador | `admin_demo` | `admin_sabor` | `admin_luigi` |
| Gerente | `gerente_demo` | `gerente_sabor` | `gerente_luigi` |
| Cajero | `cajero_demo` | `cajero_sabor` | `cajero_luigi` |
| Mesero 1 | `mesero_demo` | `mesero_sabor` | `mesero_luigi` |
| Mesero 2 | `mesero2_demo` | `mesero2_sabor` | `mesero2_luigi` |
| Cocina | `cocina_demo` | `cocina_sabor` | `cocina_luigi` |

**Superusuario de la plataforma:** `superadmin_demo`. Es el único que puede crear y suspender restaurantes (menú **Restaurantes**, `/plataforma/`) y entrar al panel de Django (`/admin/`). En una instalación real, cámbiale la contraseña o elimínalo.

## Qué trae cargado cada restaurante

- Sede(s), zonas y mesas, cada mesa con su código QR (`/restaurant/tables/qr/` con administrador o gerente).
- Menú con categorías, precios, impuestos y **recetas**; inventario con ingredientes, costos y mínimos; un proveedor.
- **Una semana de ventas** (unas 30 ventas pagadas con efectivo, tarjeta y transferencia) para que el dashboard, las gráficas y los reportes tengan información.
- **Estado en vivo:** un pedido en cocina, uno preparando y uno listo; mesas ocupadas, una en limpieza y dos pendientes (alguien escaneó el QR); un **pedido de cliente por confirmar** con nota; llamados de mesa (mesero y cuenta); un ingrediente en **stock bajo** con su alerta.

Los estados temporales vencen solos con el tiempo: la mesa pendiente a los 10 minutos, la limpieza a los 5 y el pedido de cliente sin confirmar a los 15. Los pedidos en cocina no vencen. Para ver otra vez todos los estados, ejecuta `seed_demo --reset`.

## Qué se puede probar con cada usuario

- **Administrador / gerente:** dashboard con ventas y gráficas, reportes en pantalla y en PDF, inventario (movimientos, alertas, proveedores, órdenes de compra), personal (crear, editar y desactivar empleados), códigos QR de las mesas.
- **Mesero:** mapa de mesas, crear un pedido en el POS, enviarlo a cocina, ver sus pedidos abiertos, confirmar o rechazar pedidos de clientes en **Solicitudes**, atender llamados.
- **Cajero:** panel de caja, cobrar pedidos (efectivo, tarjeta, transferencia), ticket, solicitudes de cuenta.
- **Cocina:** tablero de comandas; marcar pedidos como preparando y listo (al preparar se descuenta el inventario según la receta).
- **Cliente (sin usuario):** abrir la carta desde el QR de una mesa, agregar productos, enviar el pedido, llamar al mesero y pedir la cuenta, y ver el avance del pedido.
- **Superusuario:** crear un restaurante nuevo con su administrador, suspenderlo y reactivarlo.

## Aislamiento entre restaurantes

Cada restaurante solo ve sus propios datos. Para comprobarlo, entra con `gerente_sabor` y compara con `gerente_demo`: tienen menús, mesas, ventas e inventario distintos.
