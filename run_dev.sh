#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "=== AutoQA Setup ==="

# 1. Create virtual environment
if [ ! -d "venv" ]; then
    echo "[1/5] Creating Python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# 2. Install dependencies
echo "[2/5] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Generate .env from template
if [ ! -f .env ]; then
    echo "[3/5] Generating .env from template..."
    cp .env.example .env
    # Generate a random secret key
    python3 -c "from django.core.management.utils import get_random_secret_key; print('SECRET_KEY=' + get_random_secret_key())" >> .env.tmp
    # Replace the placeholder
    grep -v '^SECRET_KEY=' .env > .env.new
    mv .env.tmp .env.replaced
    cat .env.replaced >> .env.new
    mv .env.new .env
    rm -f .env.replaced
    echo "  → .env created. Please review and adjust settings."
else
    echo "[3/5] .env already exists, skipping."
fi

# 4. Install Tailwind and build CSS
if [ ! -d "node_modules" ]; then
    echo "[4/5] Installing Node.js dependencies (Tailwind)..."
    npm install || echo "  → npm install failed. Make sure Node.js is installed."
else
    echo "[4/5] Node modules exist, skipping npm install."
fi

if [ -f "node_modules/.bin/tailwindcss" ]; then
    echo "  → Building Tailwind CSS..."
    npx tailwindcss -i static_src/input.css -o staticfiles/css/output.css --minify
fi

# 5. Run migrations
echo "[5/5] Running database migrations..."
export DJANGO_SETTINGS_MODULE=backend.settings
python manage.py migrate

echo ""
echo "=== Setup Complete ==="
echo ""
echo "This script is for LOCAL development only (running Django outside Docker)."
echo "For Docker, use 'docker compose up --build' instead (it handles all setup internally)."
echo ""
echo "Local dev:"
echo "  1. Create a superuser:  python manage.py createsuperuser"
echo "  2. Start Django:        python manage.py runserver"
echo "  3. Watch CSS (separate terminal): npm run watch:css"
echo ""
echo "Docker:"
echo "  docker compose up --build"
echo "  (adds 'css' service for live Tailwind rebuild: docker compose up --build css)"
echo ""
echo "Dashboard: http://127.0.0.1:8000"
echo "Admin:     http://127.0.0.1:8000/admin"
echo "Chrome CDP: http://localhost:9222"
