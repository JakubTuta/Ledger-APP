# Ledger Services - What Each One Does

This guide explains each service in Ledger, what problem it solves, and how to work with it. Think of it as getting to know the team members who make Ledger work.

## Gateway Service - The Front Desk

### What It Does

The Gateway is like the front desk at a hotel - it's where everyone checks in, and it directs you to the right place. Every API request you make goes through here.

### Why You'll Appreciate It

- **One URL to remember:** Everything goes to `http://localhost:8000` (or your production URL)
- **Handles authentication:** You don't think about auth - the Gateway does it for you
- **Protects you from rate limits:** Tells you before you hit limits, not after
- **Stays up when things break:** Circuit breaker keeps working even if internal services hiccup

### How Authentication Works

The Gateway supports two types of authentication because you need different things:

**Session Tokens (JWT):**

- You get one when you register or login
- Lasts for 1 hour
- Use it for managing your account, creating projects, generating API keys
- Stored in Redis so it's fast to validate

**API Keys:**

- Long-lived tokens for your applications
- Use them for sending logs (the high-volume stuff)
- Format looks like: `ledger_proj_1_abc123...`
- First validation takes a bit (bcrypt check), then cached for 5 minutes

### Configuration

The defaults work for most people:

- Handles up to 1,000 requests per minute per project
- Can process about 10,000 requests/second on decent hardware
- 30-second timeout per request (plenty of time for normal operations)

You can adjust rate limits in your `.env` file if needed.

---

## Auth Service - The ID Checker

### What It Does

Manages who you are and what you have access to. Every account, project, and API key lives here.

### The Flow

**When you first register:**

1. You send email + password
2. We hash your password (bcrypt, intentionally slow for security)
3. Create your account
4. Automatically generate a session token
5. Return everything you need to start using Ledger immediately

**When you create an API key:**

1. We generate a random key
2. Show it to you once (save it!)
3. Hash and store the hash (not the key itself)
4. Future requests check against the hash

**When you send logs later:**

1. Gateway asks "is this API key valid?"
2. First time: Check database (~100ms with bcrypt)
3. Cache result in Redis
4. Next 5 minutes: Instant validation from cache (~5ms)

### Why It's Separate

Security, mostly. If something goes wrong in the Ingestion Service (say, a weird log crashes it), your authentication data is safely isolated in its own service with its own database.

Also, authentication scales differently than log ingestion. You might validate the same API key thousands of times per second (cache helps!), while user registration happens occasionally.

### Data It Manages

- **Accounts:** Your email, hashed password, name
- **Projects:** Containers for your logs (production, staging, dev, etc.)
- **API Keys:** Credentials for each project
- **Quotas:** How many logs you can send per day
- **Daily Usage:** Tracking to enforce quotas

Everything is scoped to projects. Your production logs never mix with staging, and each project has its own API keys and limits.

---

## Ingestion Service - The Express Lane

### What It Does

Gets your logs into the system as fast as possible. That's it. That's the whole job.

### How It's So Fast

**The secret: we don't wait for the database.**

Here's what happens when you send a log:

1. **Validation** - Check that your log is properly formatted (Pydantic does this fast)
2. **Enrichment** - Add server timestamp and error fingerprint for grouping
3. **Queue It** - Push to Redis queue (this is microseconds)
4. **Respond** - Tell you "got it!" with 202 Accepted
5. **Later** - Background workers pull from queue and write to PostgreSQL in batches

Your application doesn't wait for step 5. You get a response in under 10ms typically.

### Batching for Performance

You can send up to 1,000 logs in one request:

```python
client.log.batch([
    {"level": "info", "message": "Event 1"},
    {"level": "info", "message": "Event 2"},
    # ... up to 1,000 logs
])
```

This is much faster than 1,000 individual requests. The Ingestion Service handles the batch, validates each log, and queues them all at once.

### What Logs Look Like

**Required fields:**

- `timestamp` - When it happened (ISO 8601 format)
- `level` - debug, info, warning, error, critical
- `log_type` - console, logger, exception, custom
- `importance` - low, standard, high

**Optional but useful:**

- `message` - The actual log message (up to 10,000 characters)
- `error_type`, `error_message`, `stack_trace` - For exceptions
- `attributes` - Custom data as JSON (up to 100KB)

The Ingestion Service adds:

- `ingested_at` - When we received it
- `error_fingerprint` - SHA-256 hash for grouping similar errors

### Handling Traffic Spikes

Imagine your app suddenly gets featured and traffic 10x's. Your logging goes crazy. What happens?

**With the queue system:**

- Logs pile up in Redis queue (it's fast and can handle it)
- Workers process them at a steady pace
- Your application gets quick responses
- Nothing crashes

**Without the queue:**

- Database gets overwhelmed with writes
- Everything slows down
- Requests start timing out
- Things break

**Backpressure protection:** If the queue hits 100,000 logs for your project, we return `503 Service Unavailable` with a `Retry-After` header. Your SDK automatically backs off and retries. System stays healthy.

---

## Query Service - The Search Expert

### What It Does

Helps you find logs when you need them. Whether you want "all errors from the last hour" or "logs containing 'payment timeout'", the Query Service knows how to find them fast.

### Two Types of Queries

**Metrics (Pre-Computed):**

- Error rates over time
- Log volume by level
- Top errors by occurrence
- Daily usage statistics

These are computed by Analytics Workers and cached in Redis. Queries are instant (under 5ms) because we already did the work.

**Raw Logs (On-Demand):**

- Specific logs matching filters
- Full-text search across messages
- Filtering by time, level, environment, etc.

These hit PostgreSQL but are optimized with smart indexes and partitioning. Typically under 200ms.

### Search Capabilities

**Time range filtering:**

```
GET /api/v1/logs?start_time=2025-11-14T09:00:00Z&end_time=2025-11-14T10:00:00Z
```

Only searches the relevant time partition. If you're asking for logs from this month, we don't scan data from last year.

**Level filtering:**

```
GET /api/v1/logs?level=error
```

Find just the errors, ignore everything else.

**Full-text search:**

```
GET /api/v1/logs/search?query=timeout
```

Searches across message and error_message fields. Uses PostgreSQL's full-text search capabilities.

**Custom attributes:**

```
GET /api/v1/logs?attributes.user_id=123
```

Query your custom data. Stored as JSONB in PostgreSQL, which supports efficient queries.

### Performance Tricks

**Monthly Partitions:**
Logs are split into monthly tables. Asking for last week's logs? We only scan this month's partition, not the entire history. This can be 10-100x faster.

**BRIN Indexes:**
For time-series data, these indexes are tiny (1000x smaller than traditional B-tree) but super fast. Perfect for our "usually querying recent logs" use case.

**Covering Indexes:**
For common queries (like fetching by project_id + time), the index contains all the data we need. No need to read the actual table rows - just the index. Much faster.

**Redis Cache:**
Metrics are cached with reasonable TTLs. Your dashboard doesn't re-compute "error rate for last hour" every time you refresh - it reads from cache.

### Pagination

Results are paginated to keep things responsive:

- Default: 100 logs per page
- Maximum: 1,000 logs per page
- Use `offset` for simple pagination or cursors for large datasets

---

## Analytics Workers - The Night Crew

### What They Do

While you're not looking, these workers crunch numbers so your dashboard is always up-to-date. They run in the background on a schedule.

### The Jobs They Run

**Every 5 minutes:**

- Calculate error rates in 5-minute buckets for the last 24 hours
- Count log volume by level (debug, info, warning, error, critical)
- Write results to Redis cache

**Every 15 minutes:**

- Find top 50 most common errors (grouped by fingerprint)
- Include first occurrence, last occurrence, and total count
- Cache for instant dashboard loading

**Every hour:**

- Calculate daily usage statistics for the last 30 days
- Track quota consumption per project
- Help you see usage trends

### Why Pre-Compute?

**Without pre-computing:**
You load your dashboard → It runs "SELECT COUNT(\*) WHERE level='error' AND timestamp > NOW() - INTERVAL '1 hour'" → Takes several seconds on millions of rows → Dashboard feels slow

**With pre-computing:**
You load your dashboard → It reads "error_rate:project_1" from Redis cache → Takes ~5ms → Dashboard feels instant

The workers do the heavy lifting when you're not waiting for results.

### How They Work

1. Scheduled job triggers (APScheduler)
2. Query PostgreSQL Logs database
3. Aggregate data (COUNT, GROUP BY, etc.)
4. Serialize to JSON
5. Write to Redis with TTL (2x the job interval - so data is fresh but not stale)
6. Query Service reads from Redis when you request metrics

### Scaling

Analytics Workers can scale horizontally. Need to compute metrics for 100 projects? Run more workers and distribute the load. Each worker handles a subset of projects.

---

## How Services Talk to Each Other

### External (You → Ledger)

**Protocol:** HTTPS with REST API
**Format:** JSON (easy to read and debug)
**Authentication:** Bearer token in Authorization header

Example:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/single \
  -H "Authorization: Bearer ledger_proj_1_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"level": "info", "message": "Hello"}'
```

### Internal (Service → Service)

**Protocol:** gRPC (Google's RPC framework)
**Format:** Protocol Buffers (binary, very compact)
**Why:** About 2.5x smaller payloads, HTTP/2 multiplexing, strong typing

You never see this - it's all internal. But it's why Ledger can handle high throughput without melting.

---

## Database Setup

### Auth Database (PostgreSQL)

Stores accounts, projects, API keys, quotas.

**Characteristics:**

- Small (thousands of records)
- Transactional (need consistency)
- Frequently read (API key validation)
- Rarely written (new accounts/projects are occasional)

**Optimizations:**

- Covering indexes for fast API key lookups
- Redis caching to reduce database load

### Logs Database (PostgreSQL)

Stores all your logs.

**Characteristics:**

- Large (millions to billions of records)
- Append-heavy (mostly inserts, few updates)
- Time-series data (recent logs queried most often)
- Can tolerate eventual consistency

**Optimizations:**

- Monthly partitions for fast time-range queries
- BRIN indexes for efficient storage
- JSONB for flexible custom attributes
- Bulk inserts via COPY protocol

### Redis

The fast cache and queue system.

**What it stores:**

- Validated API keys (5-minute TTL)
- Rate limit counters (expire automatically)
- Log queues (temporary until workers process them)
- Pre-computed metrics (TTL based on job frequency)

**Why Redis:**

- In-memory = extremely fast
- Automatic expiration = no manual cleanup
- Atomic operations = perfect for counters and queues
- Supports complex data types = flexible for our needs

---

## Deployment

### How It All Runs

Everything runs via Docker Compose - both development and production.

**Network architecture:**

- Only Gateway (port 8000) is exposed to the internet
- Everything else communicates on Docker's internal network
- Internal services aren't accessible from outside

**Why this matters:**
Even if someone compromises your server, they can't directly access PostgreSQL or Redis. They'd have to go through Gateway, which has authentication and rate limiting.

### Port Assignment

| Service           | Port  | Access          |
| ----------------- | ----- | --------------- |
| Gateway           | 8000  | External (you)  |
| Auth Service      | 50051 | Internal (gRPC) |
| Ingestion Service | 50052 | Internal (gRPC) |
| Query Service     | 50053 | Internal (gRPC) |
| PostgreSQL (Auth) | 5432  | Internal only   |
| PostgreSQL (Logs) | 5433  | Internal only   |
| Redis             | 6379  | Internal only   |

### Commands You'll Use

```bash
# Start everything
./scripts/Make.ps1 up

# Check health
./scripts/Make.ps1 health

# View logs
./scripts/Make.ps1 logs-gateway
./scripts/Make.ps1 logs-auth
./scripts/Make.ps1 logs-ingestion

# Stop everything
./scripts/Make.ps1 down
```

---

## What Each Service Depends On

**Gateway depends on:**

- Redis (for caching and rate limiting)
- Auth Service (for validation)
- Ingestion Service (for log ingestion)
- Query Service (for retrieving logs)

**Auth Service depends on:**

- PostgreSQL Auth Database
- Redis (for caching)

**Ingestion Service depends on:**

- Redis (for queuing)
- PostgreSQL Logs Database (via workers)

**Query Service depends on:**

- PostgreSQL Logs Database
- Redis (for metrics cache)

**Analytics Workers depend on:**

- PostgreSQL Logs Database (read aggregations)
- Redis (write results)

---

## Production Examples

**Live deployment:**

- **API:** https://ledger-server.jtuta.cloud
- **Dashboard:** https://ledger.jtuta.cloud

Running on Docker Compose with:

- Reverse proxy (nginx) for HTTPS
- Pre-built images from Google Artifact Registry
- Automated deployments

The same Docker Compose setup you use locally works in production. Scale by adding more Gateway instances behind a load balancer when needed.

---

## Resources

- **[API Reference](https://bump.sh/tuta-corp/doc/ledger-api/)** - Complete REST API documentation
- **[OpenAPI Spec](https://ledger-server.jtuta.cloud/openapi.json)** - Machine-readable API specification
- **[Architecture Guide](ARCHITECTURE.md)** - System design and decisions
- **[Main README](../README.md)** - Getting started guide
- **[GitHub](https://github.com/JakubTuta/Ledger-APP)** - Source code and issues
