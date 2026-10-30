#!/usr/bin/env bash
# Borra los pedidos y movimientos de la demostración y la deja como nueva (usuarios, menú, mesas e inventario iniciales).
# Úsalo cuando los evaluadores terminen una ronda de pruebas. Ejecutar como root en el servidor.
set -euo pipefail
cd /opt/bemba_pos
sudo -u bemba .venv/bin/python manage.py seed_demo --reset
echo "Demostración restablecida."
