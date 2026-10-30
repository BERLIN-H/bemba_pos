"""Configuración de gunicorn para producción (se lee con: gunicorn -c deploy/gunicorn.conf.py bemba.wsgi)."""
import multiprocessing
import os

bind = os.getenv('GUNICORN_BIND', '127.0.0.1:8000')
cpus = multiprocessing.cpu_count()
workers = int(os.getenv('GUNICORN_WORKERS', cpus * 2 + 1))
threads = int(os.getenv('GUNICORN_THREADS', 4))
worker_class = 'gthread'          # varios hilos por proceso: aguanta muchas conexiones a la vez
timeout = 60
keepalive = 5
max_requests = 2000               # recicla procesos para evitar fugas de memoria
max_requests_jitter = 200
accesslog = '-'
errorlog = '-'
