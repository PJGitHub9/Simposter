FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8003 \
    # Force paths under /config
    CONFIG_DIR=/config \
    OUTPUT_ROOT=/config/output \
    UPLOAD_DIR=/config/uploads \
    LOG_FILE=/config/simposter.log

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure default folders exist in image (mount overrides are fine)
RUN mkdir -p /config/output /config/uploads

# Copy app code
COPY backend ./backend
COPY frontend ./frontend

VOLUME ["/config"]
EXPOSE 8003

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8003"]
