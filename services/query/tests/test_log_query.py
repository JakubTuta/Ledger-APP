import datetime
import json

import pytest

import query_service.models as models
import query_service.proto.query_pb2 as query_pb2
import tests.test_base as test_base


class TestLogQuery(test_base.BaseQueryTest):
    async def create_test_log(
        self,
        project_id: int,
        level: str = "info",
        log_type: str = "logger",
        message: str = "Test log",
        timestamp: datetime.datetime | None = None,
        **kwargs,
    ) -> models.Log:
        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)

        log = models.Log(
            project_id=project_id,
            timestamp=timestamp,
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            level=level,
            log_type=log_type,
            importance="standard",
            message=message,
            **kwargs,
        )

        async with self.test_db_manager.session_factory() as session:
            session.add(log)
            await session.commit()
            await session.refresh(log)
            return log

    @pytest.mark.asyncio
    async def test_query_logs_basic(self):
        await self.create_test_log(project_id=1, message="Log 1")
        await self.create_test_log(project_id=1, message="Log 2")
        await self.create_test_log(project_id=2, message="Log 3")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 2
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_query_logs_with_level_filter(self):
        await self.create_test_log(project_id=1, level="info", message="Info log")
        await self.create_test_log(project_id=1, level="error", message="Error log 1")
        await self.create_test_log(project_id=1, level="error", message="Error log 2")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            level="error",
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 2
        assert all(log.level == "error" for log in response.logs)

    @pytest.mark.asyncio
    async def test_query_logs_with_log_type_filter(self):
        await self.create_test_log(project_id=1, log_type="logger", message="Logger")
        await self.create_test_log(project_id=1, log_type="exception", message="Exception 1")
        await self.create_test_log(project_id=1, log_type="exception", message="Exception 2")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            log_type="exception",
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 2
        assert all(log.log_type == "exception" for log in response.logs)

    @pytest.mark.asyncio
    async def test_query_logs_with_time_range(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        one_hour_ago = now - datetime.timedelta(hours=1)
        two_hours_ago = now - datetime.timedelta(hours=2)

        await self.create_test_log(project_id=1, timestamp=two_hours_ago, message="Old log")
        await self.create_test_log(project_id=1, timestamp=one_hour_ago, message="Recent log")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            start_time=one_hour_ago.isoformat(),
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 1
        assert response.logs[0].message == "Recent log"

    @pytest.mark.asyncio
    async def test_query_logs_pagination(self):
        for i in range(5):
            await self.create_test_log(project_id=1, message=f"Log {i}")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            limit=2,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 2
        assert response.has_more is True

        request.offset = 2
        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 2
        assert response.has_more is True

        request.offset = 4
        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 1
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_query_logs_with_environment_filter(self):
        await self.create_test_log(project_id=1, environment="production", message="Prod log")
        await self.create_test_log(project_id=1, environment="staging", message="Staging log")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            environment="production",
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 1
        assert response.logs[0].environment == "production"

    @pytest.mark.asyncio
    async def test_query_logs_with_error_fingerprint(self):
        fingerprint = "abc123def456"
        await self.create_test_log(
            project_id=1,
            error_fingerprint=fingerprint,
            message="Error with fingerprint",
        )
        await self.create_test_log(project_id=1, message="Error without fingerprint")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            error_fingerprint=fingerprint,
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 1
        assert response.logs[0].error_fingerprint == fingerprint

    @pytest.mark.asyncio
    async def test_query_logs_empty_result(self):
        request = query_pb2.QueryLogsRequest(
            project_id=999,
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 0
        assert response.total == 0
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_get_log_by_id(self):
        log = await self.create_test_log(project_id=1, message="Test log")

        request = query_pb2.GetLogRequest(
            log_id=log.id,
            project_id=1,
        )

        response = await self.stub.GetLog(request)

        assert response.found is True
        assert response.log.id == log.id
        assert response.log.message == "Test log"

    @pytest.mark.asyncio
    async def test_get_log_not_found(self):
        request = query_pb2.GetLogRequest(
            log_id=999999,
            project_id=1,
        )

        response = await self.stub.GetLog(request)

        assert response.found is False

    @pytest.mark.asyncio
    async def test_get_log_wrong_project(self):
        log = await self.create_test_log(project_id=1, message="Test log")

        request = query_pb2.GetLogRequest(
            log_id=log.id,
            project_id=2,
        )

        response = await self.stub.GetLog(request)

        assert response.found is False

    @pytest.mark.asyncio
    async def test_query_logs_with_attributes(self):
        attributes = {"user_id": "usr_123", "request_id": "req_abc"}
        log = await self.create_test_log(
            project_id=1,
            message="Log with attributes",
            attributes=attributes,
        )

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 1
        returned_attributes = json.loads(response.logs[0].attributes)
        assert returned_attributes == attributes

    @pytest.mark.asyncio
    async def test_query_logs_ordering(self):
        now = datetime.datetime.now(datetime.timezone.utc)

        await self.create_test_log(
            project_id=1,
            timestamp=now - datetime.timedelta(minutes=2),
            message="First log",
        )
        await self.create_test_log(
            project_id=1,
            timestamp=now - datetime.timedelta(minutes=1),
            message="Second log",
        )
        await self.create_test_log(
            project_id=1,
            timestamp=now,
            message="Third log",
        )

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            limit=10,
            offset=0,
        )

        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 3
        assert response.logs[0].message == "Third log"
        assert response.logs[1].message == "Second log"
        assert response.logs[2].message == "First log"

    @pytest.mark.asyncio
    async def test_query_logs_cursor_pagination_no_skips_or_dupes(self):
        for i in range(5):
            await self.create_test_log(project_id=1, message=f"Log {i}")

        seen_ids: list[int] = []
        cursor = ""
        for _ in range(10):  # bounded loop guard, real termination is has_more
            request = query_pb2.QueryLogsRequest(project_id=1, limit=2)
            if cursor:
                request.cursor = cursor
            response = await self.stub.QueryLogs(request)
            seen_ids.extend(log.id for log in response.logs)
            if not response.has_more:
                break
            cursor = response.next_cursor

        assert len(seen_ids) == 5
        assert len(set(seen_ids)) == 5  # no duplicates across pages

    @pytest.mark.asyncio
    async def test_query_logs_cursor_pagination_stable_across_duplicate_timestamps(self):
        # All logs share the exact same timestamp - the id tiebreaker in the
        # ORDER BY / cursor comparison is what keeps pagination stable here;
        # without it, plain "ORDER BY timestamp DESC" ties could reshuffle
        # rows between pages.
        shared_ts = datetime.datetime.now(datetime.timezone.utc)
        for i in range(4):
            await self.create_test_log(project_id=1, timestamp=shared_ts, message=f"Log {i}")

        request = query_pb2.QueryLogsRequest(project_id=1, limit=2)
        first_page = await self.stub.QueryLogs(request)
        assert len(first_page.logs) == 2
        assert first_page.has_more is True
        assert first_page.next_cursor

        request2 = query_pb2.QueryLogsRequest(project_id=1, limit=2, cursor=first_page.next_cursor)
        second_page = await self.stub.QueryLogs(request2)
        assert len(second_page.logs) == 2
        assert second_page.has_more is False

        first_ids = {log.id for log in first_page.logs}
        second_ids = {log.id for log in second_page.logs}
        assert first_ids.isdisjoint(second_ids)
        assert first_ids | second_ids == {1, 2, 3, 4}

    @pytest.mark.asyncio
    async def test_query_logs_cursor_takes_precedence_over_offset(self):
        for i in range(5):
            await self.create_test_log(project_id=1, message=f"Log {i}")

        first_page = await self.stub.QueryLogs(query_pb2.QueryLogsRequest(project_id=1, limit=2))

        # offset=0 would normally restart from the top; cursor must win.
        request = query_pb2.QueryLogsRequest(
            project_id=1, limit=2, offset=0, cursor=first_page.next_cursor
        )
        response = await self.stub.QueryLogs(request)

        first_ids = {log.id for log in first_page.logs}
        second_ids = {log.id for log in response.logs}
        assert first_ids.isdisjoint(second_ids)
