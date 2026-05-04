#!/bin/bash
set -e

# Run migrations (idempotent - safe to run every startup)
echo "Running Django migrations..."
python manage.py migrate --noinput

# Collect static files (rebuilds if needed)
python manage.py collectstatic --noinput 2>/dev/null || true

# Execute the main command, or default to Django dev server with hot reload
if [ $# -eq 0 ]; then
  exec python manage.py runserver 0.0.0.0:8000
else
  exec "$@"
fi
