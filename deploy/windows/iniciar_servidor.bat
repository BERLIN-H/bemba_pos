@echo off
REM Publica Bemba POS desde este PC, gratis: servidor waitress + tunel publico de Cloudflare (sin cuenta ni tarjeta).
REM Antes de usarlo por primera vez sigue la seccion "Opcion gratis con tu PC" de DEPLOY.md.
setlocal
cd /d "%~dp0\..\.."
title Bemba POS - servidor

if not exist ".venv\Scripts\activate.bat" (
  echo No existe el entorno virtual .venv. Sigue los pasos de DEPLOY.md.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat

where cloudflared >nul 2>nul
if errorlevel 1 (
  echo Falta cloudflared. Instalalo con:  winget install --id Cloudflare.cloudflared
  echo Luego cierra y vuelve a abrir esta ventana.
  pause
  exit /b 1
)

python deploy\windows\preparar_entorno.py
if errorlevel 1 (
  echo La preparacion fallo. Revisa el mensaje de arriba.
  pause
  exit /b 1
)

set DJANGO_DEBUG=False
set DJANGO_HTTPS=True
set DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,.trycloudflare.com
set DJANGO_CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com

echo.
echo ================================================================
echo  Se abrira otra ventana con el tunel. Copia de ahi la direccion
echo  https://algo-aleatorio.trycloudflare.com y entregala a los
echo  evaluadores. Esa direccion CAMBIA cada vez que reinicies el tunel.
echo  Deja AMBAS ventanas abiertas mientras ellos prueben.
echo ================================================================
echo.
start "Bemba - tunel publico (copia la direccion trycloudflare)" cmd /k cloudflared tunnel --url http://127.0.0.1:8000

waitress-serve --listen=127.0.0.1:8000 --threads=24 --connection-limit=500 bemba.wsgi:application
pause
