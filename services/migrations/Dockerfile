# ==================== Stage 1: Builder ====================
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==================== Stage 2: Runtime ====================
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY . .

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENV_FILE_PATH=.env

# Runs to completion and exits: brings every database up to the latest schema
# version, then the application services start behind it.
CMD ["python", "-m", "migration_service", "upgrade"]
