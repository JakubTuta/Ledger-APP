# REST API Endpoints Documentation

## Overview

This document provides comprehensive documentation for the Ledger Gateway Service REST API. All endpoints are exposed through the Gateway Service running on port 8000.

**Base URL:** `http://localhost:8000/api/v1`

**API Version:** 1.0.0

---

## Table of Contents

1. [Health Endpoints](#health-endpoints)
2. [Authentication Endpoints](#authentication-endpoints)
3. [Project Management Endpoints](#project-management-endpoints)
4. [API Key Management Endpoints](#api-key-management-endpoints)
5. [Common Response Codes](#common-response-codes)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)

---

## Health Endpoints

### Basic Health Check

**Endpoint:** `GET /health`

**Description:** Check if the gateway service is running.

**Authentication:** Not required

**Response:**

```json
{
  "status": "healthy"
}
```

**Status Codes:**
- `200 OK` - Service is healthy

---

### Deep Health Check

**Endpoint:** `GET /health/deep`

**Description:** Check the health of gateway service and all dependencies (Redis, gRPC connections).

**Authentication:** Not required

**Response:**

```json
{
  "status": "healthy",
  "services": {
    "redis": "healthy",
    "grpc": {
      "auth": {
        "active_channels": 10,
        "calls_succeeded": 1234,
        "calls_failed": 5
      }
    }
  }
}
```

**Status Codes:**
- `200 OK` - All services healthy or degraded status returned

---

## Authentication Endpoints

### Register Account

**Endpoint:** `POST /api/v1/accounts/register`

**Description:** Create a new user account.

**Authentication:** Not required

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "name": "John Doe"
}
```

**Field Requirements:**
- `email` (string, required): Valid email format, max 255 characters
  - Must start and end with alphanumeric characters
  - Cannot contain consecutive dots
  - Automatically converted to lowercase
- `password` (string, required): 8-64 characters
  - Must contain at least one uppercase letter
  - Must contain at least one lowercase letter
  - Must contain at least one digit
- `name` (string, required): 1-255 characters

**Response:**

```json
{
  "account_id": 1,
  "email": "user@example.com",
  "name": "John Doe",
  "message": "Account created successfully"
}
```

**Status Codes:**
- `201 Created` - Account created successfully
- `400 Bad Request` - Invalid input (validation failed)
- `409 Conflict` - Email already registered
- `500 Internal Server Error` - Registration failed
- `503 Service Unavailable` - Service timeout

---

### Login

**Endpoint:** `POST /api/v1/accounts/login`

**Description:** Authenticate with email and password to receive a JWT access token.

**Authentication:** Not required

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123"
}
```

**Field Requirements:**
- `email` (string, required): Valid email, max 255 characters
- `password` (string, required): 8-64 characters

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "account_id": 1,
  "email": "user@example.com",
  "expires_in": 3600
}
```

**Status Codes:**
- `200 OK` - Login successful
- `401 Unauthorized` - Invalid credentials
- `500 Internal Server Error` - Login failed
- `503 Service Unavailable` - Service timeout

---

### Logout

**Endpoint:** `POST /api/v1/accounts/logout`

**Description:** Invalidate the current JWT token.

**Authentication:** Required (JWT Bearer token)

**Request Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```
No content (204)
```

**Status Codes:**
- `204 No Content` - Logout successful
- `401 Unauthorized` - Not authenticated or invalid token
- `500 Internal Server Error` - Logout failed

---

### Get Current Account

**Endpoint:** `GET /api/v1/accounts/me`

**Description:** Get account details for the authenticated user.

**Authentication:** Required (JWT Bearer token)

**Request Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**

```json
{
  "account_id": 1,
  "email": "user@example.com",
  "name": "John Doe",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**Status Codes:**
- `200 OK` - Account details retrieved
- `401 Unauthorized` - Not authenticated
- `404 Not Found` - Account not found
- `500 Internal Server Error` - Failed to fetch account
- `503 Service Unavailable` - Service timeout

---

## Project Management Endpoints

### Create Project

**Endpoint:** `POST /api/v1/projects`

**Description:** Create a new project for the authenticated account.

**Authentication:** Required (JWT Bearer token)

**Request Headers:**
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "name": "My Production App",
  "slug": "my-prod-app",
  "environment": "production"
}
```

**Field Requirements:**
- `name` (string, required): 1-255 characters, project display name
- `slug` (string, required): 1-255 characters
  - Must match pattern: `^[a-z0-9-]+$` (lowercase alphanumeric and hyphens only)
  - Automatically converted to lowercase
  - Used in URLs and API calls
- `environment` (string, optional): One of `production`, `staging`, `dev` (default: `production`)

**Response:**

```json
{
  "project_id": 1,
  "name": "My Production App",
  "slug": "my-prod-app",
  "environment": "production",
  "retention_days": 30,
  "daily_quota": 1000000
}
```

**Status Codes:**
- `201 Created` - Project created successfully
- `400 Bad Request` - Invalid input
- `401 Unauthorized` - Not authenticated
- `409 Conflict` - Project slug already exists
- `500 Internal Server Error` - Failed to create project
- `503 Service Unavailable` - Service timeout

---

### List Projects

**Endpoint:** `GET /api/v1/projects`

**Description:** Get all projects for the authenticated account.

**Authentication:** Required (JWT Bearer token)

**Request Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**

```json
{
  "projects": [
    {
      "project_id": 1,
      "name": "My Production App",
      "slug": "my-prod-app",
      "environment": "production",
      "retention_days": 30,
      "daily_quota": 1000000
    },
    {
      "project_id": 2,
      "name": "Staging Environment",
      "slug": "staging-env",
      "environment": "staging",
      "retention_days": 7,
      "daily_quota": 100000
    }
  ],
  "total": 2
}
```

**Status Codes:**
- `200 OK` - Projects retrieved successfully
- `401 Unauthorized` - Not authenticated
- `500 Internal Server Error` - Failed to list projects
- `503 Service Unavailable` - Service timeout

---

### Get Project by Slug

**Endpoint:** `GET /api/v1/projects/{project_slug}`

**Description:** Get project details by slug for the authenticated account.

**Authentication:** Required (JWT Bearer token)

**Request Headers:**
```
Authorization: Bearer <access_token>
```

**Path Parameters:**
- `project_slug` (string, required): The project slug (e.g., `my-prod-app`)

**Response:**

```json
{
  "project_id": 1,
  "name": "My Production App",
  "slug": "my-prod-app",
  "environment": "production",
  "retention_days": 30,
  "daily_quota": 1000000
}
```

**Status Codes:**
- `200 OK` - Project found and returned
- `401 Unauthorized` - Not authenticated
- `404 Not Found` - Project not found or doesn't belong to account
- `500 Internal Server Error` - Failed to get project
- `503 Service Unavailable` - Service timeout

---

## API Key Management Endpoints

### Create API Key

**Endpoint:** `POST /api/v1/projects/{project_id}/api-keys`

**Description:** Create a new API key for a project. The full API key is only shown once.

**Authentication:** Required (JWT Bearer token)

**Request Headers:**
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Path Parameters:**
- `project_id` (integer, required): The project ID to create the API key for

**Request Body:**

```json
{
  "name": "Production API Key"
}
```

**Field Requirements:**
- `name` (string, required): 1-255 characters, descriptive name for the API key

**Response:**

```json
{
  "key_id": 1,
  "full_key": "ldg_proj_1_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
  "key_prefix": "ldg_proj_1_a1b2c3",
  "warning": "Save this key now! It will not be shown again."
}
```

**Important Notes:**
- The `full_key` is only returned once during creation
- Store the key securely - it cannot be retrieved later
- The `key_prefix` can be used to identify the key in logs and UI
- Default rate limits: 1,000 requests/minute, 50,000 requests/hour

**Status Codes:**
- `201 Created` - API key created successfully
- `401 Unauthorized` - Not authenticated
- `403 Forbidden` - User doesn't own this project
- `404 Not Found` - Project not found
- `500 Internal Server Error` - Failed to create API key
- `503 Service Unavailable` - Service timeout

---

### Revoke API Key

**Endpoint:** `DELETE /api/v1/api-keys/{key_id}`

**Description:** Revoke an API key. This action cannot be undone.

**Authentication:** Required (JWT Bearer token)

**Request Headers:**
```
Authorization: Bearer <access_token>
```

**Path Parameters:**
- `key_id` (integer, required): The API key ID to revoke

**Response:**

```json
{
  "success": true,
  "message": "API key 1 has been revoked"
}
```

**Status Codes:**
- `200 OK` - API key revoked successfully
- `401 Unauthorized` - Not authenticated
- `403 Forbidden` - User doesn't own this API key
- `404 Not Found` - API key not found
- `500 Internal Server Error` - Failed to revoke API key
- `503 Service Unavailable` - Service timeout

---

## Common Response Codes

| Status Code | Description |
|------------|-------------|
| `200 OK` | Request successful |
| `201 Created` | Resource created successfully |
| `204 No Content` | Request successful, no content returned |
| `400 Bad Request` | Invalid request body or parameters |
| `401 Unauthorized` | Authentication required or invalid credentials |
| `403 Forbidden` | Authenticated but not authorized for this action |
| `404 Not Found` | Resource not found |
| `409 Conflict` | Resource already exists (e.g., duplicate email or slug) |
| `429 Too Many Requests` | Rate limit exceeded |
| `500 Internal Server Error` | Server error occurred |
| `503 Service Unavailable` | Service temporarily unavailable or timeout |

---

## Error Handling

All error responses follow a consistent format:

```json
{
  "detail": "Human-readable error message"
}
```

Examples:

**Validation Error (400):**
```json
{
  "detail": "Password must contain uppercase letter"
}
```

**Authentication Error (401):**
```json
{
  "detail": "Invalid email or password"
}
```

**Rate Limit Error (429):**
```json
{
  "detail": "Rate limit exceeded: 1000 requests per minute"
}
```

**Server Error (500):**
```json
{
  "detail": "Failed to create project"
}
```

---

## Rate Limiting

### Default Rate Limits

All API endpoints are subject to rate limiting:

- **Per-Minute Limit:** 1,000 requests
- **Per-Hour Limit:** 50,000 requests

Rate limits are enforced per API key for authenticated requests.

### Rate Limit Headers

The API returns rate limit information in response headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1642345678
```

### Rate Limit Response

When rate limit is exceeded, the API returns:

**Status Code:** `429 Too Many Requests`

**Response:**
```json
{
  "detail": "Rate limit exceeded: 1000 requests per minute"
}
```

### Middleware Stack

All requests pass through the following middleware layers:

1. **CORS Middleware** - Cross-origin resource sharing
2. **Circuit Breaker Middleware** - Fault tolerance with emergency cache fallback
3. **Rate Limit Middleware** - Sliding window rate limiting with Redis
4. **Auth Middleware** - JWT/API key validation with Redis caching

---

## Authentication Methods

### JWT Bearer Token (User Authentication)

Used for user account management endpoints:

**Header:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Applies to:**
- `/api/v1/accounts/logout`
- `/api/v1/accounts/me`
- `/api/v1/projects` (all project endpoints)
- `/api/v1/projects/{project_id}/api-keys` (create API key)
- `/api/v1/api-keys/{key_id}` (revoke API key)

**Token Lifetime:** 3600 seconds (1 hour)

### API Key (Service Authentication)

Used for log ingestion and service-to-service communication (future phases):

**Header:**
```
X-API-Key: ldg_proj_1_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
```

**Features:**
- Per-key rate limiting
- Project-scoped access
- Redis-cached validation (5-minute TTL)
- Index-only database scans for performance

---

## Performance Characteristics

### Latency Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Gateway p99 latency | <50ms | With cached auth |
| API key validation | ~5ms | Redis cached (95% hit rate) |
| Rate limit check | <1ms | Redis atomic operations |
| Throughput | 10K RPS | Per Gateway instance |

### Caching Strategy

- **API Key Cache:** 5-minute TTL in Redis
- **Emergency Cache:** 10-minute fallback during circuit breaker open state
- **Session Cache:** 1-hour TTL for JWT tokens

### Connection Pooling

- **gRPC Channels:** 10 persistent channels with keepalive
- **Redis Pool:** 50 connections maximum

---

## Example Usage

### Complete User Flow

#### 1. Register a new account

```bash
curl -X POST http://localhost:8000/api/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123",
    "name": "John Doe"
  }'
```

#### 2. Login to get access token

```bash
curl -X POST http://localhost:8000/api/v1/accounts/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }'
```

Save the `access_token` from the response.

#### 3. Create a project

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Production App",
    "slug": "my-prod-app",
    "environment": "production"
  }'
```

Save the `project_id` from the response.

#### 4. Create an API key for the project

```bash
curl -X POST http://localhost:8000/api/v1/projects/1/api-keys \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key"
  }'
```

**Important:** Save the `full_key` immediately - it won't be shown again!

#### 5. List all projects

```bash
curl -X GET http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer <access_token>"
```

#### 6. Get specific project

```bash
curl -X GET http://localhost:8000/api/v1/projects/my-prod-app \
  -H "Authorization: Bearer <access_token>"
```

#### 7. Revoke an API key

```bash
curl -X DELETE http://localhost:8000/api/v1/api-keys/1 \
  -H "Authorization: Bearer <access_token>"
```

#### 8. Logout

```bash
curl -X POST http://localhost:8000/api/v1/accounts/logout \
  -H "Authorization: Bearer <access_token>"
```

---

## Additional Resources

- **Architecture Documentation:** See `project_overview/ARCHITECTURE.md`
- **Gateway Service Details:** See `project_overview/GATEWAY_SERVICE.md`
- **Database Schema:** See `project_overview/DATABASE_SCHEMA.md`
- **Performance Optimization:** See `project_overview/OPTIMIZATION.md`

---

## Support

For issues or questions, please refer to the project README or create an issue in the repository.
