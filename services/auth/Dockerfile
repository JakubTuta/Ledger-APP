# ==================== Stage 1: Builder ====================
FROM python:3.12-slim AS builder

# Set working directory
WORKDIR /build

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies to /install
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==================== Stage 2: Runtime ====================
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENV_FILE_PATH=.env

# Default command (overridden by docker-compose to run gRPC server)
CMD ["python", "-m", "auth_service.main"]