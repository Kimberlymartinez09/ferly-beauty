#!/bin/sh
# docker-entrypoint.sh
# Punto de entrada unificado para el contenedor ERP Django.
# Se ejecuta en LOCAL (docker-compose) y en PRODUCCIÓN (Render).
# IMPORTANTE: este archivo debe tener finales de línea LF (ver .gitattributes).
# ─────────────────────────────────────────────────────────────────
set -e   # detener si cualquier comando falla

# ── W16: si se recibe un comando, ejecutarlo tal cual ────────────────
# Ej.: docker-compose `command: celery -A core worker ...` o el
# "Docker Command" de un Background Worker en Render.
# Sin argumentos → flujo normal del servicio web (migrar + gunicorn).
if [ "$#" -gt 0 ]; then
    echo "==> [entrypoint] Ejecutando comando: $*"
    exec "$@"
fi

echo "==> [entrypoint] Ejecutando migraciones de base de datos..."
python manage.py migrate --noinput

echo "==> [entrypoint] Recolectando archivos estáticos..."
python manage.py collectstatic --noinput --clear

echo "==> [entrypoint] Verificando la configuración de Django..."
python manage.py check --deploy 2>/dev/null || python manage.py check

# Superusuario: se crea solo si defines DJANGO_SUPERUSER_PASSWORD en Render.
# La contraseña nunca va en el código ni en Git. Si el usuario ya existe,
# createsuperuser falla y el mensaje de respaldo lo indica sin detener el arranque.
if [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    echo "==> [entrypoint] Creando superusuario (si no existe)..."
    python manage.py createsuperuser --noinput \
        --username "${DJANGO_SUPERUSER_USERNAME:-admin}" \
        --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" \
        || echo "==> [entrypoint] El superusuario ya existe."
fi

# ── W16: worker de Celery embebido (opción gratuita de Render) ───────
# Render Free no ofrece Background Workers: el worker corre en segundo
# plano dentro del mismo contenedor que Gunicorn.
#   --pool=solo           → un solo proceso (cabe en 512 MB)
#   --without-gossip/mingle/heartbeat → menos conexiones a Redis
# Se activa con CELERY_EMBEDDED_WORKER=1 y requiere REDIS_URL.
if [ "${CELERY_EMBEDDED_WORKER:-0}" = "1" ] && [ -n "${REDIS_URL:-}" ]; then
    echo "==> [entrypoint] Iniciando worker de Celery embebido (cola erp_django)..."
    celery -A core worker \
        --loglevel=info \
        --queues=erp_django \
        --pool=solo \
        --without-gossip --without-mingle --without-heartbeat &
else
    echo "==> [entrypoint] Worker de Celery embebido DESACTIVADO."
fi

echo "==> [entrypoint] Iniciando Gunicorn en 0.0.0.0:${PORT:-8000}..."
exec gunicorn core.wsgi \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --log-file - \
    --access-logfile -