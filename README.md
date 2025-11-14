<div align="center">

# Ledger

### Your logs deserve better than expensive cloud services

**Free, fast, and powerful log analytics for backend developers**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/JakubTuta/Ledger-APP/pulls)

[Live Demo](https://ledger.jtuta.cloud) • [API Docs](https://bump.sh/tuta-corp/doc/ledger-api/) • [Python SDK](https://github.com/JakubTuta/Ledger-SDK) • [Report Bug](https://github.com/JakubTuta/Ledger-APP/issues)

</div>

---

## The Problem

You're running a backend service. Things break. Users complain. You need to know what happened, but:

- **Datadog costs $31/host/month** (plus usage charges)
- **New Relic wants $0.30/GB** after your free tier runs out
- **Sentry charges $26/month** for error tracking alone
- **DIY solutions** take weeks to build and maintain

**What if you could have enterprise-grade logging without the enterprise price tag?**

## The Solution

Ledger is a self-hosted log analytics platform that gives you everything you need:

```python
# Just add 3 lines to your code
from ledger_sdk import LedgerClient

client = LedgerClient(api_key="your_key")
client.log.info("User signed up", attributes={"user_id": "123"})

# That's it. Logs are captured, stored, and searchable in milliseconds.
```

Then watch your logs in real-time on a beautiful web dashboard. Search through millions of logs. Track errors automatically. All for free.

## What You Get

- **Lightning Fast** - Query 10,000+ logs/second, get results in <50ms
- **Automatic Error Grouping** - Like Sentry, but free (no per-error pricing)
- **Beautiful Web Dashboard** - Real-time streaming, charts, and analytics
- **Easy Integration** - One pip install, three lines of code
- **Production Ready** - Multi-tenant, rate-limited, horizontally scalable
- **100% Free** - Self-hosted, no limits, no credit card required

### Perfect For

- Backend APIs that need better error tracking
- Startups trying to keep costs down without sacrificing quality
- Microservices needing centralized logging
- Anyone tired of paying $100+/month for basic logging

## Get Started in 5 Minutes

### Prerequisites

Just need Docker installed. That's it.

### Installation

**Step 1:** Clone and start

```bash
git clone https://github.com/JakubTuta/Ledger-APP.git
cd Ledger-APP
cp .env.example .env

# Windows
./scripts/Make.ps1 up

# Linux/Mac
make -C scripts up
```

**Step 2:** Verify it's running

```bash
# Windows
./scripts/Make.ps1 health

# Linux/Mac
make -C scripts health
```

You should see all services reporting as healthy. The API is now live at `http://localhost:8000`.

### Send Your First Log

**Option 1: Use the Python SDK (recommended)**

```bash
pip install ledger-sdk
```

```python
from ledger_sdk import LedgerClient

# Initialize once
client = LedgerClient(
    api_key="your_api_key",  # Get this from the dashboard
    base_url="http://localhost:8000"
)

# Start logging
client.log.info("User logged in", attributes={"user_id": "123"})
client.log.warning("Slow database query", attributes={"duration_ms": 450})

# Errors are automatically captured with stack traces
try:
    process_payment()
except Exception as e:
    client.log.error("Payment processing failed", error=e)
```

**Option 2: Use the REST API directly**

First, create an account and project:

```bash
# Register
curl -X POST http://localhost:8000/api/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123", "name": "Your Name"}'

# Login
curl -X POST http://localhost:8000/api/v1/accounts/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123"}'
# Save the access_token from the response

# Create a project
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My App", "slug": "my-app", "environment": "production"}'

# Create an API key (save this - it's only shown once!)
curl -X POST http://localhost:8000/api/v1/projects/1/api-keys \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production Key"}'
```

Now send a log:

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

**Congratulations!** You just sent your first log. Now let's query it:

```bash
curl -X GET "http://localhost:8000/api/v1/logs?project_id=1&limit=10" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

You should see your log in the response. Try the web dashboard at `http://localhost:8000` for a better view.

## What You Can Do

### Search Your Logs

Find exactly what you need, fast:

```bash
# All error logs from the last hour
GET /api/v1/logs?project_id=1&level=error&start_time=2025-11-14T09:00:00Z

# Full-text search for "timeout"
GET /api/v1/logs/search?project_id=1&query=timeout

# Errors from a specific user
GET /api/v1/logs?project_id=1&level=error&user_id=123
```

### Track Your Metrics

Pre-computed analytics updated in real-time:

```bash
# How many errors are happening right now?
GET /api/v1/metrics/error-rate?project_id=1

# What are the most common errors?
GET /api/v1/metrics/top-errors?project_id=1

# How many logs per hour?
GET /api/v1/metrics/log-volume?project_id=1
```

### Send Logs in Batches

Need to send lots of logs at once? Use batch ingestion:

```python
# Send up to 1,000 logs in one request
client.log.batch([
    {"level": "info", "message": "Event 1"},
    {"level": "info", "message": "Event 2"},
    # ... up to 1,000 logs
])
```

### Monitor Endpoints

Track your API performance:

```python
# Automatically capture endpoint metrics
@app.get("/api/users")
async def get_users():
    with client.monitor_endpoint("/api/users", method="GET"):
        # Your code here
        return users

# Ledger tracks response time, status codes, and errors
```

See [Endpoint Monitoring Guide](project_overview/ENDPOINT_MONITORING.md) for details.

## Features That Save You Time

### Automatic Error Grouping

Similar errors are automatically grouped together (like Sentry). No more scrolling through hundreds of duplicate errors:

- **Smart fingerprinting** - Groups by error type, location, and message
- **Occurrence tracking** - See how often each error happens
- **First/last seen** - Track when errors appear and reappear

### Real-Time Dashboard

Beautiful web interface for exploring your logs:

- **Live log streaming** - Watch logs appear in real-time
- **Advanced filtering** - Filter by level, time range, user, or custom attributes
- **Charts and graphs** - Visualize error rates and log volume
- **Multi-project support** - Manage all your services in one place

[Try the live demo](https://ledger.jtuta.cloud)

### Built-In Rate Limiting

Protect your infrastructure from runaway logging:

- **Per-minute limits** - Default: 1,000 logs/minute per project
- **Per-hour limits** - Default: 50,000 logs/hour per project
- **Daily quotas** - Default: 1 million logs/day per project
- **All configurable** - Adjust limits based on your needs

## How It Works

Ledger uses a microservices architecture optimized for speed and reliability:

```
Your App (with SDK)
    │
    ├─► Gateway (REST API) ──► Auth Service ──► PostgreSQL
    │                      │
    │                      ├─► Ingestion ──► Redis Queue ──► PostgreSQL
    │                      │
    │                      └─► Query ──► Redis Cache ──► PostgreSQL
    │
    └─► Web Dashboard
```

**Why this architecture?**

- **Separation of concerns** - Reading logs doesn't slow down writing logs
- **Redis buffering** - Handles traffic spikes without dropping logs
- **Pre-computed metrics** - Queries stay fast even with millions of logs
- **gRPC internally** - Fast, efficient communication between services

Want the technical details? Check out [ARCHITECTURE.md](documentation/ARCHITECTURE.md)

## Performance

Ledger is built to handle production workloads:

| Metric                | Performance | Notes                       |
| --------------------- | ----------- | --------------------------- |
| Log ingestion         | 10,000/sec  | Per Gateway instance        |
| Query response time   | <50ms       | P99, with cache             |
| Search millions       | <200ms      | Full-text search            |
| Error grouping        | Real-time   | Background workers          |
| Horizontal scaling    | Yes         | Add more Gateway instances  |
| Storage efficiency    | High        | Optimized PostgreSQL schema |

## Configuration

Customize Ledger by editing your `.env` file:

```bash
# Gateway settings
GATEWAY_PORT=8000

# Rate limits (adjust based on your needs)
DEFAULT_RATE_LIMIT_PER_MINUTE=1000
DEFAULT_RATE_LIMIT_PER_HOUR=50000
DEFAULT_DAILY_QUOTA=1000000

# Database connections (defaults work for Docker)
REDIS_HOST=redis
AUTH_DB_HOST=postgres-auth
LOGS_DB_HOST=postgres-logs
```

See [Configuration Guide](documentation/ARCHITECTURE.md#configuration) for all options.

## Ecosystem

Ledger is more than just the server:

- **[Python SDK](https://github.com/JakubTuta/Ledger-SDK)** - Official client library ([PyPI](https://pypi.org/project/ledger-sdk/))
- **[Web Dashboard](https://github.com/JakubTuta/Ledger-WEB)** - React-based frontend
- **[Live Demo](https://ledger.jtuta.cloud)** - Try it without installing

**Coming Soon:**

- JavaScript/Node.js SDK
- Go SDK
- Java SDK
- Slack/Discord integrations
- Webhook alerts

## Documentation

- **[API Reference](https://bump.sh/tuta-corp/doc/ledger-api/)** - Complete REST API documentation
- **[OpenAPI Spec](https://ledger-server.jtuta.cloud/openapi.json)** - Machine-readable API specification
- **[Architecture Guide](documentation/ARCHITECTURE.md)** - How everything fits together
- **[Services Guide](documentation/SERVICES.md)** - Deep dive into each service
- **[Development Guide](CLAUDE.md)** - For contributors

## Contributing

We welcome contributions! Whether it's:

- Reporting bugs
- Suggesting features
- Improving documentation
- Submitting pull requests

Check out our [Issues](https://github.com/JakubTuta/Ledger-APP/issues) to get started.

## Development

Working on Ledger itself? Here are the essential commands:

```bash
# Start all services
./scripts/Make.ps1 up

# Run tests
./scripts/Make.ps1 test

# View logs
./scripts/Make.ps1 logs-gateway
./scripts/Make.ps1 logs-auth
./scripts/Make.ps1 logs-ingestion

# Database operations
./scripts/Make.ps1 db-migrate   # Create migration
./scripts/Make.ps1 db-upgrade   # Apply migrations
./scripts/Make.ps1 db-shell     # PostgreSQL shell

# Stop everything
./scripts/Make.ps1 down
```

See [CLAUDE.md](CLAUDE.md) for detailed development instructions.

## Technology Stack

Built with modern, proven technologies:

- **Backend:** Python 3.12+, FastAPI, gRPC
- **Databases:** PostgreSQL 15, Redis 7
- **Infrastructure:** Docker, Docker Compose
- **Communication:** REST (external), gRPC (internal)

## Production Deployment

Ledger is running in production:

- **API:** https://ledger-server.jtuta.cloud
- **Dashboard:** https://ledger.jtuta.cloud

Want to deploy your own? See [Deployment Guide](documentation/ARCHITECTURE.md#deployment).

## Support

Need help?

- **Questions?** [Open a Discussion](https://github.com/JakubTuta/Ledger-APP/discussions)
- **Found a bug?** [Report an Issue](https://github.com/JakubTuta/Ledger-APP/issues)
- **Want to contribute?** [Submit a PR](https://github.com/JakubTuta/Ledger-APP/pulls)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
