# --- Stage 1: build the React frontend --------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python backend serving API + static frontend -------------------
FROM python:3.12-slim
WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .

COPY --from=frontend /build/dist /app/static

# Deployment defaults; FRED_API_KEY must be supplied at runtime.
# Mount a volume at /data to persist the cache across restarts (optional).
ENV OFV_STATIC_DIR=/app/static \
    OFV_CACHE_PATH=/data/cache.sqlite \
    OFV_TTL_QUOTES=300

RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
