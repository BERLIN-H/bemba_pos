# Propuesta visual prueba: Cocina y panel suscriptor

## Objetivo
Crear una propuesta visual más acogedora y moderna para el panel del suscriptor, con especial atención a la sección de Cocina y comandas.

La idea es usar colores pastel suaves, contrastes cálidos y una disposición de espacios clara y agradable, manteniendo legibilidad y eficiencia operativa.

---

## Estilo general

- **Paleta principal**
  - Fondo: `#fbf8f5` (cremoso muy suave)
  - Cartas / paneles: `#ffffff`
  - Acento: `#7bc2b2` (verde agua pastel)
  - Texto principal: `#1f2937` (gris oscuro)
  - Texto secundario: `#6b7280` (gris medio)
  - Bordes suaves: `#e8ecef`
  - Resaltado suave: `#f7e8db` o `#f5f1ff`

- **Tipografía**
  - Base: Inter / sistema
  - Cabeceras: peso 700, gran tamaño para jerarquía
  - Texto: mayor interlineado y espaciado entre bloques

- **Espaciado**
  - Generoso, con márgenes amplios entre tarjetas
  - Uso de tarjetas con `border-radius: 18px`
  - Sombras sutiles: `0 12px 32px rgba(24, 42, 67, 0.08)`

---

## Propuesta para Cocina y comandas

### 1. Encabezado de la pantalla

- Título principal: `Cocina y comandas`
- Subtítulo descriptivo: `Gestión rápida de órdenes para el equipo de cocina`
- Un pequeño bloque de estado con tres chips:
  - `Pendientes`
  - `En preparación`
  - `Listas para servir`

Esto ayuda a que el chef tenga contexto inmediato.

### 2. Tablero de pedidos estilo tarjetas

Cada comanda se presenta como una tarjeta clara y jerarquizada:

- Cabecera de tarjeta con:
  - Pedido #
  - Mesa
  - Hora o prioridad
  - Estado actual en un `pill` suave
- Lista de ítems con:
  - cantidad destacada dentro de un círculo pastel
  - nombre del plato en negrita
  - notas ligeras en texto gris
- Pie de tarjeta con botones secundarios:
  - `Marcar en preparación`
  - `Marcar listo`
  - `Cobrar pedido`

### 3. Layout

- Grid de tarjetas con columnas fluidas, por ejemplo:
  - 3 columnas en pantallas grandes
  - 2 columnas en medianas
  - 1 columna en móvil
- Alternar tarjetas con fondos suaves según estado:
  - `Pendiente`: `#f4f7f6`
  - `Preparando`: `#eef9f7`
  - `Listo`: `#f3f6ff`

### 4. Mejoras visuales para comandas

- Añadir una banda lateral de color suave en cada tarjeta para mejorar la lectura rápida.
- Colocar la cantidad como un `badge` redondeado.
- Agrupar los elementos en bloques bien definidos.
- Usar iconografía ligera para estados (por ejemplo, reloj para pendiente, cuchillo para preparando, check para listo).

---

## Propuesta para panel del suscriptor

### 1. Home dashboard

- Tarjetas de métricas con fondo blanco y sombra ligera.
- Secciones bien definidas: `Resumen`, `Mesas`, `Pedidos abiertos`, `Cocina`.
- Uso de microinteracciones: hover suave en cada tarjeta.

### 2. Botones y acciones

- Botones principales con fondo `#7bc2b2` y texto blanco.
- Botones secundarios con borde suave y fondo translúcido.

### 3. Tipos de contenido

- Mapas de mesas más limpios, con estados codificados por colores amigables.
- Lista de pedidos con separación clara y llamadas a la acción visibles.

---

## Cómo avanzar

### Opción 1: Revisar la propuesta
Te paso esta propuesta visual de prueba sin tocar código. Si te gusta, implemento los cambios en el CSS y las plantillas.

### Opción 2: Desechar
Si prefieres otro estilo o no quieres avanzar, cerramos esta prueba y seguimos con otra dirección.

---

## Nota importante

En este entorno no tengo acceso directo a crear un archivo `.fig` de Figma, pero sí puedo convertir esta propuesta en un diseño real dentro del proyecto o traducirla a un prototipo CSS/HTML.

> Dime si quieres que implemente esta propuesta como un mockup en el sistema o si la descartamos.
