# Stage 1: Build Tailwind CSS
FROM node:18-alpine AS css-builder

WORKDIR /build

COPY package.json ./
RUN npm install

COPY static_src/ ./static_src/
COPY tailwind.config.js ./
# Tailwind content config scans templates/ and core/ for class names
COPY templates/ ./templates/
COPY core/ ./core/
RUN npx tailwindcss -i static_src/input.css -o staticfiles/css/output.css --minify

# Stage 2: Runtime image
FROM python:3.13-slim

WORKDIR /app

# System dependencies (gcc needed for some Python packages, docker for security scans)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ca-certificates \
    curl \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker.io docker-cli \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer if requirements.txt unchanged)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy built CSS from builder stage
COPY --from=css-builder /build/staticfiles/css/output.css staticfiles/css/output.css

# Entrypoint lives OUTSIDE /app so it survives volume mounts in dev
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create non-root user
RUN adduser --disabled-password --no-create-home appuser && chown -R appuser:appuser /app && chown appuser:appuser /entrypoint.sh
USER appuser

EXPOSE 8234

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8234", "--workers", "2"]
