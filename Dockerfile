# ---------- Frontend build stage ----------
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend

# Copy frontend dependencies and sources
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend ./

# Extract version from version.ts and save for runtime stage
RUN VERSION=$(grep "APP_VERSION" src/version.ts | sed "s/.*'\(.*\)'.*/\1/") \
    && echo "{\"app_version\": \"${VERSION}\"}" > /tmp/version-info.json \
    && echo "Extracted version: ${VERSION}"

# Build with API pointing at container backend (same port)
ARG VITE_API_URL=http://localhost:8003
ENV VITE_API_URL=${VITE_API_URL}
RUN npm ci && npm run build

# ---------- Backend/runtime stage ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8003 \
    PUID=1000 \
    PGID=1000 \
    UMASK=0000 \
    # Force paths under /config
    CONFIG_DIR=/config \
    OUTPUT_ROOT=/config/output \
    UPLOAD_DIR=/config/uploads \
    SETTINGS_DIR=/config/settings \
    LOG_DIR=/config/logs

WORKDIR /app
COPY --from=frontend-builder /tmp/version-info.json /tmp/version-info.json
# Docker image tag — passed via --build-arg DOCKER_TAG=latest at build time
ARG DOCKER_TAG=unknown
ARG GIT_BRANCH=unknown

# Install fonts+gosu (runtime deps, kept) in a single apt-get pass — fewer network round-trips
# means fewer chances to hit a transient DNS/connection blip mid-build, and Acquire::Retries
# rides out blips that do happen.
# Copy .ttf files into /app/config/fonts so the /api/fonts endpoint and _load_font() can find
# them without scanning /usr/share.
RUN apt-get update -o Acquire::Retries=5 \
    && apt-get install -y -o Acquire::Retries=5 --no-install-recommends \
        fonts-dejavu-core fonts-liberation gosu \
    && APP_VERSION=$(python3 -c "import json; print(json.load(open('/tmp/version-info.json'))['app_version'])") \
    && echo "Detected app version: ${APP_VERSION}" \
    && echo "Docker tag: ${DOCKER_TAG}" \
    && echo "{\"git_branch\": \"${GIT_BRANCH}\", \"app_version\": \"${APP_VERSION}\", \"docker_tag\": \"${DOCKER_TAG}\"}" > /app/build-info.json \
    && rm -f /tmp/version-info.json \
    && mkdir -p /app/config/fonts \
    && find /usr/share/fonts -name "*.ttf" -exec cp {} /app/config/fonts/ \; \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure default folders exist in image (mount overrides are fine)
RUN mkdir -p /config/output /config/uploads /config/assets /config/settings /config/logs

# Copy backend code
COPY backend ./backend

# Copy built frontend assets
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Runtime entrypoint to apply PUID/PGID/UMASK and permissions
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

VOLUME ["/config"]
EXPOSE 8003

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8003"]
