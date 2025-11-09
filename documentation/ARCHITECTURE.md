# Ledger System Architecture

## Overview

Ledger is built on a microservices architecture designed for high throughput, reliability, and scalability. This document explains how the system works and why certain design decisions were made.

## System Components

```
┌──────────────────────────────────────────────────────────────┐
│                        Your Applications                      │
│              (Python SDK, Node SDK, Direct API)              │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTPS REST
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                    Gateway Service (Port 8000)               │
│  ┌────────────┐  ┌──────────┐  ┌────────────┐              │
│  │    Auth    │  │   Rate   │  │  Circuit   │              │
│  │ Middleware │→ │ Limiting │→ │  Breaker   │              │
│  └────────────┘  └──────────┘  └────────────┘              │
└────────┬─────────────────┬─────────────┬────────────────────┘
         │ gRPC            │ gRPC        │ gRPC
         ▼                 ▼             ▼
┌────────────────┐  ┌─────────────┐  ┌──────────────┐
│  Auth Service  │  │  Ingestion  │  │    Query     │
│   (Port 50051) │  │   Service   │  │   Service    │
│                │  │ (Port 50052)│  │ (Port 50053) │
└────────┬───────┘  └──────┬──────┘  └──────┬───────┘
         │                 │                 │
         ▼                 ▼                 ▼
┌────────────────┐  ┌─────────────────────────────────┐
│ PostgreSQL     │  │      Redis Cache & Queues       │
│ (Auth DB)      │  ├─────────────────────────────────┤
│ Port 5432      │  │ • API key cache (5min TTL)      │
└────────────────┘  │ • Rate limit counters           │
                    │ • Log ingestion queues          │
                    │ • Pre-computed metrics          │
                    └──────────┬──────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   PostgreSQL        │
                    │   (Logs DB)         │
                    │   Port 5433         │
                    │ • Time-partitioned  │
                    │ • BRIN indexes      │
                    └─────────────────────┘
                               ▲
                               │
                    ┌──────────┴──────────┐
                    │  Analytics Workers  │
                    │ (Background Jobs)   │
                    │ • Error aggregation │
                    │ • Metrics           │
                    └─────────────────────┘
```

## Service Details

### Gateway Service

**Purpose**: Single entry point for all external API requests

**Key Responsibilities**:
- Route REST requests to internal gRPC services
- Authenticate requests (JWT session tokens or API keys)
- Enforce rate limits per project
- Provide fault tolerance with circuit breakers

**Authentication Methods**:
- **JWT Session Tokens**: Issued by `/register` and `/login` endpoints, valid for 1 hour
  - Used for account-level operations (project management, settings)
  - Stored in Redis with key format `session:{token}`
  - Automatically provided after registration (no separate login needed)
- **API Keys**: Long-lived keys for log ingestion
  - Used for high-throughput data ingestion
  - Validated via Auth Service with Redis caching
  - Format: `ledger_<random_32_chars>`

**Why it exists**:
- Centralizes security and policy enforcement
- Shields internal services from external traffic
- Simplifies client integration (REST instead of gRPC)
- Enables independent scaling of business logic services

**Performance**:
- Target: 10,000 requests/second per instance
- Latency: <50ms (p99) with cached authentication
- Horizontally scalable (stateless)

### Auth Service

**Purpose**: Manages user accounts, projects, and API keys

**Key Responsibilities**:
- User registration and authentication
- Multi-tenant project management
- API key generation and validation
- Daily usage tracking and quota enforcement

**Why it exists**:
- Centralized security reduces attack surface
- Shared authentication logic across all services
- Independent scaling for auth-heavy workloads

**Performance**:
- API key validation: 5ms (cached), 100ms (uncached)
- Uses Redis caching for 95%+ hit rate
- bcrypt hashing with appropriate cost factors

### Ingestion Service

**Purpose**: High-throughput log collection and queuing

**Key Responsibilities**:
- Validate incoming logs
- Enrich logs with metadata (timestamps, error fingerprints)
- Queue logs in Redis for asynchronous processing
- Monitor queue depth and apply backpressure

**Why it exists**:
- Decouples log reception from storage (async processing)
- Handles traffic spikes with Redis queue buffering
- Fast response times (202 Accepted immediately)
- Prevents database overload during high traffic

**Performance**:
- Accepts logs in <10ms
- Batch ingestion up to 1,000 logs per request
- MessagePack serialization for efficiency
- Queue depth limit: 100,000 per project

### Query Service

**Purpose**: Fast log retrieval and search

**Key Responsibilities**:
- Query raw logs from PostgreSQL with filters
- Full-text search across log messages
- Retrieve pre-computed metrics from Redis
- Time-range queries with partition pruning

**Why it exists**:
- Separates read operations from write operations
- Optimized for query performance (connection pooling, indexes)
- Read-only design enables horizontal scaling
- Fast metrics via Redis cache

**Performance**:
- Raw log queries: <200ms (with partition pruning)
- Metrics queries: <5ms (Redis cached)
- Target: 5,000 queries/second per instance

### Analytics Workers

**Purpose**: Background processing for metrics and aggregations

**Key Responsibilities**:
- Pre-compute error rates (5-minute buckets)
- Aggregate log volumes by level and project
- Calculate top errors by fingerprint
- Generate daily usage statistics

**Why it exists**:
- Heavy aggregation queries don't impact user requests
- Pre-computed metrics enable instant query responses
- Scheduled jobs ensure data freshness
- No user-facing API (internal only)

**Performance**:
- Runs scheduled jobs (every 5min, 15min, 1hour)
- Writes results to Redis with TTL expiration
- Scales horizontally for more projects

## Data Flow

### Log Ingestion Flow

1. **Client sends log** → Gateway (REST API)
2. **Gateway authenticates** → Validates API key (Redis cache or Auth Service)
3. **Gateway checks rate limits** → Redis atomic counters
4. **Gateway forwards** → Ingestion Service (gRPC)
5. **Ingestion validates** → Pydantic validation
6. **Ingestion enriches** → Adds fingerprint, timestamps
7. **Ingestion queues** → Redis LPUSH (MessagePack)
8. **Workers consume** → Redis BRPOP
9. **Workers bulk insert** → PostgreSQL (COPY protocol)

**Timeline**: Steps 1-7 complete in <10ms (async)

### Log Query Flow

1. **Client requests logs** → Gateway (REST API)
2. **Gateway authenticates** → Validates API key (cached)
3. **Gateway forwards** → Query Service (gRPC)
4. **Query Service fetches** → PostgreSQL with filters
5. **Query Service returns** → Results to Gateway
6. **Gateway responds** → JSON to client

**Timeline**: <200ms for raw logs, <5ms for cached metrics

### Authentication Flow

1. **Client includes API key** → Authorization header
2. **Gateway checks Redis cache** → 95% cache hit (5ms)
3. **On cache miss** → Gateway calls Auth Service (gRPC)
4. **Auth Service queries DB** → Index-only scan (fast)
5. **Auth Service verifies** → bcrypt check (100ms)
6. **Auth Service returns** → Project ID + quotas
7. **Gateway caches result** → Redis (5-minute TTL)

## Design Decisions

### Why Microservices?

**Benefits**:
- **Independent Scaling**: Auth, Ingestion, and Query have different load patterns
- **Technology Flexibility**: Can use different databases/languages per service
- **Fault Isolation**: Ingestion failure doesn't affect queries
- **Team Organization**: Clear service boundaries

**Trade-offs**:
- More operational complexity (multiple services to deploy)
- Network latency between services (mitigated with gRPC)

### Why Separate Auth and Logs Databases?

**Auth Database**:
- Low volume, high consistency requirements
- OLTP workload (transactions)
- Critical for security
- Needs point-in-time recovery

**Logs Database**:
- High volume, eventual consistency acceptable
- Time-series workload (append-heavy)
- Can tolerate some data loss
- Uses partitioning for performance

**Benefits**: Independent scaling, backup strategies, and optimization

### Why gRPC for Internal Communication?

**Advantages**:
- 2.5x smaller payloads than JSON (binary Protocol Buffers)
- HTTP/2 multiplexing (multiple requests per connection)
- Strong typing with .proto contracts
- Built-in streaming support

**Trade-off**: More complex than REST, but worth it for internal services

### Why Redis for Everything Fast?

**Use Cases**:
1. **API Key Cache**: Sub-millisecond lookups (95% hit rate)
2. **Rate Limiting**: Atomic counters with automatic expiration
3. **Log Queues**: LPUSH/BRPOP for async processing
4. **Metrics Cache**: Pre-computed analytics results

**Benefits**: Single source of truth for hot data, automatic TTL cleanup

### Why Connection Pooling?

**Problem**: Creating new connections takes 50-100ms

**Solution**: Maintain pool of persistent connections
- PostgreSQL: 20 base + 10 overflow connections
- gRPC: 10 persistent channels with keepalive
- Redis: 50 connection pool

**Result**: Eliminates connection overhead, handles traffic bursts

### Why Partition PostgreSQL Logs Table?

**Without Partitioning**:
- Query scans entire table (millions/billions of rows)
- Indexes grow huge (slow inserts and queries)
- Hard to drop old data

**With Monthly Partitioning**:
- Query scans only relevant partition (10-100x faster)
- BRIN indexes are tiny (1000x smaller than B-tree)
- Drop old partitions instantly (no DELETE needed)

**Example**: Query for last 7 days scans 1 partition, not 12

## Scalability

### Horizontal Scaling

All services are stateless and can be scaled independently:

- **Gateway**: Add instances behind load balancer
- **Auth Service**: Add instances (Redis cache shared)
- **Ingestion Service**: Add instances (Redis queue shared)
- **Query Service**: Add instances (read-only)
- **Analytics Workers**: Distribute jobs across workers

### Database Scaling

**PostgreSQL**:
- Current: Single instance handles 5,000 queries/sec
- Next: Read replicas for Query Service
- Future: Sharding by project_id if needed

**Redis**:
- Current: Single instance handles 100,000 ops/sec
- Next: Redis Cluster if sustained >50,000 ops/sec

### Performance Targets

| Component               | Target         | Current        |
|-------------------------|----------------|----------------|
| Gateway throughput      | 10K RPS        | Achieved       |
| Log ingestion latency   | <10ms          | Achieved       |
| Query latency (cached)  | <50ms          | Achieved       |
| Query latency (raw)     | <200ms         | Achieved       |
| Cache hit rate          | >95%           | Achieved       |

## Reliability Features

### Circuit Breaker

**Problem**: Auth Service failure blocks all requests

**Solution**: Circuit breaker with stale cache fallback
- CLOSED: Normal operation
- OPEN: After 5 failures, serve 10-minute emergency cache
- HALF_OPEN: Test recovery after 30 seconds

**Result**: System stays operational during Auth Service outages

### Rate Limiting

**Protection Against**:
- DDoS attacks
- Quota abuse
- Runaway clients

**Implementation**: Redis sliding window
- Per-minute limit: 1,000 requests
- Per-hour limit: 50,000 requests
- Configurable per project

### Backpressure

**Problem**: Too many logs can overwhelm storage

**Solution**: Queue depth monitoring
- Max 100,000 logs per project in queue
- Returns 503 with Retry-After when full
- Clients implement exponential backoff

## Security

### API Key Security

- Never stored in plaintext (bcrypt hashed)
- Cached validation result, not the key itself
- Keys can be revoked instantly
- Shown once during creation

### Network Security

- External: HTTPS/TLS 1.3 (production)
- Internal: gRPC (mTLS in production)
- Redis: Password protected
- PostgreSQL: Private VPC

### Multi-Tenancy

- Project-level isolation (data never shared)
- API keys scoped to single project
- Quotas enforced per project
- Query Service validates ownership

## Monitoring & Observability

### Health Checks

- `/health` - Basic liveness check
- `/health/deep` - Dependency health (Redis, gRPC)

### Metrics (Prometheus format)

- Request duration histograms (p50, p95, p99)
- Cache hit rates
- Error rates by service
- Queue depths
- Database connection pool usage

### Logging

- Structured JSON logs
- Correlation IDs for request tracing
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

## Future Enhancements

- **Distributed Tracing**: OpenTelemetry integration
- **Alerting**: PagerDuty/Slack notifications
- **ML Anomaly Detection**: Automatic issue detection
- **Hot/Cold Storage**: Move old logs to cheaper storage
- **Read Replicas**: Scale Query Service reads
- **Compression**: Reduce storage costs by 5-10x
