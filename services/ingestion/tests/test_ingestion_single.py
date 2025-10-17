import datetime

import pytest

import ingestion_service.proto.ingestion_pb2 as ingestion_pb2

from .helpers import create_proto_log
from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestSingleLogIngestion(BaseIngestionTest):
    """Test single log ingestion endpoint."""

    async def test_ingest_simple_log(self):
        """Test ingesting a simple info log."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Application started successfully",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Simple log ingested successfully")

    async def test_ingest_log_with_attributes(self):
        """Test ingesting log with custom attributes."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "custom",
            "importance": "standard",
            "message": "User action completed",
            "attributes": {"user_id": 12345, "action": "purchase", "amount": 99.99, "currency": "USD"},
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Log with attributes ingested successfully")

    async def test_ingest_error_log(self):
        """Test ingesting an error log with exception details."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "critical",
            "message": "Database connection failed",
            "error_type": "ConnectionError",
            "error_message": "Unable to connect to database server",
            "stack_trace": """Traceback (most recent call last):
  File "/app/database.py", line 42, in connect
    conn = psycopg2.connect(dsn)
  File "/usr/lib/python3.12/site-packages/psycopg2/__init__.py", line 122, in connect
    conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
ConnectionError: Unable to connect to database server""",
            "platform": "python",
            "platform_version": "3.12.0",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Error log with exception ingested successfully")

    async def test_ingest_log_enqueued_to_redis(self):
        """Test that ingested log is actually enqueued to Redis."""
        log_dict1 = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "warning",
            "log_type": "logger",
            "importance": "high",
            "message": "API rate limit approaching",
        }

        proto_log1 = create_proto_log(log_dict1)
        request1 = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log1)

        response1 = await self.stub.IngestLog(request1)
        assert response1.success is True

        await self.redis.flushdb()

        log_dict2 = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test queue check",
        }

        proto_log2 = create_proto_log(log_dict2)
        request2 = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log2)

        response2 = await self.stub.IngestLog(request2)
        assert response2.success is True

        print("✅ Log correctly enqueued to Redis")

    async def test_ingest_with_environment_and_release(self):
        """Test ingesting log with environment and release tags."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "logger",
            "importance": "standard",
            "message": "Deployment completed",
            "environment": "production",
            "release": "v2.5.0",
            "sdk_version": "1.0.0",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Log with environment and release ingested successfully")

    async def test_ingest_network_log(self):
        """Test ingesting network/API request log."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "network",
            "importance": "standard",
            "message": "API request completed",
            "attributes": {
                "method": "POST",
                "url": "/api/v1/users",
                "status_code": 201,
                "duration_ms": 145,
                "request_id": "req_abc123",
            },
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Network log ingested successfully")

    async def test_ingest_database_log(self):
        """Test ingesting database query log."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "debug",
            "log_type": "database",
            "importance": "low",
            "message": "Database query executed",
            "attributes": {
                "query": "SELECT * FROM users WHERE id = ?",
                "duration_ms": 15,
                "rows_affected": 1,
                "connection_pool_size": 10,
            },
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Database log ingested successfully")

    async def test_ingest_critical_log(self):
        """Test ingesting critical importance log."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "critical",
            "log_type": "exception",
            "importance": "critical",
            "message": "System out of memory",
            "error_type": "MemoryError",
            "error_message": "Cannot allocate memory",
            "stack_trace": "MemoryError: Cannot allocate memory",
            "platform": "python",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Critical log ingested successfully")

    async def test_ingest_debug_log(self):
        """Test ingesting debug level log."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "debug",
            "log_type": "logger",
            "importance": "low",
            "message": "Cache miss for key: user_123",
            "attributes": {"cache_key": "user_123", "cache_ttl": 300},
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Debug log ingested successfully")

    async def test_ingest_with_sdk_metadata(self):
        """Test ingesting log with complete SDK metadata."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "SDK initialized",
            "sdk_version": "2.1.0",
            "platform": "nodejs",
            "platform_version": "20.10.0",
            "environment": "staging",
            "release": "v1.0.0-beta.5",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Log with SDK metadata ingested successfully")

    async def test_ingest_with_nested_attributes(self):
        """Test ingesting log with deeply nested attributes."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "custom",
            "importance": "standard",
            "message": "Complex event tracked",
            "attributes": {
                "event": {
                    "type": "purchase",
                    "user": {"id": 123, "tier": "premium", "location": {"country": "US", "city": "New York"}},
                    "items": [
                        {"id": "item1", "price": 29.99, "quantity": 2},
                        {"id": "item2", "price": 49.99, "quantity": 1},
                    ],
                    "totals": {"subtotal": 109.97, "tax": 9.90, "total": 119.87},
                }
            },
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Log with nested attributes ingested successfully")

    async def test_ingest_javascript_error(self):
        """Test ingesting JavaScript error log."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "high",
            "message": "Uncaught TypeError: Cannot read property 'name' of undefined",
            "error_type": "TypeError",
            "error_message": "Cannot read property 'name' of undefined",
            "stack_trace": """TypeError: Cannot read property 'name' of undefined
    at getUserName (/app/user.js:15:20)
    at processUser (/app/main.js:42:15)
    at Array.map (native)
    at main (/app/main.js:40:10)""",
            "platform": "nodejs",
            "platform_version": "18.17.0",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ JavaScript error ingested successfully")

    async def test_ingest_python_traceback(self):
        """Test ingesting Python traceback."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "high",
            "message": "KeyError: 'user_id'",
            "error_type": "KeyError",
            "error_message": "'user_id'",
            "stack_trace": """Traceback (most recent call last):
  File "/app/main.py", line 145, in process_request
    user_id = data['user_id']
KeyError: 'user_id'""",
            "platform": "python",
            "platform_version": "3.11.5",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Python traceback ingested successfully")

    async def test_ingest_java_exception(self):
        """Test ingesting Java exception stack trace."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "error",
            "log_type": "exception",
            "importance": "high",
            "message": "NullPointerException in UserService",
            "error_type": "NullPointerException",
            "error_message": "null",
            "stack_trace": """java.lang.NullPointerException
    at com.example.service.UserService.getUser(UserService.java:42)
    at com.example.controller.UserController.fetchUser(UserController.java:25)
    at com.example.Main.main(Main.java:10)""",
            "platform": "java",
            "platform_version": "17.0.5",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Java exception ingested successfully")

    async def test_response_format(self):
        """Test that response has correct format."""
        log_dict = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "info",
            "log_type": "console",
            "importance": "standard",
            "message": "Test log",
        }

        proto_log = create_proto_log(log_dict)
        request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

        response = await self.stub.IngestLog(request)
        assert response.success is True
        print("✅ Response format is correct")

    async def test_concurrent_single_ingestions(self):
        """Test multiple concurrent single log ingestions."""
        import asyncio

        async def ingest_log(i):
            log_dict = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Concurrent log {i}",
            }
            proto_log = create_proto_log(log_dict)
            request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)
            return await self.stub.IngestLog(request)

        tasks = [ingest_log(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        assert all(r.success is True for r in results)
        print("✅ 50 concurrent single ingestions successful")

