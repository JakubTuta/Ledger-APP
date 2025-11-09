# Ledger - Production-Ready Log Analytics

**Stop losing money on expensive logging services.** Ledger is a free, open-source log analytics platform built for backend developers who need enterprise-grade monitoring without the enterprise price tag.

## Why Ledger?

Running a backend server? You need to know what's happening in production. But paid logging services can cost hundreds or thousands per month. Ledger gives you everything you need, completely free:

### Built for Backend Servers

✅ **Catch Every Error** - Automatic error grouping and real-time alerts so you never miss a critical issue\
✅ **Lightning Fast** - Ingest 10,000+ logs/second, query in <50ms. Your monitoring won't slow you down\
✅ **100% Free** - Self-hosted, no usage limits, no credit card required. Save thousands per year\
✅ **Production Ready** - Multi-tenant, rate-limited, and scalable from day one\
✅ **Easy Integration** - Drop-in SDK for Python (more languages coming soon)\
✅ **Complete Visibility** - Track errors, performance, and usage metrics in one place

### Perfect For

- **Startups** saving money while maintaining production monitoring
- **Backend APIs** that need fast, reliable error tracking
- **Microservices** requiring centralized logging across multiple services
- **DevOps teams** who want full control of their infrastructure
- **Any backend server** that needs better logging than console.log()

## Key Features

- **High Throughput**: Millions of logs per second with Redis queue buffering
- **Error Tracking**: Automatic error grouping and fingerprinting (Sentry-like)
- **Real-Time Analytics**: Pre-computed metrics and instant search
- **Multi-Tenancy**: Isolated projects with quotas for production/staging/dev
- **Powerful Search**: Full-text search with time-range filtering
- **Web Dashboard**: Beautiful UI for exploring logs and metrics ([Ledger-Front](https://github.com/JakubTuta/Ledger-Front))
- **Rate Limiting**: Built-in DDoS protection

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for development)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/JakubTuta/Ledger-APP.git
cd Ledger-APP
```

2. Copy environment configuration:

```bash
cp .env.example .env
```

3. Start all services:

```bash
# Windows (PowerShell)
./scripts/Make.ps1 up

# Linux/Mac
make -C scripts up
```

4. Check service health:

```bash
# Windows (PowerShell)
./scripts/Make.ps1 health

# Linux/Mac
make -C scripts health
```

The Gateway API will be available at `http://localhost:8000`

### Your First Log

1. **Register an account**:

```bash
curl -X POST http://localhost:8000/api/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123",
    "name": "Your Name"
  }'
```

2. **Login to get access token**:

```bash
curl -X POST http://localhost:8000/api/v1/accounts/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }'
```

3. **Create a project**:

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer <your_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My App",
    "slug": "my-app",
    "environment": "production"
  }'
```

4. **Create an API key**:

```bash
curl -X POST http://localhost:8000/api/v1/projects/1/api-keys \
  -H "Authorization: Bearer <your_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key"
  }'
```

Save the `full_key` - it won't be shown again!

5. **Send your first log**:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/single \
  -H "Authorization: Bearer <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2025-10-17T10:00:00Z",
    "level": "info",
    "log_type": "console",
    "importance": "standard",
    "message": "Hello from Ledger!"
  }'
```

6. **Query your logs**:

```bash
curl -X GET "http://localhost:8000/api/v1/logs?project_id=1&limit=10" \
  -H "Authorization: Bearer <your_api_key>"
```

## Architecture Overview

Ledger uses a microservices architecture with the following components:

```
┌─────────────────┐
│  Your App/SDK   │
└────────┬────────┘
         │ REST API
         ▼
┌─────────────────┐
│  Gateway (8000) │ ← Single entry point for all requests
└────────┬────────┘
         │ Internal gRPC
         ├───────┬──────────┬─────────────┐
         ▼       ▼          ▼             ▼
    ┌────────┐ ┌──────┐ ┌──────┐  ┌──────────┐
    │  Auth  │ │Ingest│ │Query │  │Analytics │
    │Service │ │      │ │      │  │ Workers  │
    └────┬───┘ └───┬──┘ └───┬──┘  └────┬─────┘
         │         │        │           │
         ▼         ▼        ▼           ▼
    ┌────────┐ ┌─────────────────────────┐
    │Auth DB │ │  Redis + Logs Database  │
    └────────┘ └─────────────────────────┘
```

### Core Services

- **Gateway Service**: Entry point for all API requests with authentication and rate limiting
- **Auth Service**: Manages accounts, projects, and API keys
- **Ingestion Service**: High-throughput log collection with Redis queue buffering
- **Query Service**: Fast log retrieval and search with pre-computed metrics
- **Analytics Workers**: Background processing for metrics aggregation and error grouping

For detailed architecture information, see `documentation/ARCHITECTURE.md`

## Using Ledger

### SDK Integration

Ledger provides official SDKs for easy integration with your backend:

**Python SDK**: Full-featured SDK with automatic error tracking

```python
# Install via pip
pip install ledger-sdk

# Use in your code
from ledger_sdk import LedgerClient

client = LedgerClient(api_key="your_api_key")
client.log.info("User logged in", attributes={"user_id": "123"})
client.log.error("Payment failed", error=exception)
```

**More Languages Coming Soon**: JavaScript/Node.js, Go, Java

**[📦 View SDK Repository](https://github.com/JakubTuta/Ledger-SDK)** - Complete SDK documentation, examples, and source code

### Web Dashboard

Monitor your logs with the Ledger web interface:

**[🌐 Ledger-Front](https://github.com/JakubTuta/Ledger-Front)** - Modern web dashboard for:

- Real-time log streaming
- Error grouping and tracking
- Analytics dashboards with charts
- Advanced search and filtering
- Multi-project management

### Log Ingestion

Send logs via REST API:

**Single Log**:

```bash
POST /api/v1/ingest/single
```

**Batch Logs** (up to 1,000):

```bash
POST /api/v1/ingest/batch
```

### Querying Logs

**Search logs**:

```bash
GET /api/v1/logs?project_id=1&level=error&start_time=2025-01-01T00:00:00Z
```

**Full-text search**:

```bash
GET /api/v1/logs/search?project_id=1&query=timeout
```

**Get metrics**:

```bash
GET /api/v1/metrics/error-rate?project_id=1
GET /api/v1/metrics/log-volume?project_id=1
GET /api/v1/metrics/top-errors?project_id=1
```

## Performance

Ledger is built for scale:

- **Ingestion**: 10,000+ logs/second per Gateway instance
- **Query Latency**: <50ms (p99) for cached requests, <200ms for raw log queries
- **Search**: Full-text search across millions of logs
- **Rate Limiting**: Configurable per-project limits (default: 1,000/min, 50,000/hour)

## Configuration

Key configuration options in `.env`:

```bash
# Gateway
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000

# Rate Limits
DEFAULT_RATE_LIMIT_PER_MINUTE=1000
DEFAULT_RATE_LIMIT_PER_HOUR=50000

# Project Quotas
DEFAULT_DAILY_QUOTA=1000000

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# PostgreSQL
AUTH_DB_HOST=postgres-auth
AUTH_DB_PORT=5432
LOGS_DB_HOST=postgres-logs
LOGS_DB_PORT=5433
```

## Documentation

- **[API Reference](documentation/API_REFERENCE.md)** - Complete REST API documentation
- **[Architecture](documentation/ARCHITECTURE.md)** - System design and service overview
- **[Services Guide](documentation/SERVICES.md)** - Detailed information about each service
- **[Development Guide](CLAUDE.md)** - For contributors and developers

## Related Projects

- **[Ledger-SDK](https://github.com/JakubTuta/Ledger-SDK)** - Official SDKs for multiple languages
- **[Ledger-Front](https://github.com/JakubTuta/Ledger-Front)** - Web dashboard for log visualization

## Development Commands

### Service Management

```bash
# Windows (PowerShell)
./scripts/Make.ps1 up              # Start all services
./scripts/Make.ps1 down            # Stop all services
./scripts/Make.ps1 health          # Check service health
./scripts/Make.ps1 logs-gateway    # View gateway logs

# Linux/Mac
make -C scripts up
make -C scripts down
make -C scripts health
make -C scripts logs-gateway
```

### Testing

```bash
# Windows (PowerShell)
./scripts/Make.ps1 test            # Run all tests

# Linux/Mac
make -C scripts test
```

## Technology Stack

- **Backend**: Python 3.12+, FastAPI, gRPC
- **Databases**: PostgreSQL 15, Redis 7
- **Infrastructure**: Docker, Docker Compose
- **Communication**: REST (external), gRPC (internal)

## Support

- **Issues**: [Report bugs or request features](https://github.com/JakubTuta/Ledger-APP/issues)
- **Documentation**: Complete guides available in `/documentation`
- **SDK Issues**: [Report SDK-specific issues](https://github.com/JakubTuta/Ledger-SDK/issues)
- **Frontend Issues**: [Report UI issues](https://github.com/JakubTuta/Ledger-Front/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
