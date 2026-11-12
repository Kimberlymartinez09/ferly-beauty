# core/settings_prod.py
"""Configuración de producción — Render.com (versión final W03).

Hereda settings.py y sobreescribe todo lo necesario para producción.

Variables de entorno requeridas en Render Dashboard:
    SECRET_KEY              → clave aleatoria de ≥ 50 caracteres
    DATABASE_URL            → proporcionada automáticamente por Render PostgreSQL
    DJANGO_SETTINGS_MODULE  → core.settings_prod
    ALLOWED_HOSTS           → tu-app.onrender.com (o dejar vacío para auto)
    STRIPE_SECRET_KEY       → sk_live_... o sk_test_...
    STRIPE_PUBLISHABLE_KEY  → pk_live_... o pk_test_...
    STRIPE_WEBHOOK_SECRET   → whsec_... (del endpoint creado en el Dashboard de Stripe)
"""
from .settings import *  # noqa: F401,F403  hereda toda la configuración base
import os

import dj_database_url

# ── SEGURIDAD BÁSICA ───────────────────────────────────────────────────────
DEBUG = False
SECRET_KEY = os.environ['SECRET_KEY']  # falla si no existe, intencionalmente

# ── HOSTS PERMITIDOS ────────────────────────────────────────────────────────
_render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
_extra_hosts = os.environ.get('ALLOWED_HOSTS', '').split(',')

ALLOWED_HOSTS = ['localhost', '127.0.0.1'] + (
    [_render_host] if _render_host else []
) + [h for h in _extra_hosts if h]

# ── BASE DE DATOS: PostgreSQL via DATABASE_URL ─────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )
}

# ── CSRF: dominios de confianza ────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = []
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_render_host}')

# ── PROXY (Render termina SSL antes de llegar a Django) ───────────────────
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── HEADERS HTTP SEGUROS ───────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

# ── STRIPE ─────────────────────────────────────────────────────────────────
# Se leen del entorno sin valores de respaldo para que nunca se use una
# clave de prueba inventada en producción.
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# ── ALMACENAMIENTO ─────────────────────────────────────────────────────────
# CompressedStaticFilesStorage comprime los estáticos sin exigir un manifiesto.
# Con CompressedManifestStaticFilesStorage, cualquier referencia a un archivo
# que no esté en el manifiesto (como vendor/bootswatch de Jazzmin) devuelve
# 500 en todo el admin.
_bucket = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

if _bucket:
    # Solo activa S3 si la variable de entorno está configurada
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    }
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    AWS_STORAGE_BUCKET_NAME = _bucket
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    MEDIA_URL = f'https://{_bucket}.s3.amazonaws.com/'

# ── LOGGING: solo WARNING y superiores en producción ──────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[%(levelname)s] %(name)s: %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django.security': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}