# Ledger Services Guide

This document provides an overview of each service in the Ledger platform, what it does, and how it contributes to the system.

## Gateway Service

### Overview
The Gateway Service is your single entry point for all API interactions with Ledger. It handles authentication, rate limiting, and routes requests to the appropriate internal services.

### Key Features
- **REST API**: Standard HTTPS/JSON interface for all operations
- **Authentication**: Validates JWT tokens and API keys
- **Rate Limiting**: Prevents abuse with configurable limits
- **Circuit Breaker**: Maintains availability during service outages
- **Request Translation**: Converts REST to internal gRPC calls

### When You Use It
Every single API request you make goes through the Gateway Service. It's the only externally accessible service.

### Configuration
- **Port**: 8000 (HTTP/HTTPS)
- **Rate Limits**: 1,000 requests/minute, 50,000 requests/hour (default)
- **Timeout**: 30 seconds per request

### Performance
- Target throughput: 10,000 requests/second
- Average latency: <50ms (with cached auth)
- Horizontally scalable

---

## Auth Service

### Overview
The Auth Service manages all authentication and authorization for Ledger. It handles user accounts, projects, and API keys.

### Key Features
- **Account Management**: User registration and login
- **Multi-Tenancy**: Support for multiple projects per account
- **API Key Management**: Generate, validate, and revoke API keys
- **Quota Tracking**: Monitor and enforce daily log quotas
- **Secure Storage**: bcrypt hashing for passwords and keys

### When You Use It
Indirectly, every authenticated request uses the Auth Service for validation. Directly, you use it when:
- Registering a new account
- Logging in
- Creating or managing projects
- Generating API keys

### Data Model
- **Accounts**: Your user account with email/password
- **Projects**: Isolated environments (production, staging, dev)
- **API Keys**: Per-project authentication tokens
- **Quotas**: Daily log limits per project

### Security Features
- Password hashing (bcrypt, cost 12)
- API key hashing (bcrypt, cost 10)
- Keys shown only once at creation
- Redis caching (5-minute TTL) for fast validation
- Circuit breaker fallback to emergency cache

### Performance
- API key validation: 5ms (cached), 100ms (uncached)
- Cache hit rate: >95%
- Supports thousands of validations per second

---

## Ingestion Service

### Overview
The Ingestion Service is responsible for receiving and processing incoming logs at high speed. It validates, enriches, and queues logs for storage.

### Key Features
- **High Throughput**: Handles thousands of logs per second
- **Validation**: Ensures log data meets schema requirements
- **Enrichment**: Adds metadata like timestamps and error fingerprints
- **Queue Buffering**: Uses Redis to handle traffic spikes
- **Backpressure**: Returns 503 when queue is full (prevents overload)
- **Batch Support**: Accept up to 1,000 logs in a single request

### When You Use It
Every time you send logs to Ledger:
- Single log: `POST /api/v1/ingest/single`
- Batch logs: `POST /api/v1/ingest/batch`
- Check queue: `GET /api/v1/queue/depth`

### How It Works
1. Receives log via Gateway
2. Validates log structure (Pydantic)
3. Enriches with metadata:
   - `ingested_at`: Server timestamp
   - `error_fingerprint`: SHA-256 hash for error grouping
4. Serializes with MessagePack (faster than JSON)
5. Pushes to Redis queue (LPUSH)
6. Background workers consume queue (BRPOP)
7. Bulk insert to PostgreSQL (COPY protocol)

### Log Schema
**Required Fields**:
- `timestamp`: ISO 8601 format
- `level`: debug, info, warning, error, critical
- `log_type`: console, logger, exception, custom
- `importance`: low, standard, high

**Optional Fields**:
- `message`: Log message (max 10,000 chars)
- `error_type`, `error_message`, `stack_trace`: Exception details
- `environment`, `release`, `platform`: Context
- `attributes`: Custom JSONB data (max 100KB)

### Performance
- Accepts logs in <10ms
- Queue depth limit: 100,000 per project
- Batch size: Up to 1,000 logs
- Background workers handle database writes asynchronously

### Error Handling
- Partial success for batch requests
- Detailed error messages for rejected logs
- Dead-letter queue for unprocessable logs
- Graceful backpressure with Retry-After headers

---

## Query Service

### Overview
The Query Service provides fast access to your stored logs and pre-computed metrics. It's optimized for read operations and supports complex filtering and search.

### Key Features
- **Log Retrieval**: Query logs with filters (time, level, type)
- **Full-Text Search**: Search across log messages and attributes
- **Pre-Computed Metrics**: Instant access to aggregated data
- **Time-Range Queries**: Efficient partition pruning
- **Pagination**: Handle large result sets

### When You Use It
Whenever you need to retrieve or search logs:
- Query logs: `GET /api/v1/logs`
- Search logs: `GET /api/v1/logs/search`
- Get single log: `GET /api/v1/logs/{id}`
- Error rates: `GET /api/v1/metrics/error-rate`
- Log volumes: `GET /api/v1/metrics/log-volume`
- Top errors: `GET /api/v1/metrics/top-errors`
- Usage stats: `GET /api/v1/metrics/usage-stats`

### Query Capabilities

**Filters**:
- Time range (start_time, end_time)
- Log level (debug, info, warning, error, critical)
- Log type (console, logger, exception, etc.)
- Environment (production, staging, dev)
- Custom attributes (JSONB queries)

**Search**:
- Full-text search on message and error_message
- Attribute search: `attributes.user_id:"usr_123"`
- Regex support: `message:/timeout|error/i`

**Pagination**:
- Limit (default: 100, max: 1,000)
- Offset for simple pagination
- Cursor-based for large datasets

### Data Sources

**PostgreSQL (Raw Logs)**:
- Complete log history
- Monthly partitions for fast queries
- BRIN indexes for time-series
- Full-text search capabilities

**Redis (Metrics)**:
- Pre-computed by Analytics Workers
- Sub-5ms response times
- Updated every 5-15 minutes

### Performance
- Raw log queries: <200ms (with partition pruning)
- Metrics queries: <5ms (Redis cached)
- Target: 5,000 queries/second per instance
- Horizontally scalable (stateless)

### Optimization Features
- Partition pruning (only scan relevant months)
- Covering indexes (index-only scans)
- Connection pooling (30 base + 20 overflow)
- Query result caching (60-second TTL)

---

## Analytics Workers

### Overview
Analytics Workers run in the background to pre-compute metrics and aggregations. They read from the Logs Database and write results to Redis cache.

### Key Features
- **Scheduled Jobs**: Run at regular intervals (5min, 15min, 1hour)
- **Metric Aggregation**: Calculate error rates, log volumes, top errors
- **Error Grouping**: Group similar errors by fingerprint
- **Usage Statistics**: Track quota usage per project
- **Cache Population**: Write results to Redis for fast queries

### What It Does
Unlike other services, Analytics Workers have no API. They run scheduled jobs:

**Every 5 minutes**:
- Error rate aggregation (5-minute buckets, last 24 hours)
- Log volume by level and project

**Every 15 minutes**:
- Top errors by fingerprint (top 50, last 24 hours)

**Every hour**:
- Daily usage statistics (last 30 days)

### How It Works
1. Scheduler triggers job (APScheduler)
2. Query PostgreSQL Logs DB for time range
3. Aggregate data (COUNT, GROUP BY)
4. Serialize to JSON
5. Write to Redis with TTL (2x job interval)
6. Query Service reads from Redis

### Why Pre-Compute?
- **Speed**: Instant dashboard loads (<5ms)
- **Efficiency**: Heavy queries don't impact user requests
- **Scalability**: Add workers for more projects/metrics
- **Predictability**: Controlled resource usage

### Performance
- Jobs complete in seconds (time-bounded queries)
- Idempotent (safe to run multiple times)
- Horizontal scaling via job distribution

### Monitoring
- Health check via file-based monitoring
- Job execution time tracking
- Redis cache hit rate monitoring

---

## Service Communication

### External (Your Apps → Ledger)
- **Protocol**: HTTPS REST
- **Format**: JSON
- **Authentication**: API keys in Authorization header
- **Endpoint**: Gateway Service (port 8000)

### Internal (Service → Service)
- **Protocol**: gRPC
- **Format**: Protocol Buffers (binary)
- **Authentication**: Mutual TLS (production)
- **Benefits**: 2.5x smaller payloads, HTTP/2 multiplexing

### Why Different Protocols?
- **REST for external**: Easy integration, wide support
- **gRPC for internal**: Performance, strong typing, efficiency

---

## Database Architecture

### Auth Database (PostgreSQL)
**Purpose**: Store account, project, and API key data

**Tables**:
- `accounts`: User credentials
- `projects`: Project configurations
- `api_keys`: Hashed API keys with rate limits
- `daily_usage`: Quota tracking

**Optimization**: Covering indexes for fast API key lookups

### Logs Database (PostgreSQL)
**Purpose**: Store all log entries

**Tables**:
- `logs`: Main log storage (partitioned by month)
- `error_groups`: Aggregated error tracking

**Optimization**: Monthly partitions, BRIN indexes, JSONB for attributes

### Redis
**Purpose**: Fast caching and queue buffering

**Use Cases**:
- API key validation cache (5-minute TTL)
- Rate limiting counters (atomic operations)
- Log ingestion queues (LPUSH/BRPOP)
- Pre-computed metrics (written by Analytics Workers)

---

## Deployment

### Development
All services run in Docker containers via Docker Compose:
```bash
./scripts/Make.ps1 up    # Windows
make -C scripts up       # Linux/Mac
```

### Production Recommendations
- **Kubernetes**: For orchestration and auto-scaling
- **Managed Databases**: Cloud SQL for PostgreSQL
- **Managed Redis**: Memorystore or ElastiCache
- **Load Balancer**: For Gateway Service
- **Monitoring**: Prometheus + Grafana

---

## Service Dependencies

```
Gateway
  ├─ Depends on: Redis, Auth Service, Ingestion Service, Query Service
  └─ Accessed by: External clients

Auth Service
  ├─ Depends on: PostgreSQL (Auth DB), Redis
  └─ Accessed by: Gateway

Ingestion Service
  ├─ Depends on: Redis, PostgreSQL (Logs DB)
  └─ Accessed by: Gateway

Query Service
  ├─ Depends on: PostgreSQL (Logs DB), Redis
  └─ Accessed by: Gateway

Analytics Workers
  ├─ Depends on: PostgreSQL (Logs DB), Redis
  └─ Accessed by: Nobody (internal background jobs)
```

---

## Next Steps

- **API Reference**: See `API_REFERENCE.md` for complete endpoint documentation
- **Architecture**: See `ARCHITECTURE.md` for system design details
- **Development**: See `../CLAUDE.md` for development guidelines
