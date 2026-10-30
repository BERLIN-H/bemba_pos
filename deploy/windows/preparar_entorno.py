"""Prepara Bemba POS para publicarlo desde un PC (Windows o Linux).

Hace tres cosas, todas seguras de repetir:
  1. Garantiza que el archivo .env tenga una DJANGO_SECRET_KEY propia (si no, el modo producción no arranca).
  2. Aplica las migraciones de la base de datos.
  3. Reúne los archivos estáticos (CSS y JS) para que el servidor los sirva.

Los datos de demostración se cargan aparte, una sola vez:  python manage.py seed_demo
"""
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / '.env'


def ensure_secret_key():
    text = ENV_FILE.read_text(encoding='utf-8') if ENV_FILE.exists() else ''
    if re.search(r'^DJANGO_SECRET_KEY=\S+', text, flags=re.MULTILINE):
        print('.env ya tiene DJANGO_SECRET_KEY.')
        return
    if text and not text.endswith('\n'):
        text += '\n'
    text += f'DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}\n'
    ENV_FILE.write_text(text, encoding='utf-8')
    print('Se agregó una DJANGO_SECRET_KEY nueva a .env.')


def manage(*args):
    result = subprocess.run([sys.executable, 'manage.py', *args], cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)


if __name__ == '__main__':
    ensure_secret_key()
    manage('migrate', '--noinput')
    manage('collectstatic', '--noinput')
    print('Entorno listo.')
