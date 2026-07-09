<div align="center">

# Ledger

### Your logs deserve better than expensive cloud services

**Free, fast, OpenTelemetry-native log and trace analytics for backend developers**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)

[Live Demo](https://ledger.jtuta.cloud) • [API Docs](https://bump.sh/tuta-corp/doc/ledger-api/) • [Python SDK](https://github.com/JakubTuta/Ledger-SDK) • [Report Bug](https://github.com/JakubTuta/Ledger-APP/issues)

</div>

---

## What is Ledger

Ledger is a self-hosted, OpenTelemetry-native log and trace analytics platform. It ingests
standard OTLP/HTTP from any language's OTel SDK — not just Python — and stores/searches logs and
traces in milliseconds, with a real-time web dashboard included.

```python
from ledger import LedgerClient

ledger = LedgerClient(api_key="your_key", base_url="http://localhost:8020")
ledger.log_info("User signed up", attributes={"user_id": "123"})
```

## Why Ledger

- **100% Free** — Self-hosted, no limits, no credit card required
- **OpenTelemetry-native** — accepts standard OTLP/HTTP traces, logs, *and metrics* from any language's OTel SDK
- **Fast full-text search** — trigram-indexed Explore page with facets and live tail
- **Error tracking workflow** — group, assign, resolve/ignore/mute, with automatic regression detection
- **Uptime & heartbeat monitors** — HTTP checks and dead-man's-switch pings for cron jobs
- **Alert rules** — threshold-based alerts with escalation and maintenance windows, delivered via in-app, email, webhook, Slack, Discord, PagerDuty, or Opsgenie
- **Distributed tracing** — End-to-end visibility across services
- **Two-factor auth & scoped sessions** — TOTP 2FA, httpOnly refresh cookies, per-device session management
- **One-line setup** — `pip install ledger-sdk` and a few lines of code (Python), or standard OTel env vars (any other language)
- **Production ready** — Multi-tenant, rate-limited, horizontally scalable
- **Fast** — tested sustaining 10,000+ logs/s on a single node with near-zero queue lag

## Get Started

### Prerequisites

Docker installed.

### Installation

```bash
git clone https://github.com/JakubTuta/Ledger-APP.git
cd Ledger-APP
cp .env.example .env
```

Open `.env` and set `JWT_SECRET` (and the SMTP/`FRONTEND_URL` settings if you want outbound email).
Everything else has a working default.

```bash
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

API is live at `http://localhost:8020`.

### Send Your First Log

**Option 1: Python SDK (recommended)**

```bash
pip install ledger-sdk
```

```python
from ledger import LedgerClient

ledger = LedgerClient(
    api_key="your_api_key",  # Get this from the dashboard
    base_url="http://localhost:8020"
)

ledger.log_info("User logged in", attributes={"user_id": "123"})
ledger.log_warning("Slow database query", attributes={"duration_ms": 450})

try:
    process_payment()
except Exception as e:
    ledger.log_exception(e, message="Payment processing failed")
```

**Option 2: Any OpenTelemetry SDK**

Not using Python? Ledger accepts standard OTLP/HTTP, so any language's stock OTel SDK works —
no Ledger-specific package required:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:8020"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer YOUR_API_KEY"
```

Then use your language's normal OTel SDK setup — traces go to `POST /v1/traces`, logs go to
`POST /v1/logs`, metrics go to `POST /v1/metrics` (all three accept `application/x-protobuf` or
`application/json`, gzip optional).

**Option 3: Account/project setup via REST API**

```bash
# Register
curl -X POST http://localhost:8020/api/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123", "name": "Your Name"}'

# Login and save the access_token
curl -X POST http://localhost:8020/api/v1/accounts/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123"}'

# Create a project
curl -X POST http://localhost:8020/api/v1/projects \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My App", "slug": "my-app", "environment": "production"}'

# Create an API key (shown only once)
curl -X POST http://localhost:8020/api/v1/projects/1/api-keys \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production Key"}'
```

Send a log via raw OTLP/JSON:

```bash
curl -X POST http://localhost:8020/v1/logs \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "resourceLogs": [{
      "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "my-app"}}]},
      "scopeLogs": [{
        "logRecords": [{
          "severityNumber": 9,
          "body": {"stringValue": "Hello from Ledger!"},
          "attributes": [{"key": "user_id", "value": {"stringValue": "123"}}]
        }]
      }]
    }]
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

## Ecosystem

- **[Python SDK](https://github.com/JakubTuta/Ledger-SDK)** — Official client library ([PyPI](https://pypi.org/project/ledger-sdk/)), OpenTelemetry-native with enhanced Python features
- **Any OpenTelemetry SDK** — Ledger's gateway accepts standard OTLP/HTTP; no Ledger-specific package needed for other languages
- **[Web Dashboard](https://github.com/JakubTuta/Ledger-WEB)** — Real-time log and trace viewer
- **[Live Demo](https://ledger.jtuta.cloud)** — Try it without installing
- **[API Reference](https://bump.sh/tuta-corp/doc/ledger-api/)** — Complete REST API docs

## License

MIT License — see [LICENSE](LICENSE) for details.
