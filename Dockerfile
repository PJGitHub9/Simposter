# ---------- Frontend build stage ----------
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend

# Copy frontend dependencies and sources
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend ./

# Build with API pointing at container backend (same port)
ARG VITE_API_URL=http://localhost:8003
ENV VITE_API_URL=${VITE_API_URL}
RUN npm ci && npm run build

# ---------- Backend/runtime stage ----------
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8003 \
    # Force paths under /config
    CONFIG_DIR=/config \
    OUTPUT_ROOT=/config/output \
    UPLOAD_DIR=/config/uploads \
    SETTINGS_DIR=/config/settings \
    LOG_DIR=/config/logs

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Ensure usable fonts for text overlay (DejaVu)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

# Ensure default folders exist in image (mount overrides are fine)
RUN mkdir -p /config/output /config/uploads /config/settings /config/logs

# Copy backend code
COPY backend ./backend

# Copy built frontend assets
COPY --from=frontend-builder /frontend/dist ./frontend/dist

VOLUME ["/config"]
EXPOSE 8003

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8003"]
