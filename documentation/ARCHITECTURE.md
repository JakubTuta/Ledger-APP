# Understanding Ledger's Architecture

## What We Built and Why

Ledger is designed around one core idea: **logging should be fast, reliable, and not get in your way**. To make that happen, we built a microservices architecture that separates concerns so each part can do its job well.

Think of it like a restaurant kitchen: you have different stations (prep, grill, plating) each focused on one thing, working together to get food to customers quickly. That's how Ledger works - specialized services working together.

## The Big Picture

Here's how everything connects:

```
Your Application (using our SDK or sending HTTP requests)
            │
            ├──► Gateway Service (port 8000)
            │    ├─ The front door - handles auth, rate limits, routing
            │    └─ Real-time notifications via SSE (Server-Sent Events)
            │
            ├──► Auth Service
            │    └─ Manages who you are and what you can access
            │
            ├──► Ingestion Service
            │    ├─ Receives your logs super fast, queues them for storage
            │    └─ Publishes error notifications to Redis Pub/Sub
            │
            ├──► Query Service
            │    └─ Helps you find and retrieve your logs quickly
            │
            ├──► Analytics Workers
            │    └─ Crunches numbers in the background for dashboards
            │
            └──► Redis Pub/Sub
                 └─ Real-time event bus for instant error notifications
```

**The important part:** Only the Gateway is accessible from the outside world. Everything else runs internally for security. You talk to the Gateway, and it handles the rest.

## How the Services Work Together

### Gateway Service - Your Front Door

**What it does:** This is the only service you ever talk to directly. It's like a receptionist at a hotel - handling check-in (authentication), setting boundaries (rate limiting), and directing you to the right department.

**Why we built it this way:**
- **One entry point** means easier security - we only need to protect one service from the internet
- **Centralized policies** let us enforce rate limits and authentication in one place
- **REST API** is familiar and easy to use from any language or tool
- **Shields internal services** from the chaos of the internet

The Gateway can handle about 10,000 requests per second on a single instance. Need more? Just add another instance behind a load balancer.

### Auth Service - The Bouncer

**What it does:** Manages everything about who you are - your account, your projects, your API keys. When you send a log, this service confirms "yes, this API key is valid and belongs to project X."

**Why it's separate:**
- **Security isolation** - if something goes wrong elsewhere, your credentials are safe
- **Independent scaling** - authentication has different load patterns than log ingestion
- **Caching layer** - we cache validated API keys in Redis so we're not hitting the database every time

When you first use an API key, it takes about 100 milliseconds to validate (we're checking your password hash with bcrypt, which is intentionally slow for security). After that? Cached in Redis, and validation takes less than 5 milliseconds. We hit that cache over 95% of the time, which keeps things fast.

### Ingestion Service - The Speed Demon

**What it does:** Receives your logs and gets them stored as fast as possible. Speed is everything here.

**Here's how it works:**
1. Your log arrives (validated by Gateway)
2. We check that it's properly formatted
3. We add some metadata (timestamps, error fingerprints for grouping)
4. We push it to a Redis queue
5. We immediately respond "got it!" (this is the fast part - usually under 10ms)
6. Background workers pull from the queue and write to PostgreSQL in batches

**Why queuing matters:**
Imagine your app suddenly gets a traffic spike and starts logging like crazy. Without a queue, we'd be trying to write directly to the database, which would slow down or even crash. With Redis queue buffering, we can handle those spikes smoothly - the queue absorbs the burst, and workers process it at a steady pace.

You can send up to 1,000 logs in one batch request, which is much faster than sending them one at a time.

### Query Service - The Librarian

**What it does:** Helps you find your logs when you need them. Whether you're searching for "all errors in the last hour" or "logs containing the word 'timeout'", this service knows where to look.

**The secret sauce:**
- **Partition pruning** - we store logs in monthly partitions. Looking for last week's logs? We only search this month's partition, ignoring everything else
- **Smart indexes** - we use BRIN indexes that are tiny but super fast for time-series data
- **Redis cache** - frequently accessed metrics are cached so dashboards load instantly

Raw log queries (going to the database) typically take under 200ms. Cached metrics? Under 5ms.

### Analytics Workers - The Night Shift

**What they do:** While you sleep, these workers are calculating things like "how many errors happened in the last hour?" or "what are the top 10 most common errors this week?" They write results to Redis cache and PostgreSQL for fast dashboard queries.

**Why pre-compute?**
Running "count all errors in the last 24 hours" is slow if you're doing it live every time someone opens a dashboard. By pre-aggregating data hourly and caching results, your dashboard loads instantly. Aggregated metrics include exception counts, endpoint performance statistics, and log volume by type/level.

Think of it like a newspaper: instead of researching every story when someone buys a paper, we do the research ahead of time and print it. Much faster.

### Real-Time Notifications - The Alert System

**What they do:** Send instant error alerts to your browser the moment something goes wrong. No polling, no refresh - errors appear immediately.

**Here's how notifications flow:**

1. Error log arrives at Ingestion Service
2. Ingestion validates and queues it (normal flow)
3. Immediately publishes notification to Redis Pub/Sub channel `notifications:errors:{project_id}`
4. All Gateway instances subscribed to that channel receive it
5. Gateway streams it to connected browsers via Server-Sent Events (SSE)
6. Your dashboard shows an alert - typically within 30 milliseconds

**Why SSE instead of WebSockets?**
- Built into browsers (EventSource API)
- Automatic reconnection if connection drops
- Simpler for one-way server→client communication
- Works over regular HTTP/HTTPS (easier behind load balancers)

**Why Redis Pub/Sub?**
Redis acts as an event bus. When Ingestion publishes a notification, Redis broadcasts it to all subscribed Gateway instances. This means you can scale horizontally - run 10 Gateway instances, and they'll all receive and stream notifications to their connected clients.

**The trade-off:** Notifications are fire-and-forget. If you're not connected when an error occurs, you won't see that notification. That's by design - they're for instant awareness, not reliable delivery. Critical errors are still stored in the database for later review.

## How a Log Gets Stored

Let's follow one log from your application to the database:

**Step 1:** Your app calls `client.log.error("Payment failed")`

**Step 2:** SDK sends HTTP request to Gateway with your API key

**Step 3:** Gateway checks "is this API key valid?" - usually finds it cached in Redis (5ms)

**Step 4:** Gateway checks "has this project hit its rate limit?" - quick Redis counter check

**Step 5:** Gateway sends your log to Ingestion Service via gRPC (internal communication)

**Step 6:** Ingestion Service validates the log structure and adds metadata like a timestamp and error fingerprint

**Step 7:** If log is error/critical, publish notification to Redis Pub/Sub (microseconds, non-blocking)

**Step 8:** Log gets pushed to Redis queue (this takes microseconds)

**Step 9:** Gateway responds "202 Accepted" (your app can continue immediately)

**Step 10:** Connected browsers receive notification via SSE within 30ms

**Step 11:** Background worker pulls log from queue and writes to PostgreSQL with hundreds of other logs in one batch

**Total time to respond to your app:** Usually under 10ms. Your application doesn't wait for database writes or notification delivery.

## How You Get Logs Back

When you query for logs:

**Step 1:** Your request hits Gateway

**Step 2:** Gateway authenticates and forwards to Query Service

**Step 3:** Query Service looks at what you want:
- Metrics like "error rate"? Check Redis cache (instant)
- Specific logs? Query PostgreSQL with smart filtering

**Step 4:** Results come back to Gateway, then to you

**For metrics:** Usually under 5ms total
**For raw logs:** Usually under 200ms total

## Design Decisions Explained

### Why Microservices Instead of One Big Application?

**The restaurant analogy again:** Imagine if one chef had to take orders, cook every dish, and handle the register. They'd be overwhelmed. By having specialists (services), each can focus and scale independently.

**Real benefits:**
- **Ingestion** needs to be fast and handle spikes → optimized for speed
- **Queries** need to be accurate and flexible → optimized for search
- **Auth** needs to be secure and consistent → optimized for safety

If everything's in one app, you can't optimize for conflicting requirements.

**The trade-off:** More complexity in deployment and monitoring. We use Docker Compose to make this manageable.

### Why Two Separate Databases?

We use one PostgreSQL database for auth stuff (accounts, API keys) and another for logs.

**Auth database:**
- Small amount of data (thousands of records, not millions)
- Needs to be consistent (you don't want duplicate accounts)
- Critical for security (must backup regularly)
- Transactional workload (insert account, create project, etc.)

**Logs database:**
- Massive amount of data (millions or billions of logs)
- Can tolerate some eventual consistency
- Append-heavy (just writing, not updating)
- Uses time-partitioning for performance

Trying to optimize one database for both would make it worse at both jobs.

### Why gRPC Internally but REST Externally?

**For you (external):** We use REST with JSON because:
- Works everywhere (every language has HTTP libraries)
- Easy to test (just use curl)
- Readable (JSON is human-friendly)

**Internally between our services:** We use gRPC with Protocol Buffers because:
- About 2.5x smaller payloads than JSON (faster over the network)
- HTTP/2 under the hood (one connection, multiple requests)
- Strongly typed (our services have contracts)
- Built-in streaming support

It's about using the right tool for each job.

### Why Redis for So Many Things?

Redis is like a super-fast shared whiteboard for our services. We use it for:

**1. Caching API keys:** After validating once, we remember "this key is valid" for 5 minutes

**2. Rate limiting:** We count "project X made 500 requests this minute" using Redis counters that automatically expire

**3. Log queues:** Temporary buffer for logs before they're written to PostgreSQL

**4. Metrics cache:** Pre-computed dashboard numbers stored for instant access

**Why Redis?** It's in-memory (super fast), handles automatic expiration (we don't need to clean up), and supports atomic operations (perfect for counters and queues).

### Why Partition the Logs Table?

Without partitioning, querying old logs means scanning a table with billions of rows. Slow.

**With monthly partitions:**
- Query for "logs from last week"? Only scan this month's partition
- Drop logs older than 90 days? Drop three partition tables instantly (no DELETE needed)
- Smaller indexes per partition (faster inserts and queries)

Example: Searching for logs from yesterday without partitioning might scan 100 million rows. With partitioning? Maybe 3 million rows. That's a big difference.

## Keeping Things Reliable

### Circuit Breaker - The Safety Valve

Imagine Auth Service crashes. Without protection, every request would wait, timeout, and fail. Your entire platform would grind to a halt.

**Our circuit breaker:**
- **Normally (CLOSED):** Everything works fine
- **After failures (OPEN):** "Auth Service seems down, let's use emergency cache for a bit"
- **Testing recovery (HALF_OPEN):** "Let's try one request to see if it's back"

We keep an emergency cache in Redis with longer TTL (10 minutes instead of 5). When Auth Service is down, we serve from stale cache. Better to let valid API keys work with old data than to reject everything.

### Rate Limiting - The Traffic Cop

**Why limit requests?**
- Prevent one runaway client from affecting others
- Protect against DDoS attacks
- Enforce fair usage across projects

**How it works:**
We use Redis to count requests per minute and per hour. When you make a request:
1. Increment counter for "project_123:minute"
2. If it's the first request this minute, set expiration to 60 seconds
3. Check if count > 1,000 (default limit)
4. If yes, return 429 Too Many Requests
5. Same thing for hourly counter (default: 50,000/hour)

It's fast (Redis atomic operations) and automatically cleans up (counters expire).

### Backpressure - Knowing When to Say No

If your app suddenly sends 100,000 logs per second, our queue would fill up and we'd run out of memory.

**Our solution:** Monitor queue depth. When it hits 100,000 logs for your project:
- Return `503 Service Unavailable`
- Include `Retry-After: 60` header (suggesting when to try again)
- Your SDK automatically backs off and retries

This keeps the system healthy instead of crashing.

## Security by Design

### Network Isolation

**External world can access:** Only Gateway (port 8000)

**Everything else is internal:**
- Auth Service
- Ingestion Service
- Query Service
- Both PostgreSQL databases
- Redis

They communicate over Docker's internal network. Even if someone compromises your server, they can't directly access the databases or internal services.

### API Key Security

**What we DON'T do:** Store your API key in plain text
**What we DO:** Hash it with bcrypt (like passwords)

When you create an API key, we show it once. After that, it's hashed. When you send a request:
1. We hash your key
2. Look up the hash in our database
3. Cache the result (not the key itself)

If our database leaks, your keys aren't exposed in plain text.

## Performance Characteristics

Rather than just throwing numbers at you, here's what they mean in practice:

**"Gateway handles 10,000 requests/second"**
→ Your small app doing 10 requests/second? You're using 0.1% of capacity. Room to grow.

**"Cached auth validation: 5ms"**
→ Authentication adds almost no latency to your requests

**"Raw log queries: under 200ms"**
→ Fast enough for dashboards to feel instant to humans

**"Metrics queries: under 5ms"**
→ Pre-computed analytics load as fast as a static page

**"Cache hit rate: >95%"**
→ We're almost always serving from the fast path

## Scaling Strategy

### What Scales Horizontally (Add More Instances)

- **Gateway:** Add instances behind a load balancer
- **Auth Service:** Add instances (share same Redis cache)
- **Ingestion Service:** Add instances (share same Redis queue)
- **Query Service:** Add instances (all read-only)
- **Analytics Workers:** Distribute jobs across workers

All these services are stateless - they don't remember anything between requests. That makes them easy to scale.

### What Scales Vertically (Bigger Server)

- **PostgreSQL:** Currently handles thousands of queries/second on one instance. When needed, we can add read replicas for Query Service
- **Redis:** Currently handles hundreds of thousands of operations/second. Can switch to Redis Cluster if needed

### When to Scale

**You'll know you need more Gateway instances when:**
- CPU usage stays above 70%
- Response times creep up
- Request rates approaching 10,000/sec

**You'll know you need database scaling when:**
- Query times consistently over 500ms
- Connection pool saturation
- Disk I/O maxed out

## What's Next

We've built a solid foundation, but there's always room to grow:

- **Distributed tracing** to follow a request through all services
- **Alerting** to notify you when things go wrong
- **Anomaly detection** to catch weird patterns automatically
- **Hot/cold storage** to move old logs to cheaper storage
- **Compression** to reduce storage costs

The architecture is designed to support all of these without major rewrites.

## Resources

- **[API Reference](https://bump.sh/tuta-corp/doc/ledger-api/)** - Complete REST API documentation
- **[OpenAPI Spec](https://ledger-server.jtuta.cloud/openapi.json)** - Machine-readable API specification
- **[Services Guide](SERVICES.md)** - Deep dive into each service
- **[Main README](../README.md)** - Getting started

---

**Production Deployment:**
- **Server:** https://ledger-server.jtuta.cloud
- **Dashboard:** https://ledger.jtuta.cloud
- **GitHub:** https://github.com/JakubTuta/Ledger-APP
