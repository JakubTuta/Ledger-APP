import datetime
import json

import pytest

import query_service.models as models
import query_service.proto.query_pb2 as query_pb2
import query_service.services.log_query as log_query
import tests.test_base as test_base


class _LogFactoryMixin:
    """Shared `create_test_log` helper for test classes that need to seed
    rows directly via the ORM. Not itself a test class -- classes needing
    this mix it in alongside `test_base.BaseQueryTest`, so its `test_*`
    methods (there are none) never get collected on their own and its
    helper isn't duplicated across classes that do have tests.
    """

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


class TestLogQuery(_LogFactoryMixin, test_base.BaseQueryTest):
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

    @pytest.mark.asyncio
    async def test_query_logs_with_client_channel_filter(self):
        await self.create_test_log(project_id=1, client_channel="browser_navigation")
        await self.create_test_log(project_id=1, client_channel="api_client")
        await self.create_test_log(project_id=1, client_channel="api_client")

        request = query_pb2.QueryLogsRequest(project_id=1, client_channel=["api_client"], limit=10)
        response = await self.stub.QueryLogs(request)

        assert len(response.logs) == 2
        assert all(log.client_channel == "api_client" for log in response.logs)

    @pytest.mark.asyncio
    async def test_query_logs_with_multiple_client_channel_values_is_or(self):
        await self.create_test_log(project_id=1, client_channel="browser_navigation")
        await self.create_test_log(project_id=1, client_channel="browser_xhr")
        await self.create_test_log(project_id=1, client_channel="bot")
        await self.create_test_log(project_id=1, client_channel="api_client")

        request = query_pb2.QueryLogsRequest(
            project_id=1,
            client_channel=["browser_navigation", "browser_xhr"],
            limit=10,
        )
        response = await self.stub.QueryLogs(request)

        channels = {log.client_channel for log in response.logs}
        assert channels == {"browser_navigation", "browser_xhr"}

    @pytest.mark.asyncio
    async def test_query_logs_returns_client_channel_and_country(self):
        await self.create_test_log(project_id=1, client_channel="browser_xhr", client_country="DE")

        response = await self.stub.QueryLogs(query_pb2.QueryLogsRequest(project_id=1, limit=10))

        assert response.logs[0].client_channel == "browser_xhr"
        assert response.logs[0].client_country == "DE"

    @pytest.mark.asyncio
    async def test_query_logs_client_channel_unset_when_absent(self):
        await self.create_test_log(project_id=1)

        response = await self.stub.QueryLogs(query_pb2.QueryLogsRequest(project_id=1, limit=10))

        assert not response.logs[0].HasField("client_channel")
        assert not response.logs[0].HasField("client_country")


class TestSplitFacetWindow:
    """
    Unit tests for the raw/rollup window split. The rollup job recomputes a
    fixed _ROLLUP_WINDOW_DAYS trailing window every run and keeps no
    watermark, so the split is pure wall-clock arithmetic against `now`:
    anything within the window and older than _ROLLUP_SAFE_LAG is trusted;
    everything else (partial edge hours, the recent lag buffer, history older
    than the window) comes off `logs` directly.
    """

    # NOW sits well clear of both window edges so most tests only have to
    # reason about the one boundary they're targeting.
    NOW = datetime.datetime(2026, 6, 15, 14, 27, tzinfo=datetime.timezone.utc)
    NOW_FLOOR = datetime.datetime(2026, 6, 15, 14, 0, tzinfo=datetime.timezone.utc)
    CEILING = NOW_FLOOR - datetime.timedelta(hours=1)
    FLOOR = NOW_FLOOR - datetime.timedelta(days=log_query._ROLLUP_WINDOW_DAYS)

    def test_short_recent_window_is_raw(self):
        start = self.CEILING - datetime.timedelta(hours=3, minutes=40)
        end = self.CEILING + datetime.timedelta(minutes=20)

        raw_ranges, rollup_range = log_query._split_facet_window(start, end, self.NOW)

        assert rollup_range == (
            self.CEILING - datetime.timedelta(hours=3),
            self.CEILING,
        )
        assert raw_ranges == [
            (start, self.CEILING - datetime.timedelta(hours=3), False),
            (self.CEILING, end, True),
        ]

    def test_tail_within_the_safe_lag_stays_raw(self):
        start = self.CEILING - datetime.timedelta(hours=5)
        end = self.NOW

        raw_ranges, rollup_range = log_query._split_facet_window(start, end, self.NOW)

        assert rollup_range == (start, self.CEILING)
        assert raw_ranges == [(self.CEILING, end, True)]

    def test_history_older_than_the_window_stays_raw(self):
        start = self.FLOOR - datetime.timedelta(days=5)
        end = self.FLOOR + datetime.timedelta(hours=3)

        raw_ranges, rollup_range = log_query._split_facet_window(start, end, self.NOW)

        assert rollup_range == (self.FLOOR, self.FLOOR + datetime.timedelta(hours=3))
        assert raw_ranges == [(start, self.FLOOR, False)]

    def test_window_entirely_older_than_the_rollup_is_all_raw(self):
        start = self.FLOOR - datetime.timedelta(days=10)
        end = self.FLOOR - datetime.timedelta(days=5)

        raw_ranges, rollup_range = log_query._split_facet_window(start, end, self.NOW)

        assert rollup_range is None
        assert raw_ranges == [(start, end, True)]

    def test_window_shorter_than_one_bucket_is_raw(self):
        start = self.CEILING - datetime.timedelta(minutes=50)
        end = self.CEILING - datetime.timedelta(minutes=10)

        raw_ranges, rollup_range = log_query._split_facet_window(start, end, self.NOW)

        assert rollup_range is None
        assert raw_ranges == [(start, end, True)]


class TestGetLogFacets(_LogFactoryMixin, test_base.BaseQueryTest):
    async def seed_rollup_bucket(
        self,
        project_id: int,
        bucket: datetime.datetime,
        count: int,
        level: str = "info",
        log_type: str = "logger",
        status_class: str = "",
        environment: str = "",
        client_channel: str = "",
    ) -> None:
        async with self.test_db_manager.session_factory() as session:
            await session.execute(
                models.log_facets_1h.insert().values(
                    project_id=project_id,
                    bucket=bucket,
                    level=level,
                    log_type=log_type,
                    status_class=status_class,
                    environment=environment,
                    client_channel=client_channel,
                    count=count,
                )
            )
            await session.commit()

    @pytest.mark.asyncio
    async def test_facets_merge_rollup_with_raw_tail(self):
        # 3h back clears the rollup's 1h safe-lag boundary comfortably, so
        # this bucket is trusted; the log an hour later falls inside the lag
        # buffer and has to come from `logs` directly.
        base = datetime.datetime.now(datetime.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) - datetime.timedelta(hours=3)

        await self.seed_rollup_bucket(project_id=1, bucket=base, count=5, level="info")

        # Inside the rolled-up hour: the rollup already accounts for it, so
        # counting the raw row too would double count.
        await self.create_test_log(
            project_id=1, level="info", timestamp=base + datetime.timedelta(minutes=30)
        )
        # Within the safe-lag buffer: only the raw table knows about this one.
        await self.create_test_log(
            project_id=1, level="error", timestamp=base + datetime.timedelta(hours=1, minutes=10)
        )

        response = await self.stub.GetLogFacets(
            query_pb2.GetLogFacetsRequest(
                project_id=1,
                start_time=base.isoformat(),
                end_time=(base + datetime.timedelta(hours=1, minutes=30)).isoformat(),
            )
        )

        assert {v.value: v.count for v in response.level} == {"info": 5, "error": 1}

    @pytest.mark.asyncio
    async def test_facets_apply_dimension_filters_to_the_rollup(self):
        base = datetime.datetime.now(datetime.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) - datetime.timedelta(hours=3)

        await self.seed_rollup_bucket(
            project_id=1, bucket=base, count=5, level="info", client_channel="api_client"
        )
        await self.seed_rollup_bucket(
            project_id=1, bucket=base, count=9, level="error", client_channel="bot"
        )

        response = await self.stub.GetLogFacets(
            query_pb2.GetLogFacetsRequest(
                project_id=1,
                start_time=base.isoformat(),
                end_time=(base + datetime.timedelta(hours=1)).isoformat(),
                level="error",
            )
        )

        assert {v.value: v.count for v in response.client_channel} == {"bot": 9}

    @pytest.mark.asyncio
    async def test_facets_drop_the_rollups_absent_value_marker(self):
        base = datetime.datetime.now(datetime.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) - datetime.timedelta(hours=3)

        await self.seed_rollup_bucket(
            project_id=1, bucket=base, count=4, environment="", client_channel=""
        )

        response = await self.stub.GetLogFacets(
            query_pb2.GetLogFacetsRequest(
                project_id=1,
                start_time=base.isoformat(),
                end_time=(base + datetime.timedelta(hours=1)).isoformat(),
            )
        )

        assert list(response.environment) == []
        assert list(response.client_channel) == []
        assert {v.value: v.count for v in response.level} == {"info": 4}

    @pytest.mark.asyncio
    async def test_search_bypasses_the_rollup_entirely(self):
        base = datetime.datetime.now(datetime.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) - datetime.timedelta(hours=3)

        await self.seed_rollup_bucket(project_id=1, bucket=base, count=5, level="info")
        await self.create_test_log(
            project_id=1,
            level="warning",
            message="disk almost full",
            timestamp=base + datetime.timedelta(minutes=30),
        )

        response = await self.stub.GetLogFacets(
            query_pb2.GetLogFacetsRequest(
                project_id=1,
                start_time=base.isoformat(),
                end_time=(base + datetime.timedelta(hours=1, minutes=30)).isoformat(),
                search="disk",
            )
        )

        assert {v.value: v.count for v in response.level} == {"warning": 1}

    @pytest.mark.asyncio
    async def test_facets_include_client_channel_bucket(self):
        await self.create_test_log(project_id=1, client_channel="browser_navigation")
        await self.create_test_log(project_id=1, client_channel="browser_navigation")
        await self.create_test_log(project_id=1, client_channel="api_client")
        await self.create_test_log(project_id=1, client_channel=None)

        response = await self.stub.GetLogFacets(query_pb2.GetLogFacetsRequest(project_id=1))

        values = {v.value: v.count for v in response.client_channel}
        assert values == {"browser_navigation": 2, "api_client": 1}

    @pytest.mark.asyncio
    async def test_facets_client_channel_respects_other_filters(self):
        await self.create_test_log(project_id=1, level="error", client_channel="api_client")
        await self.create_test_log(project_id=1, level="info", client_channel="api_client")

        response = await self.stub.GetLogFacets(
            query_pb2.GetLogFacetsRequest(project_id=1, level="error")
        )

        values = {v.value: v.count for v in response.client_channel}
        assert values == {"api_client": 1}


class TestGetErrorList(_LogFactoryMixin, test_base.BaseQueryTest):
    async def create_test_error_log(self, project_id: int, **kwargs) -> models.Log:
        kwargs.setdefault("level", "error")
        kwargs.setdefault("error_type", "ValueError")
        kwargs.setdefault("message", "boom")
        return await self.create_test_log(project_id=project_id, **kwargs)

    @pytest.mark.asyncio
    async def test_error_list_with_client_channel_filter(self):
        await self.create_test_error_log(project_id=1, client_channel="api_client")
        await self.create_test_error_log(project_id=1, client_channel="bot")

        response = await self.stub.GetErrorList(
            query_pb2.GetErrorListRequest(project_id=1, period="last7days", client_channel=["bot"])
        )

        assert len(response.errors) == 1

    @pytest.mark.asyncio
    async def test_error_list_with_multiple_client_channel_values_is_or(self):
        await self.create_test_error_log(
            project_id=1, message="err from api", client_channel="api_client"
        )
        await self.create_test_error_log(project_id=1, message="err from bot", client_channel="bot")
        await self.create_test_error_log(
            project_id=1, message="err from browser", client_channel="browser_navigation"
        )

        response = await self.stub.GetErrorList(
            query_pb2.GetErrorListRequest(
                project_id=1,
                period="last7days",
                client_channel=["api_client", "bot"],
            )
        )

        assert len(response.errors) == 2

    @pytest.mark.asyncio
    async def test_error_list_without_client_channel_filter_returns_all(self):
        await self.create_test_error_log(
            project_id=1, message="err from api", client_channel="api_client"
        )
        await self.create_test_error_log(
            project_id=1, message="err with no channel", client_channel=None
        )

        response = await self.stub.GetErrorList(
            query_pb2.GetErrorListRequest(project_id=1, period="last7days")
        )

        assert len(response.errors) == 2


class TestGetCountryBreakdown(_LogFactoryMixin, test_base.BaseQueryTest):
    @pytest.mark.asyncio
    async def test_country_breakdown_counts_and_orders_by_count_desc(self):
        await self.create_test_log(project_id=1, client_country="US")
        await self.create_test_log(project_id=1, client_country="US")
        await self.create_test_log(project_id=1, client_country="US")
        await self.create_test_log(project_id=1, client_country="DE")
        await self.create_test_log(project_id=1, client_country="DE")

        response = await self.stub.GetCountryBreakdown(
            query_pb2.GetCountryBreakdownRequest(project_id=1)
        )

        countries = [(c.country, c.count) for c in response.countries]
        assert countries == [("US", 3), ("DE", 2)]

    @pytest.mark.asyncio
    async def test_country_breakdown_excludes_null_country(self):
        await self.create_test_log(project_id=1, client_country="US")
        await self.create_test_log(project_id=1, client_country=None)

        response = await self.stub.GetCountryBreakdown(
            query_pb2.GetCountryBreakdownRequest(project_id=1)
        )

        assert len(response.countries) == 1
        assert response.countries[0].country == "US"

    @pytest.mark.asyncio
    async def test_country_breakdown_with_multiple_client_channel_values_is_or(self):
        await self.create_test_log(project_id=1, client_country="US", client_channel="bot")
        await self.create_test_log(
            project_id=1, client_country="DE", client_channel="browser_navigation"
        )
        await self.create_test_log(project_id=1, client_country="FR", client_channel="api_client")

        response = await self.stub.GetCountryBreakdown(
            query_pb2.GetCountryBreakdownRequest(
                project_id=1, client_channel=["bot", "browser_navigation"]
            )
        )

        countries = {c.country for c in response.countries}
        assert countries == {"US", "DE"}

    @pytest.mark.asyncio
    async def test_country_breakdown_respects_limit(self):
        for code in ("US", "DE", "FR", "JP"):
            await self.create_test_log(project_id=1, client_country=code)

        response = await self.stub.GetCountryBreakdown(
            query_pb2.GetCountryBreakdownRequest(project_id=1, limit=2)
        )

        assert len(response.countries) == 2

    @pytest.mark.asyncio
    async def test_country_breakdown_scoped_to_project(self):
        await self.create_test_log(project_id=1, client_country="US")
        await self.create_test_log(project_id=2, client_country="DE")

        response = await self.stub.GetCountryBreakdown(
            query_pb2.GetCountryBreakdownRequest(project_id=1)
        )

        assert len(response.countries) == 1
        assert response.countries[0].country == "US"
