# core/settings.py
import sys
from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_limpio(nombre, default=''):
    """Lee una variable de entorno y quita comillas sobrantes copiadas en Render."""
    valor = env(nombre, default=default)
    if isinstance(valor, str):
        return valor.strip().strip('"').strip("'")
    return valor


# ── Variables de entorno ──────────────────────────────────────────────────
env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(str(BASE_DIR / '.env'))

SECRET_KEY = env('SECRET_KEY', default='dev-key-insegura-solo-para-desarrollo')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# Render define esta variable automáticamente con tu dominio
RENDER_EXTERNAL_HOSTNAME = env('RENDER_EXTERNAL_HOSTNAME', default='')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')

# ── Apps instaladas ───────────────────────────────────────────────────────
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',   # debe ir antes de staticfiles
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Terceros
    'anymail',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    # Apps del ERP
    'clientes',
    'proveedores',
    'productos',
    'ventas',
    'reportes',
    'configuracion',
    'catalogo',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'core.urls'

# ── Templates ─────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'catalogo.context_processors.carrito_info',   # carrito (W13)
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ── Base de datos ─────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Internacionalización ──────────────────────────────────────────────────
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

# ── Archivos estáticos ────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Manifiesto de WhiteNoise solo en producción (requiere collectstatic)
if DEBUG or 'test' in sys.argv:
    _static_backend = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    _static_backend = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': _static_backend},
}

# ── Archivos media ────────────────────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── Autenticación ─────────────────────────────────────────────────────────
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/productos/'
LOGOUT_REDIRECT_URL = '/'

# ── DRF ──────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── JAZZMIN — Personalización del admin ───────────────────────────────────
JAZZMIN_SETTINGS = {
    # Identidad
    'site_title': 'ERP Django',
    'site_header': 'ERP UTEC Celaya',
    'site_brand': '📦 ERP Django',
    'welcome_sign': 'Bienvenido al Sistema ERP · UTEC Celaya',
    'copyright': 'MC. Román Fernando López González · UTEC Celaya',
    'site_icon': None,
    'site_logo': None,

    # Búsqueda global en el admin
    'search_model': ['clientes.Cliente', 'productos.Producto'],

    # Menú superior
    'topmenu_links': [
        {'name': 'Inicio ERP', 'url': '/', 'new_window': False},
        {'name': 'Productos',  'url': '/productos/'},
        {'name': 'Clientes',   'url': '/clientes/'},
        {'name': 'Ventas',     'url': '/ventas/'},
    ],

    # Menú de usuario
    'usermenu_links': [
        {'name': 'Ver ERP', 'url': '/', 'new_window': False},
    ],

    # Menú lateral
    'order_with_respect_to': [
        'clientes', 'proveedores', 'productos',
        'ventas', 'configuracion', 'auth',
    ],

    # Iconos Font Awesome
    'icons': {
        'auth': 'fas fa-users-cog',
        'auth.user': 'fas fa-user',
        'auth.Group': 'fas fa-users',
        'clientes.Cliente': 'fas fa-user-tie',
        'proveedores.Proveedor': 'fas fa-truck',
        'productos.Categoria': 'fas fa-tags',
        'productos.Producto': 'fas fa-box',
        'ventas.Venta': 'fas fa-file-invoice-dollar',
        'ventas.DetalleVenta': 'fas fa-list',
        'ventas.Pedido': 'fas fa-shopping-cart',
        'configuracion.ConfiguracionERP': 'fas fa-cogs',
    },
    'default_icon_parents': 'fas fa-folder',
    'default_icon_children': 'fas fa-circle',

    # Apariencia
    'related_modal_active': True,
    # 'custom_css': 'erp_custom.css',   # activar solo cuando exista static/erp_custom.css
    'show_sidebar': True,
    'navigation_expanded': True,
    'hide_apps': [],
    'hide_models': [],

    # UI
    'changeform_format': 'horizontal_tabs',
    'language_chooser': False,
}

JAZZMIN_UI_TWEAKS = {
    'navbar_small_text': False,
    'footer_small_text': False,
    'body_small_text': False,
    'brand_small_text': False,
    'brand_colour': 'navbar-dark',
    'accent': 'accent-navy',
    'navbar': 'navbar-dark',
    'no_navbar_border': False,
    'navbar_fixed': True,
    'layout_boxed': False,
    'footer_fixed': False,
    'sidebar_fixed': True,
    'sidebar': 'sidebar-dark-navy',
    'sidebar_nav_small_text': False,
    'sidebar_disable_expand': False,
    'sidebar_nav_child_indent': True,
    'sidebar_nav_compact_style': False,
    'sidebar_nav_legacy_style': False,
    'sidebar_nav_flat_style': False,
    'theme': 'default',
    'button_classes': {
        'primary': 'btn-primary',
        'secondary': 'btn-secondary',
        'info': 'btn-info',
        'warning': 'btn-warning',
        'danger': 'btn-danger',
        'success': 'btn-success',
    },
}

# ── DJANGO SITES (requerido por allauth) ──────────────────────────────────
SITE_ID = 1

# ── AUTHENTICATION BACKENDS ───────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',            # admin
    'allauth.account.auth_backends.AuthenticationBackend',  # allauth
]

# ── ALLAUTH: configuración para desarrollo académico ──────────────────────
ACCOUNT_LOGIN_METHODS      = {'username'}
ACCOUNT_EMAIL_REQUIRED     = False
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_LOGOUT_ON_GET      = True
ACCOUNT_SESSION_REMEMBER   = True

# ── STRIPE (pasarela de pago) ─────────────────────────────────────────────
# Las claves reales van en .env o en las variables de Render, nunca en Git.
STRIPE_SECRET_KEY      = env('STRIPE_SECRET_KEY',      default='sk_test_placeholder')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY', default='pk_test_placeholder')
STRIPE_WEBHOOK_SECRET  = env('STRIPE_WEBHOOK_SECRET',  default='whsec_placeholder')

# ── CELERY — Cola de tareas asíncronas (W16) ──────────────────────────────
# REDIS_URL definida (Render → Key Value o Redis local):
#     las tareas se encolan en Redis y las procesa el worker.
# REDIS_URL vacía (laboratorio sin Redis / tests):
#     modo EAGER → .delay() ejecuta la tarea en el mismo proceso.
REDIS_URL = _env_limpio('REDIS_URL')

if REDIS_URL:
    CELERY_BROKER_URL        = REDIS_URL
    CELERY_RESULT_BACKEND    = REDIS_URL
    CELERY_TASK_ALWAYS_EAGER = False
else:
    CELERY_BROKER_URL        = 'memory://'
    CELERY_RESULT_BACKEND    = 'cache+memory://'
    CELERY_TASK_ALWAYS_EAGER = True

# Los resultados caducan en 1 hora (el Key Value gratuito tiene 25 MB)
CELERY_RESULT_EXPIRES = 3600

# Formato de serialización (JSON es seguro y portable)
CELERY_ACCEPT_CONTENT    = ['json']
CELERY_TASK_SERIALIZER   = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Zona horaria (heredar de Django)
CELERY_TIMEZONE = TIME_ZONE

# Reintentos automáticos ante fallos de conexión al broker
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Tiempo máximo que puede correr una tarea antes de ser terminada (segundos)
CELERY_TASK_SOFT_TIME_LIMIT = 300   # 5 minutos
CELERY_TASK_TIME_LIMIT      = 360   # 6 minutos (hard limit)

# Cola por defecto: debe coincidir con -Q erp_django del worker
CELERY_TASK_DEFAULT_QUEUE = 'erp_django'

# Las excepciones NO se propagan al que llama: así un fallo al enviar el correo
# no hace que el webhook de Stripe responda con error y Stripe reintente el evento.
CELERY_TASK_EAGER_PROPAGATES = False

# ── CELERY BEAT — Tareas programadas (W18) ────────────────────────────────
CELERY_BEAT_SCHEDULE = {

    # Verificar stock bajo cada hora
    'verificar-stock-bajo-cada-hora': {
        'task':     'ventas.verificar_stock_bajo',
        'schedule': timedelta(hours=1),
        'args':     (5,),   # umbral = 5 unidades
        'options':  {'queue': 'erp_django'},
    },

    # Reporte de ventas diario a las 8:00 AM (hora México)
    'reporte-ventas-diario-8am': {
        'task':     'ventas.reporte_ventas_diario',
        'schedule': crontab(hour=8, minute=0),
        'options':  {'queue': 'erp_django'},
    },

}

# Beat usa la zona horaria de Django (no UTC)
CELERY_BEAT_TIMEZONE = TIME_ZONE

# ── CORREO ELECTRÓNICO ────────────────────────────────────────────────────
# Producción (Render): EMAIL_BACKEND se activa solo si existe SENDGRID_API_KEY.
# Desarrollo: sin clave, el correo se imprime en la terminal.
SENDGRID_API_KEY = _env_limpio('SENDGRID_API_KEY')

EMAIL_BACKEND = _env_limpio(
    'EMAIL_BACKEND',
    default=(
        'anymail.backends.sendgrid.EmailBackend'
        if SENDGRID_API_KEY
        else 'django.core.mail.backends.console.EmailBackend'
    ),
)

# Remitente: debe ser EXACTAMENTE una dirección verificada en SendGrid
# (Settings → Sender Authentication → Verify a Single Sender).
DEFAULT_FROM_EMAIL = _env_limpio(
    'DEFAULT_FROM_EMAIL',
    default='Ferly Beauty <noreply@erp-django.com>',
)

# Prefijo del asunto de los correos del sistema
EMAIL_SUBJECT_PREFIX = '[ERP Django] '

# Administradores que reciben alertas y reportes del sistema
ADMINS = [
    ('Admin ERP', _env_limpio('ADMIN_EMAIL', default='admin@erp-django.com')),
]

# Configuración de django-anymail (SendGrid)
ANYMAIL = {
    'SENDGRID_API_KEY': SENDGRID_API_KEY,
}