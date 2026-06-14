<div align="center">

# Ledger

### Your logs deserve better than expensive cloud services

**Free, fast, and powerful log analytics for backend developers**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)

[Live Demo](https://ledger.jtuta.cloud) • [API Docs](https://bump.sh/tuta-corp/doc/ledger-api/) • [Python SDK](https://github.com/JakubTuta/Ledger-SDK) • [Report Bug](https://github.com/JakubTuta/Ledger-APP/issues)

</div>

---

## What is Ledger

Ledger is a self-hosted log analytics platform. Capture, store, and search your logs in milliseconds — with a real-time web dashboard included.

```python
from ledger import LedgerClient

ledger = LedgerClient(api_key="your_key", base_url="http://localhost:8000")
ledger.log_info("User signed up", attributes={"user_id": "123"})
```

## Why Ledger

- **100% Free** — Self-hosted, no limits, no credit card required
- **Automatic error grouping** — Like Sentry, but without per-error pricing
- **Real-time streaming** — Watch logs appear live as your app runs
- **Distributed tracing** — End-to-end visibility across services
- **Alert rules** — Threshold-based alerts via in-app, email, or webhook
- **One-line setup** — `pip install ledger-sdk` and a few lines of code
- **Production ready** — Multi-tenant, rate-limited, horizontally scalable

## Get Started

### Prerequisites

Docker installed.

### Installation

```bash
git clone https://github.com/JakubTuta/Ledger-APP.git
cd Ledger-APP
cp .env.example .env

# Windows
./scripts/Make.ps1 up

# Linux/Mac
make -C scripts up
```

Verify everything is running:

```bash
# Windows
./scripts/Make.ps1 health

# Linux/Mac
make -C scripts health
```

API is live at `http://localhost:8000`.

### Send Your First Log

**Option 1: Python SDK (recommended)**

```bash
pip install ledger-sdk
```

```python
from ledger import LedgerClient

ledger = LedgerClient(
    api_key="your_api_key",  # Get this from the dashboard
    base_url="http://localhost:8000"
)

ledger.log_info("User logged in", attributes={"user_id": "123"})
ledger.log_warning("Slow database query", attributes={"duration_ms": 450})

try:
    process_payment()
except Exception as e:
    ledger.log_exception(e, message="Payment processing failed")
```

**Option 2: REST API**

```bash
# Register
curl -X POST http://localhost:8000/api/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123", "name": "Your Name"}'

# Login and save the access_token
curl -X POST http://localhost:8000/api/v1/accounts/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123"}'

# Create a project
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My App", "slug": "my-app", "environment": "production"}'

# Create an API key (shown only once)
curl -X POST http://localhost:8000/api/v1/projects/1/api-keys \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production Key"}'
```

Send a log:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/single \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2025-11-14T10:00:00Z",
    "level": "info",
    "message": "Hello from Ledger!",
    "attributes": {"user_id": "123"}
  }'
```

## Features

### Automatic Error Grouping

Similar errors are automatically grouped together — like Sentry, but free:

- Groups by error type, location, and message
- Tracks occurrence counts
- Shows first and last seen timestamps

### Real-Time Dashboard

- Live log streaming as your app runs
- Filter by level, time range, or custom attributes
- Charts and graphs for error rates and log volume
- Multi-project support

[Try the live demo](https://ledger.jtuta.cloud)

### Query Your Logs

```bash
# All errors from the last hour
GET /api/v1/logs?project_id=1&level=error&start_time=2025-11-14T09:00:00Z

# Error rate right now
GET /api/v1/metrics/error-rate?project_id=1

# Most common errors
GET /api/v1/metrics/top-errors?project_id=1
```

## Configuration

Edit your `.env` file:

```bash
GATEWAY_PORT=8000
DEFAULT_RATE_LIMIT_PER_MINUTE=1000
DEFAULT_RATE_LIMIT_PER_HOUR=50000
DEFAULT_DAILY_QUOTA=1000000
```

## Ecosystem

- **[Python SDK](https://github.com/JakubTuta/Ledger-SDK)** — Official client library ([PyPI](https://pypi.org/project/ledger-sdk/))
- **[Web Dashboard](https://github.com/JakubTuta/Ledger-WEB)** — Real-time log viewer
- **[Live Demo](https://ledger.jtuta.cloud)** — Try it without installing
- **[API Reference](https://bump.sh/tuta-corp/doc/ledger-api/)** — Complete REST API docs

## License

MIT License — see [LICENSE](LICENSE) for details.
