# Ledger API Reference

## Overview

This document provides complete documentation for the Ledger REST API. Use these endpoints to send logs, query data, and manage your account.

**Base URL**: `http://localhost:8000/api/v1`

**API Version**: 1.0.0

---

## Table of Contents

1. [Health Endpoints](#health-endpoints)
2. [Authentication Endpoints](#authentication-endpoints)
3. [Project Management Endpoints](#project-management-endpoints)
4. [API Key Management Endpoints](#api-key-management-endpoints)
5. [Dashboard Panel Management Endpoints](#dashboard-panel-management-endpoints)
6. [Log Ingestion Endpoints](#log-ingestion-endpoints)
7. [Common Response Codes](#common-response-codes)
8. [Error Handling](#error-handling)
9. [Rate Limiting](#rate-limiting)

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

**Description:** Create a new user account. Returns an access token for immediate use, eliminating the need for a separate login call.

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
  "access_token": "token_1_user@example.com",
  "token_type": "bearer",
  "account_id": 1,
  "email": "user@example.com",
  "name": "John Doe",
  "expires_in": 3600,
  "message": "Account created successfully"
}
```

**Response Fields:**
- `access_token` (string): JWT token for authentication (valid for 3600 seconds)
- `token_type` (string): Always "bearer"
- `account_id` (integer): Unique account identifier
- `email` (string): Registered email address (lowercase)
- `name` (string): User's full name
- `expires_in` (integer): Token expiration time in seconds (1 hour)
- `message` (string): Success message

**Status Codes:**
- `201 Created` - Account created successfully with access token
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

## Dashboard Panel Management Endpoints

### Get Dashboard Panels

**Endpoint:** `GET /api/v1/dashboard/panels`

**Description:** Retrieve all dashboard panels for the authenticated user. Dashboard panels allow users to customize their dashboard view with filtered and aggregated data from different projects.

**Authentication:** Required (API Key)

**Request Headers:**
```
Authorization: Bearer <api_key>
```

**Response:**

```json
{
  "panels": [
    {
      "id": "panel_a1b2c3d4e5f6g7h8",
      "name": "Project A Logs",
      "index": 0,
      "project_id": "project-a",
      "time_range_from": "2025-10-01T00:00:00Z",
      "time_range_to": "2025-10-30T23:59:59Z",
      "type": "logs"
    },
    {
      "id": "panel_b2c3d4e5f6g7h8i9",
      "name": "Error Dashboard",
      "index": 1,
      "project_id": "project-b",
      "time_range_from": "2025-10-15T00:00:00Z",
      "time_range_to": "2025-10-30T23:59:59Z",
      "type": "errors"
    }
  ],
  "total": 2
}
```

**Panel Fields:**
- `id` (string): Unique panel identifier
- `name` (string): User-defined panel name
- `index` (integer): Display order (0-based)
- `project_id` (string): Associated project identifier
- `time_range_from` (string): Start of time range (ISO 8601)
- `time_range_to` (string): End of time range (ISO 8601)
- `type` (string): Panel type - `logs`, `errors`, or `metrics`

**Caching:**
- Panel data is cached in Redis for 5 minutes
- Cache is automatically invalidated on create/update/delete operations

**Status Codes:**
- `200 OK` - Panels retrieved successfully
- `401 Unauthorized` - Not authenticated
- `404 Not Found` - Dashboard not found (rare - auto-created on first access)
- `500 Internal Server Error` - Failed to retrieve panels
- `503 Service Unavailable` - Service timeout

---

### Create Dashboard Panel

**Endpoint:** `POST /api/v1/dashboard/panels`

**Description:** Create a new dashboard panel for the authenticated user.

**Authentication:** Required (API Key)

**Request Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**

```json
{
  "name": "Error Dashboard",
  "index": 1,
  "project_id": "project-b",
  "time_range_from": "2025-10-15T00:00:00Z",
  "time_range_to": "2025-10-30T23:59:59Z",
  "type": "errors"
}
```

**Field Requirements:**
- `name` (string, required): 1-255 characters, descriptive panel name
- `index` (integer, required): Display order, must be >= 0
- `project_id` (string, required): Valid project identifier
- `time_range_from` (string, required): ISO 8601 timestamp
- `time_range_to` (string, required): ISO 8601 timestamp
- `type` (string, required): Must be one of `logs`, `errors`, `metrics`

**Response:**

```json
{
  "id": "panel_b2c3d4e5f6g7h8i9",
  "name": "Error Dashboard",
  "index": 1,
  "project_id": "project-b",
  "time_range_from": "2025-10-15T00:00:00Z",
  "time_range_to": "2025-10-30T23:59:59Z",
  "type": "errors"
}
```

**Status Codes:**
- `201 Created` - Panel created successfully
- `400 Bad Request` - Invalid panel data
- `401 Unauthorized` - Not authenticated
- `500 Internal Server Error` - Failed to create panel
- `503 Service Unavailable` - Service timeout

---

### Update Dashboard Panel

**Endpoint:** `PUT /api/v1/dashboard/panels/{panel_id}`

**Description:** Update an existing dashboard panel for the authenticated user.

**Authentication:** Required (API Key)

**Request Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Path Parameters:**
- `panel_id` (string, required): The panel ID to update

**Request Body:**

```json
{
  "name": "Updated Panel Name",
  "index": 0,
  "project_id": "project-a",
  "time_range_from": "2025-10-01T00:00:00Z",
  "time_range_to": "2025-10-30T23:59:59Z",
  "type": "metrics"
}
```

**Field Requirements:**
- Same as Create Dashboard Panel (all fields required)

**Response:**

```json
{
  "id": "panel_a1b2c3d4e5f6g7h8",
  "name": "Updated Panel Name",
  "index": 0,
  "project_id": "project-a",
  "time_range_from": "2025-10-01T00:00:00Z",
  "time_range_to": "2025-10-30T23:59:59Z",
  "type": "metrics"
}
```

**Status Codes:**
- `200 OK` - Panel updated successfully
- `400 Bad Request` - Invalid panel data
- `401 Unauthorized` - Not authenticated
- `404 Not Found` - Panel not found
- `500 Internal Server Error` - Failed to update panel
- `503 Service Unavailable` - Service timeout

---

### Delete Dashboard Panel

**Endpoint:** `DELETE /api/v1/dashboard/panels/{panel_id}`

**Description:** Delete a dashboard panel for the authenticated user.

**Authentication:** Required (API Key)

**Request Headers:**
```
Authorization: Bearer <api_key>
```

**Path Parameters:**
- `panel_id` (string, required): The panel ID to delete

**Response:**

```json
{
  "success": true,
  "message": "Panel panel_a1b2c3d4e5f6g7h8 deleted successfully"
}
```

**Status Codes:**
- `200 OK` - Panel deleted successfully
- `401 Unauthorized` - Not authenticated
- `404 Not Found` - Panel not found
- `500 Internal Server Error` - Failed to delete panel
- `503 Service Unavailable` - Service timeout

---

## Log Ingestion Endpoints

### Ingest Single Log

**Endpoint:** `POST /api/v1/ingest/single`

**Description:** Ingest a single log entry into the system. Logs are queued for asynchronous processing.

**Authentication:** Required (API Key)

**Request Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**

```json
{
  "timestamp": "2025-10-17T10:00:00Z",
  "level": "info",
  "log_type": "console",
  "importance": "standard",
  "message": "Application started successfully",
  "environment": "production",
  "release": "v1.2.3",
  "sdk_version": "1.0.0",
  "platform": "python",
  "platform_version": "3.12.0",
  "attributes": {
    "user_id": "123",
    "request_id": "req_abc"
  }
}
```

**Field Requirements:**
- `timestamp` (string, required): ISO 8601 format timestamp
- `level` (string, required): One of `debug`, `info`, `warning`, `error`, `critical`
- `log_type` (string, required): One of `console`, `logger`, `exception`, `custom`
- `importance` (string, required): One of `low`, `standard`, `high`
- `message` (string, optional): Log message (max 10,000 characters)
- `error_type` (string, optional): Error class name for exceptions
- `error_message` (string, optional): Error message (max 5,000 characters)
- `stack_trace` (string, optional): Stack trace (max 50,000 characters)
- `environment` (string, optional): e.g., `production`, `staging`, `dev`
- `release` (string, optional): Release version
- `sdk_version` (string, optional): SDK version
- `platform` (string, optional): Platform name (e.g., `python`, `node`, `java`)
- `platform_version` (string, optional): Platform version
- `attributes` (object, optional): Custom attributes (max 100KB serialized)

**Response:**

```json
{
  "accepted": 1,
  "rejected": 0,
  "message": "Log accepted for processing"
}
```

**Status Codes:**
- `202 Accepted` - Log queued for processing
- `400 Bad Request` - Invalid log entry
- `401 Unauthorized` - Missing or invalid API key
- `429 Too Many Requests` - Rate limit exceeded
- `503 Service Unavailable` - Queue full (includes `Retry-After: 60` header)

---

### Ingest Log Batch

**Endpoint:** `POST /api/v1/ingest/batch`

**Description:** Ingest multiple log entries in a single request for better performance.

**Authentication:** Required (API Key)

**Request Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**

```json
{
  "logs": [
    {
      "timestamp": "2025-10-17T10:00:00Z",
      "level": "info",
      "log_type": "console",
      "importance": "standard",
      "message": "Request started"
    },
    {
      "timestamp": "2025-10-17T10:00:01Z",
      "level": "error",
      "log_type": "exception",
      "importance": "high",
      "message": "Database connection failed",
      "error_type": "ConnectionError",
      "error_message": "Failed to connect to database",
      "stack_trace": "Traceback (most recent call last):\n  File app.py, line 42"
    }
  ]
}
```

**Field Requirements:**
- `logs` (array, required): Array of log objects (max 1,000 logs per batch)
- Each log object follows the same schema as single log ingestion

**Response:**

```json
{
  "accepted": 98,
  "rejected": 2,
  "errors": [
    "Log 5: Invalid timestamp format",
    "Log 12: Message exceeds maximum length"
  ]
}
```

**Response Fields:**
- `accepted` (integer): Number of logs successfully queued
- `rejected` (integer): Number of logs that failed validation
- `errors` (array, nullable): Error messages for rejected logs

**Status Codes:**
- `202 Accepted` - Batch processed (may include partial failures)
- `400 Bad Request` - Empty batch or all logs invalid
- `401 Unauthorized` - Missing or invalid API key
- `429 Too Many Requests` - Rate limit exceeded
- `503 Service Unavailable` - Queue full (includes `Retry-After: 60` header)

---

### Get Queue Depth

**Endpoint:** `GET /api/v1/queue/depth`

**Description:** Get the current queue depth for your project. Useful for monitoring backpressure.

**Authentication:** Required (API Key)

**Request Headers:**
```
Authorization: Bearer <api_key>
```

**Response:**

```json
{
  "project_id": 1,
  "queue_depth": 1500
}
```

**Response Fields:**
- `project_id` (integer): Your project ID
- `queue_depth` (integer): Number of logs currently queued for processing

**Status Codes:**
- `200 OK` - Queue depth retrieved successfully
- `401 Unauthorized` - Missing or invalid API key
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Failed to retrieve queue depth

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

Used for log ingestion endpoints:

**Header:**
```
Authorization: Bearer ldg_proj_1_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
```

**Applies to:**
- `/api/v1/ingest/single` (ingest single log)
- `/api/v1/ingest/batch` (ingest batch logs)
- `/api/v1/queue/depth` (get queue depth)

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

**Response includes an `access_token`** - no separate login needed!

```json
{
  "access_token": "token_1_user@example.com",
  "token_type": "bearer",
  "account_id": 1,
  "email": "user@example.com",
  "name": "John Doe",
  "expires_in": 3600,
  "message": "Account created successfully"
}
```

#### 2. (Optional) Login for existing accounts

Only needed if you already have an account:

```bash
curl -X POST http://localhost:8000/api/v1/accounts/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }'
```

Save the `access_token` from either the registration or login response.

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

#### 8. Use the API key to ingest logs

```bash
# Ingest a single log
curl -X POST http://localhost:8000/api/v1/ingest/single \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2025-10-17T10:00:00Z",
    "level": "info",
    "log_type": "console",
    "importance": "standard",
    "message": "Application started"
  }'

# Ingest a batch of logs
curl -X POST http://localhost:8000/api/v1/ingest/batch \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      {
        "timestamp": "2025-10-17T10:00:00Z",
        "level": "info",
        "log_type": "console",
        "importance": "standard",
        "message": "Request received"
      },
      {
        "timestamp": "2025-10-17T10:00:01Z",
        "level": "info",
        "log_type": "console",
        "importance": "standard",
        "message": "Request processed"
      }
    ]
  }'

# Check queue depth
curl -X GET http://localhost:8000/api/v1/queue/depth \
  -H "Authorization: Bearer <api_key>"
```

#### 9. Logout

```bash
curl -X POST http://localhost:8000/api/v1/accounts/logout \
  -H "Authorization: Bearer <access_token>"
```

---

## Additional Resources

- **[Architecture Guide](ARCHITECTURE.md)** - System design and service overview
- **[Services Guide](SERVICES.md)** - Detailed information about each service
- **[Main README](../README.md)** - Getting started and quick start guide

---

## Need Help?

- Check the [README](../README.md) for getting started
- Review the [Architecture Guide](ARCHITECTURE.md) for system design
- See [Services Guide](SERVICES.md) for service details
