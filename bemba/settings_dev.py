from .settings import *

# Use SQLite for development when MariaDB is not available or incompatible.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'bemba@example.com'
ALERT_EMAIL_RECIPIENTS = os.getenv('ALERT_EMAIL_RECIPIENTS', 'admin@example.com').split(',')
