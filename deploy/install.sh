#!/usr/bin/env bash
# Instala Bemba POS en un servidor Ubuntu 24.04 LTS recién creado, x86 o ARM (MySQL + gunicorn + Caddy).
# Sirve para Oracle Cloud (capa gratuita), DigitalOcean y cualquier VPS con Ubuntu 24.04.
#
# Uso, como root, dentro de la carpeta del proyecto ya copiada al servidor:
#   DEMO_PASSWORD='Clave-Para-Evaluadores-1' DOMAIN=bemba.midominio.com bash deploy/install.sh   # con HTTPS (recomendado)
#   DEMO_PASSWORD='Clave-Para-Evaluadores-1' bash deploy/install.sh                              # solo HTTP por IP
#
# Se puede volver a ejecutar sin perder datos: conserva el .env y la base de datos si ya existen.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Ejecuta este script como root (sudo -i)."; exit 1; fi

SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR=/opt/bemba_pos
APP_USER=bemba
DOMAIN="${DOMAIN:-}"
DB_NAME=bemba_pos
DB_USER=bemba

echo "==> 1/9 Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3-venv python3-dev build-essential pkg-config default-libmysqlclient-dev \
    mysql-server caddy ufw rsync curl openssl

SERVER_IP="$(curl -4 -fsS --max-time 8 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"

echo "==> 2/9 Copiando el proyecto a $APP_DIR"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR"
rsync -a --delete \
    --exclude '.venv' --exclude '.env' --exclude 'db.sqlite3' --exclude 'staticfiles' --exclude '__pycache__' \
    "$SRC"/ "$APP_DIR"/

echo "==> 3/9 Base de datos MySQL"
cat > /etc/mysql/mysql.conf.d/bemba.cnf <<'CNF'
[mysqld]
innodb_buffer_pool_size = 512M
max_connections = 300
character-set-server = utf8mb4
CNF
systemctl restart mysql

if [ ! -f "$APP_DIR/.env" ]; then
    echo "==> 4/9 Creando .env (claves nuevas)"
    DB_PASS="$(openssl rand -hex 16)"
    SECRET_KEY="$(openssl rand -base64 48 | tr -d '\n')"
    DEMO_PASSWORD="${DEMO_PASSWORD:-$(openssl rand -base64 9 | tr -d '/+=')a1!}"

    mysql <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
SQL

    if [ -n "$DOMAIN" ]; then
        BASE_URL="https://$DOMAIN"; HOSTS="$DOMAIN,$SERVER_IP,localhost"; HTTPS=True; CSRF="https://$DOMAIN"
    else
        BASE_URL="http://$SERVER_IP"; HOSTS="$SERVER_IP,localhost"; HTTPS=False; CSRF="http://$SERVER_IP"
    fi

    cat > "$APP_DIR/.env" <<ENVFILE
DB_ENGINE=mysql
MYSQL_DATABASE=$DB_NAME
MYSQL_USER=$DB_USER
MYSQL_PASSWORD=$DB_PASS
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
DJANGO_SECRET_KEY=$SECRET_KEY
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$HOSTS
DJANGO_HTTPS=$HTTPS
DJANGO_CSRF_TRUSTED_ORIGINS=$CSRF
PUBLIC_BASE_URL=$BASE_URL
SEED_DEMO_PASSWORD=$DEMO_PASSWORD
ALERT_EMAIL_RECIPIENTS=admin@example.com
ENVFILE
    NEW_ENV=1
else
    echo "==> 4/9 Ya existe .env: se conserva (base de datos y claves intactas)"
    NEW_ENV=0
fi
chmod 600 "$APP_DIR/.env"
# Lee valores del .env para el resumen final
get_env() { grep -E "^$1=" "$APP_DIR/.env" | head -1 | cut -d= -f2-; }

echo "==> 5/9 Entorno de Python"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements-mysql.txt"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

run_manage() { sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && .venv/bin/python manage.py $*"; }

echo "==> 6/9 Migraciones, archivos estáticos y datos de demostración"
run_manage migrate --noinput
run_manage collectstatic --noinput
run_manage seed_demo

echo "==> 7/9 Servicio de la aplicación (gunicorn)"
cat > /etc/systemd/system/bemba.service <<UNIT
[Unit]
Description=Bemba POS (gunicorn)
After=network.target mysql.service
Requires=mysql.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/gunicorn -c deploy/gunicorn.conf.py bemba.wsgi:application
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now bemba
systemctl restart bemba

echo "==> 8/9 Servidor web Caddy"
if [ -n "$DOMAIN" ]; then
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
CADDY
else
cat > /etc/caddy/Caddyfile <<CADDY
:80 {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
CADDY
fi
systemctl enable caddy
systemctl restart caddy

echo "==> 9/9 Firewall y copias de seguridad diarias"
if iptables -L INPUT -n 2>/dev/null | grep -q REJECT; then
    # Imágenes como las de Oracle Cloud traen reglas iptables que bloquean todo menos SSH: se abren 80 y 443 antes del REJECT.
    DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent >/dev/null
    POS="$(iptables -L INPUT --line-numbers -n | awk '/REJECT/ {print $1; exit}')"
    for PORT in 80 443; do
        if ! iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; then
            iptables -I INPUT "$POS" -p tcp --dport "$PORT" -j ACCEPT
            POS=$((POS + 1))
        fi
    done
    netfilter-persistent save >/dev/null
else
    ufw allow OpenSSH >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    ufw --force enable >/dev/null
fi

mkdir -p /var/backups/bemba
cat > /etc/cron.daily/bemba-backup <<'CRON'
#!/bin/sh
mysqldump --single-transaction bemba_pos | gzip > /var/backups/bemba/bemba_$(date +%F).sql.gz
find /var/backups/bemba -name '*.sql.gz' -mtime +7 -delete
CRON
chmod +x /etc/cron.daily/bemba-backup

sleep 3
echo
echo "============================================================"
echo " Bemba POS instalado"
echo "  Dirección:   $(get_env PUBLIC_BASE_URL)"
echo "  Estado:      $(systemctl is-active bemba) (aplicación) / $(systemctl is-active caddy) (web)"
echo "  Usuarios de prueba (misma contraseña para todos):"
echo "     admin_demo  gerente_demo  cajero_demo  mesero_demo  cocina_demo"
echo "  Contraseña:  $(get_env SEED_DEMO_PASSWORD)"
echo "============================================================"
