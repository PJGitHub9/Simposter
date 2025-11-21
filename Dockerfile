FROM python:3.11-slim

WORKDIR /app

# Allow setting PUID / PGID (Unraid standard)
ENV PUID=1000
ENV PGID=1000

RUN addgroup --gid $PGID appgroup && \
    adduser --uid $PUID --ingroup appgroup appuser

RUN mkdir -p /config /poster-outputs

COPY requirements.txt .

# Install deps AS ROOT before switching user
RUN pip install --no-cache-dir -r requirements.txt

# Drop privileges NOW
USER appuser

COPY backend ./backend
COPY frontend ./frontend

ENV OUTPUT_ROOT=/poster-outputs

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
