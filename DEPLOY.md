# Cómo dejar Bemba POS disponible para el equipo evaluador (sin pagar)

## Qué elegir

Revisé las opciones gratuitas vigentes a octubre de 2026. Esto es lo que resultó:

| Opción | ¿Gratis de verdad? | ¿Sirve para este proyecto? |
|---|---|---|
| **Oracle Cloud "Always Free"** | Sí, sin vencimiento. Pide tarjeta de crédito o débito solo para verificar la identidad (no se cobra; hace una retención de unos US$1 que se devuelve). | **La mejor para estar disponible las 24 horas.** Servidor propio con Ubuntu, MySQL y IP fija. Detalles abajo. |
| **Tu PC + túnel de Cloudflare** | Sí, sin cuenta ni tarjeta. | **La mejor si no tienes tarjeta o quieres empezar hoy.** El profesor permitió usar un PC como servidor. Solo funciona mientras el PC esté encendido. |
| PythonAnywhere (plan gratis) | Sí | **Descartada.** Las cuentas nuevas ya no incluyen MySQL, el límite diario de CPU es de 100 segundos, no hay SSH y la app expira al mes si no se renueva. No aguanta una prueba de carga. |
| DigitalOcean | No | Ya no es gratis para estudiantes: salió del paquete de GitHub Student el 31 de julio de 2026. Cuesta unos US$24 a 32 al mes. |

**Recomendación:** intenta crear la cuenta de Oracle (puede tardar o fallar por capacidad o por la tarjeta) y, **mientras tanto, deja funcionando la opción del PC** para que el equipo ya pueda probar. Si Oracle sale bien, pasas el mismo proyecto allá y el PC queda libre.

Los datos de prueba (3 restaurantes, usuarios, ventas) se cargan igual en ambas opciones con `python manage.py seed_demo`. La lista de usuarios está en **DATOS_DE_PRUEBA.md**.

## Opción A: tu PC con Windows + túnel gratis de Cloudflare

Ya tienes el proyecto corriendo con MariaDB. Para publicarlo:

1. **Instala las dependencias** (una vez), con el entorno virtual activo:
   ```
   pip install -r requirements.txt
   ```
2. **Instala el túnel** (una vez): `winget install --id Cloudflare.cloudflared` y cierra y abre la terminal.
3. **Carga los datos de prueba** (una vez): `python manage.py migrate` y luego `python manage.py seed_demo`.
4. **Inicia todo** haciendo doble clic en `deploy\windows\iniciar_servidor.bat`. El script prepara el entorno, arranca el servidor de producción (waitress) y abre una segunda ventana con el túnel.
5. En la ventana del túnel aparece una dirección como `https://palabras-al-azar.trycloudflare.com`. **Esa es la dirección que entregas a los evaluadores.**

Lo que debes saber de esta opción:

- **El PC debe estar encendido, con internet y con las dos ventanas abiertas** mientras ellos prueben. Desactiva la suspensión de Windows (Configuración, Sistema, Inicio/apagado y batería, Pantalla y suspensión: poner "Nunca").
- **La dirección cambia cada vez que se reinicia el túnel.** Si apagas el PC o cierras la ventana, hay que avisarles la nueva. Una dirección fija exige un dominio propio (cuesta unos pocos dólares al año); no es gratis.
- **Límite de carga:** Cloudflare corta a 200 peticiones simultáneas en los túneles gratuitos (responde error 429 al exceso), no da garantía de disponibilidad y los considera para pruebas y desarrollo. Con una prueba de estrés de miles de usuarios a la vez habrá errores 429; no es un fallo del sistema. Dilo así al profesor si lo piden.
- Los códigos QR de las mesas toman la dirección con la que abras la página *Códigos QR*. Ábrela usando la dirección del túnel, no `127.0.0.1`, y deja `PUBLIC_BASE_URL` vacío en tu `.env`.
- En esta opción los usuarios de prueba entran a la dirección del túnel; tú puedes seguir usando `http://127.0.0.1:8000` para desarrollar con `runserver`.

## Opción B: Oracle Cloud Always Free (servidor 24/7 gratis)

Qué ofrece: una máquina virtual Arm (VM.Standard.A1.Flex) con su propia IP, hasta 200 GB de disco y 10 TB de transferencia al mes. **Advertencias reales:**

- **Recorte reciente:** la documentación oficial sigue diciendo 4 CPU y 24 GB de RAM, pero varios medios reportan que desde el 15 de junio de 2026 el cupo quedó en 2 CPU y 12 GB. Confírmalo al crear la máquina. Aun así, 2 CPU y 12 GB son suficientes para la evaluación.
- **Puede aparecer "Out of capacity"** al crear la máquina. Suele resolverse reintentando en otro momento u otro dominio de disponibilidad.
- **La región se elige al crear la cuenta y no se puede cambiar.** Elige la más cercana a Colombia que ofrezca la capa gratuita.
- **Tarjeta:** solo acepta crédito o débito físicas o digitales de banco; no acepta tarjetas virtuales ni prepago. Algunas tarjetas colombianas son rechazadas; prueba con otra si falla.
- Oracle puede recuperar máquinas gratuitas **inactivas** (uso de CPU, red y memoria bajo cerca del 20 % durante 7 días). Durante la evaluación esto no debería ocurrir.

Pasos:

1. **Crear la cuenta** en oracle.com/cloud/free (pide teléfono y tarjeta).
2. **Crear la máquina:** menú Compute, Instances, Create instance. Imagen **Ubuntu 24.04**, forma **VM.Standard.A1.Flex** con la etiqueta *Always Free-eligible* (usa el máximo permitido de CPU y RAM), sube o genera tu llave SSH y deja asignada una IP pública. Anota la IP.
3. **Abrir los puertos en la red de Oracle:** en la máquina entra a su subred, luego *Security Lists*, *Add Ingress Rules*: origen `0.0.0.0/0`, protocolo TCP, puertos `80` y `443`. Sin esto no entra nadie, aunque el servidor esté bien.
4. **Subir el proyecto** desde tu PC (PowerShell):
   ```
   scp -i tu_llave.key bemba_pos_mejorado.zip ubuntu@IP_DE_LA_MAQUINA:/home/ubuntu/
   ssh -i tu_llave.key ubuntu@IP_DE_LA_MAQUINA
   ```
5. **En la máquina:**
   ```
   sudo -i
   apt-get update && apt-get install -y unzip
   cd /home/ubuntu && unzip bemba_pos_mejorado.zip && cd bemba_pos
   DEMO_PASSWORD='ClaveParaEvaluadores1!' bash deploy/install.sh
   ```
   Tarda de 5 a 15 minutos (compila algunas librerías en Arm). Al terminar imprime la dirección y la contraseña.
6. Abre `http://IP_DE_LA_MAQUINA` en el navegador y prueba con `superadmin_demo` y los demás usuarios.

HTTPS: con una IP el sitio funciona con HTTP. Para HTTPS necesitas un nombre de dominio apuntando a la IP y ejecutar el instalador con `DOMAIN=tu.dominio.com`. Sin dominio, puedes probar `IP-con-guiones.sslip.io` (por ejemplo `129-146-10-20.sslip.io`) como dominio; no lo probé y depende de los límites de Let's Encrypt.

Operación: `systemctl status bemba caddy` muestra el estado y ambos servicios se reinician solos. Para dejar la demostración como nueva: `bash /opt/bemba_pos/deploy/reset_demo.sh`. El servidor hace una copia diaria de la base de datos en `/var/backups/bemba`.

## Cómo se crean los restaurantes

Los restaurantes los crea el **superusuario de la plataforma** (`superadmin_demo` en los datos de prueba). Al iniciar sesión cae en **Restaurantes** (`/plataforma/`), donde puede:

- **Crear restaurante:** nombre, plan, cantidad de mesas y el usuario administrador. El sistema crea la sede principal, una zona «Salón», las mesas (cada una con su código QR) y el administrador.
- **Suspender o activar** un restaurante. Un restaurante suspendido no puede iniciar sesión ni mostrar su carta pública.

El administrador del restaurante entra con su usuario y crea al resto del personal (gerente, cajero, meseros, cocina) desde **Empleados**.

## Capacidad (medición orientativa)

En una máquina de 1 CPU compartida, con el generador de carga en la misma máquina: unas 95 cargas por segundo de la carta pública, unas 340 de la pantalla de login y unas 8 inicios de sesión completos por segundo. El inicio de sesión es lo más costoso porque Django verifica la contraseña con un algoritmo lento a propósito. Una prueba con miles de inicios de sesión simultáneos saturará el procesador de cualquier máquina gratuita; eso es una limitación de hardware, no del código. Son estimaciones, no garantías.

## Límites que conviene saber

- Probé la aplicación en modo producción (sin debug, con servidor real, archivos estáticos, cookies seguras y protección CSRF). **No pude ejecutar el instalador de Linux ni el túnel en un servidor o PC reales desde aquí**; el script de preparación para Windows sí lo probé. Si algo falla, el mensaje de error indica el paso; pégamelo y lo corrijo.
- Las pruebas automáticas corrieron con SQLite. Con tu MariaDB verificaste que las pantallas cargan; haz un recorrido completo (pedido, cocina, cobro, QR) antes de entregar.
