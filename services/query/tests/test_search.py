import datetime

import pytest

import query_service.models as models
import query_service.proto.query_pb2 as query_pb2
import tests.test_base as test_base


class TestLogSearch(test_base.BaseQueryTest):
    async def create_test_log(
        self,
        project_id: int,
        level: str = "info",
        log_type: str = "logger",
        message: str = "Test log",
        error_type: str | None = None,
        error_message: str | None = None,
        **kwargs,
    ) -> models.Log:
        timestamp = datetime.datetime.now(datetime.timezone.utc)

        log = models.Log(
            project_id=project_id,
            timestamp=timestamp,
            ingested_at=datetime.datetime.now(datetime.timezone.utc),
            level=level,
            log_type=log_type,
            importance="standard",
            message=message,
            error_type=error_type,
            error_message=error_message,
            **kwargs,
        )

        async with self.test_db_manager.session_factory() as session:
            session.add(log)
            await session.commit()
            await session.refresh(log)
            return log

    @pytest.mark.asyncio
    async def test_search_logs_by_message(self):
        await self.create_test_log(project_id=1, message="Database connection timeout")
        await self.create_test_log(project_id=1, message="User login successful")
        await self.create_test_log(project_id=1, message="Database query executed")

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="database",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 2
        assert all("database" in log.message.lower() for log in response.logs)

    @pytest.mark.asyncio
    async def test_search_logs_by_error_type(self):
        await self.create_test_log(
            project_id=1,
            message="Error occurred",
            error_type="TimeoutError",
            error_message="Connection timed out",
        )
        await self.create_test_log(
            project_id=1,
            message="Another error",
            error_type="ValueError",
            error_message="Invalid value",
        )

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="TimeoutError",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1
        assert response.logs[0].error_type == "TimeoutError"

    @pytest.mark.asyncio
    async def test_search_logs_by_error_message(self):
        await self.create_test_log(
            project_id=1,
            message="Error 1",
            error_message="Connection timeout after 30 seconds",
        )
        await self.create_test_log(
            project_id=1,
            message="Error 2",
            error_message="Invalid request format",
        )

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="timeout",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1
        assert "timeout" in response.logs[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_search_logs_case_insensitive(self):
        await self.create_test_log(project_id=1, message="Database ERROR occurred")
        await self.create_test_log(project_id=1, message="User not found")

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="ERROR",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1

        request.query = "error"
        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1

    @pytest.mark.asyncio
    async def test_search_logs_with_time_range(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        one_hour_ago = now - datetime.timedelta(hours=1)
        two_hours_ago = now - datetime.timedelta(hours=2)

        await self.create_test_log(project_id=1, message="Old error log")
        async with self.test_db_manager.session_factory() as session:
            await session.execute(
                models.Log.__table__.update().values(timestamp=two_hours_ago)
            )
            await session.commit()

        await self.create_test_log(project_id=1, message="Recent error log")

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="error",
            start_time=one_hour_ago.isoformat(),
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1
        assert response.logs[0].message == "Recent error log"

    @pytest.mark.asyncio
    async def test_search_logs_pagination(self):
        for i in range(5):
            await self.create_test_log(project_id=1, message=f"Error log {i}")

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="error",
            limit=2,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 2
        assert response.total == 5
        assert response.has_more is True

        request.offset = 4
        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_search_logs_no_results(self):
        await self.create_test_log(project_id=1, message="User login successful")

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="nonexistent",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 0
        assert response.total == 0
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_search_logs_project_isolation(self):
        await self.create_test_log(project_id=1, message="Error in project 1")
        await self.create_test_log(project_id=2, message="Error in project 2")

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="error",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1
        assert response.logs[0].project_id == 1

    @pytest.mark.asyncio
    async def test_search_logs_partial_match(self):
        await self.create_test_log(project_id=1, message="Connection timeout")
        await self.create_test_log(project_id=1, message="User login")

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="time",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 1
        assert "timeout" in response.logs[0].message.lower()

    @pytest.mark.asyncio
    async def test_search_logs_ordering(self):
        now = datetime.datetime.now(datetime.timezone.utc)

        log1 = await self.create_test_log(project_id=1, message="Error 1")
        log2 = await self.create_test_log(project_id=1, message="Error 2")
        log3 = await self.create_test_log(project_id=1, message="Error 3")

        async with self.test_db_manager.session_factory() as session:
            await session.execute(
                models.Log.__table__.update()
                .where(models.Log.id == log1.id)
                .values(timestamp=now - datetime.timedelta(minutes=2))
            )
            await session.execute(
                models.Log.__table__.update()
                .where(models.Log.id == log2.id)
                .values(timestamp=now - datetime.timedelta(minutes=1))
            )
            await session.execute(
                models.Log.__table__.update()
                .where(models.Log.id == log3.id)
                .values(timestamp=now)
            )
            await session.commit()

        request = query_pb2.SearchLogsRequest(
            project_id=1,
            query="error",
            limit=10,
            offset=0,
        )

        response = await self.stub.SearchLogs(request)

        assert len(response.logs) == 3
        assert response.logs[0].message == "Error 3"
        assert response.logs[1].message == "Error 2"
        assert response.logs[2].message == "Error 1"
