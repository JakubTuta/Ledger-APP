import json
import secrets
from datetime import datetime, timezone

import auth_service.config as config
import auth_service.models as models
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

VALID_TRAFFIC_CATEGORIES = {"users", "bots", "servers", "unknown"}

# Ordered so the validation error reads the same way every time it is raised.
VALID_PANEL_TYPES = (
    "logs",
    "errors",
    "metrics",
    "error_list",
    "bottleneck",
    "error_heatmap",
    "trace",
    "trace_list",
    "summary",
    "latency_overview",
    "country_map",
    "metric_series",
)

VALID_METRIC_AGGREGATIONS = ("avg", "sum", "min", "max", "count", "p50", "p95", "p99")
VALID_METRIC_INTERVALS = ("1m", "5m", "1h", "1d")


class DashboardService:
    """
    Dashboard panel management service.

    Responsibilities:
    - Retrieve user dashboard panels (with Redis caching)
    - Create new dashboard panels (invalidates cache)
    - Update existing dashboard panels (invalidates cache)
    - Delete dashboard panels (invalidates cache)

    Caching strategy:
    - Cache key: dashboard:panels:{user_id}
    - TTL: 300 seconds (5 minutes)
    - Invalidated on mutations
    """

    def __init__(self, redis: Redis | None = None):
        self.redis = redis
        self.cache_ttl = config.settings.DASHBOARD_CACHE_TTL

    async def get_dashboard_panels(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> list[dict]:
        """
        Get all dashboard panels for a user.

        Uses Redis cache for fast retrieval:
        - Cache hit: Returns cached panels (5 min TTL)
        - Cache miss: Fetches from DB and caches result
        """

        if self.redis:
            cached_panels = await self._get_cached_panels(user_id)
            if cached_panels is not None:
                return cached_panels

        result = await session.execute(
            select(models.UserDashboard).where(models.UserDashboard.user_id == user_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            dashboard = models.UserDashboard(
                user_id=user_id,
                panels=[],
            )
            session.add(dashboard)
            await session.commit()
            await session.refresh(dashboard)

        panels = dashboard.panels

        if self.redis:
            await self._cache_panels(user_id, panels)

        return panels

    async def create_dashboard_panel(
        self,
        session: AsyncSession,
        user_id: int,
        name: str,
        index: int,
        project_id: str,
        panel_type: str,
        period: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
        endpoint: str | None = None,
        routes: list[str] | None = None,
        statistic: str | None = None,
        layout: dict | None = None,
        trace_id: str | None = None,
        service_filter: str | None = None,
        operation_filter: str | None = None,
        min_duration_ms: int | None = None,
        has_error: bool | None = None,
        status_class: str | None = None,
        logs_search: str | None = None,
        traffic_categories: list[str] | None = None,
        metric_name: str | None = None,
        metric_aggregation: str | None = None,
        metric_group_by: list[str] | None = None,
        metric_tag_filters: dict[str, str] | None = None,
        metric_interval: str | None = None,
        include_client_errors: bool | None = None,
    ) -> dict:
        """Create a new dashboard panel."""

        if not self._validate_panel_type(panel_type):
            raise ValueError(
                f"Invalid panel type '{panel_type}'. Must be one of: {', '.join(VALID_PANEL_TYPES)}"
            )

        if panel_type == "metrics":
            if not endpoint:
                raise ValueError("'endpoint' is required for metrics type panels")

        self._validate_metric_panel(panel_type, metric_aggregation, metric_interval)

        has_period = period is not None
        has_dates = period_from is not None and period_to is not None

        if not has_period and not has_dates:
            raise ValueError("Either 'period' or both 'periodFrom' and 'periodTo' must be provided")

        if has_period and has_dates:
            raise ValueError("Cannot use both 'period' and 'periodFrom'/'periodTo'")

        self._validate_traffic_categories(traffic_categories)

        panel_id = self._generate_panel_id()

        if layout is not None:
            if layout.get("x", 0) < 0 or layout.get("y", 0) < 0:
                raise ValueError("layout x and y must be >= 0")
            if layout.get("w", 1) <= 0 or layout.get("h", 1) <= 0:
                raise ValueError("layout w and h must be > 0")

        new_panel = {
            "id": panel_id,
            "name": name,
            "index": index,
            "project_id": project_id,
            "period": period,
            "periodFrom": period_from,
            "periodTo": period_to,
            "type": panel_type,
            "endpoint": endpoint,
            "routes": routes if routes else [],
            "statistic": statistic if statistic else "",
            "layout": layout,
            "trace_id": trace_id,
            "service_filter": service_filter,
            "operation_filter": operation_filter,
            "min_duration_ms": min_duration_ms,
            "has_error": has_error,
            "status_class": status_class,
            "logs_search": logs_search,
            "traffic_categories": traffic_categories if traffic_categories else [],
            "metric_name": metric_name,
            "metric_aggregation": metric_aggregation,
            "metric_group_by": metric_group_by if metric_group_by else [],
            "metric_tag_filters": metric_tag_filters if metric_tag_filters else {},
            "metric_interval": metric_interval,
            "include_client_errors": include_client_errors,
        }

        result = await session.execute(
            select(models.UserDashboard).where(models.UserDashboard.user_id == user_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            dashboard = models.UserDashboard(
                user_id=user_id,
                panels=[new_panel],
            )
            session.add(dashboard)
        else:
            panels = dashboard.panels.copy()
            panels.append(new_panel)
            dashboard.panels = panels
            dashboard.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(dashboard)

        if self.redis:
            await self._invalidate_cache(user_id)

        return new_panel

    async def update_dashboard_panel(
        self,
        session: AsyncSession,
        user_id: int,
        panel_id: str,
        name: str,
        index: int,
        project_id: str,
        panel_type: str,
        period: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
        endpoint: str | None = None,
        routes: list[str] | None = None,
        statistic: str | None = None,
        layout: dict | None = None,
        trace_id: str | None = None,
        service_filter: str | None = None,
        operation_filter: str | None = None,
        min_duration_ms: int | None = None,
        has_error: bool | None = None,
        status_class: str | None = None,
        logs_search: str | None = None,
        traffic_categories: list[str] | None = None,
        metric_name: str | None = None,
        metric_aggregation: str | None = None,
        metric_group_by: list[str] | None = None,
        metric_tag_filters: dict[str, str] | None = None,
        metric_interval: str | None = None,
        include_client_errors: bool | None = None,
    ) -> dict:
        """Update an existing dashboard panel."""

        if not self._validate_panel_type(panel_type):
            raise ValueError(
                f"Invalid panel type '{panel_type}'. Must be one of: {', '.join(VALID_PANEL_TYPES)}"
            )

        if panel_type == "metrics":
            if not endpoint:
                raise ValueError("'endpoint' is required for metrics type panels")

        self._validate_metric_panel(panel_type, metric_aggregation, metric_interval)

        has_period = period is not None
        has_dates = period_from is not None and period_to is not None

        if not has_period and not has_dates:
            raise ValueError("Either 'period' or both 'periodFrom' and 'periodTo' must be provided")

        if has_period and has_dates:
            raise ValueError("Cannot use both 'period' and 'periodFrom'/'periodTo'")

        self._validate_traffic_categories(traffic_categories)

        result = await session.execute(
            select(models.UserDashboard).where(models.UserDashboard.user_id == user_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            raise ValueError("Dashboard not found for user")

        panels = dashboard.panels.copy()
        panel_found = False

        if layout is not None:
            if layout.get("x", 0) < 0 or layout.get("y", 0) < 0:
                raise ValueError("layout x and y must be >= 0")
            if layout.get("w", 1) <= 0 or layout.get("h", 1) <= 0:
                raise ValueError("layout w and h must be > 0")

        for i, panel in enumerate(panels):
            if panel["id"] == panel_id:
                panels[i] = {
                    "id": panel_id,
                    "name": name,
                    "index": index,
                    "project_id": project_id,
                    "period": period,
                    "periodFrom": period_from,
                    "periodTo": period_to,
                    "type": panel_type,
                    "endpoint": endpoint,
                    "routes": routes if routes else [],
                    "statistic": statistic if statistic else "",
                    "layout": layout,
                    "trace_id": trace_id,
                    "service_filter": service_filter,
                    "operation_filter": operation_filter,
                    "min_duration_ms": min_duration_ms,
                    "has_error": has_error,
                    "status_class": status_class,
                    "logs_search": logs_search,
                    "traffic_categories": traffic_categories if traffic_categories else [],
                    "metric_name": metric_name,
                    "metric_aggregation": metric_aggregation,
                    "metric_group_by": metric_group_by if metric_group_by else [],
                    "metric_tag_filters": metric_tag_filters if metric_tag_filters else {},
                    "metric_interval": metric_interval,
                    "include_client_errors": include_client_errors,
                }
                panel_found = True
                break

        if not panel_found:
            raise ValueError(f"Panel with id '{panel_id}' not found")

        dashboard.panels = panels
        dashboard.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(dashboard)

        if self.redis:
            await self._invalidate_cache(user_id)

        return panels[i]

    async def delete_dashboard_panel(
        self,
        session: AsyncSession,
        user_id: int,
        panel_id: str,
    ) -> bool:
        """Delete a dashboard panel."""

        result = await session.execute(
            select(models.UserDashboard).where(models.UserDashboard.user_id == user_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            raise ValueError("Dashboard not found for user")

        panels = dashboard.panels.copy()
        original_length = len(panels)

        panels = [panel for panel in panels if panel["id"] != panel_id]

        if len(panels) == original_length:
            raise ValueError(f"Panel with id '{panel_id}' not found")

        dashboard.panels = panels
        dashboard.updated_at = datetime.now(timezone.utc)

        await session.commit()

        if self.redis:
            await self._invalidate_cache(user_id)

        return True

    async def get_dashboard_tabs(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> tuple[list[dict], str | None]:
        result = await session.execute(
            select(models.UserDashboard).where(models.UserDashboard.user_id == user_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            return [], None

        return dashboard.tabs, dashboard.active_tab_id

    async def save_dashboard_tabs(
        self,
        session: AsyncSession,
        user_id: int,
        tabs: list[dict],
        active_tab_id: str | None,
    ) -> bool:
        result = await session.execute(
            select(models.UserDashboard).where(models.UserDashboard.user_id == user_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            dashboard = models.UserDashboard(
                user_id=user_id,
                panels=[],
                tabs=tabs,
                active_tab_id=active_tab_id,
            )
            session.add(dashboard)
        else:
            dashboard.tabs = tabs
            dashboard.active_tab_id = active_tab_id
            dashboard.updated_at = datetime.now(timezone.utc)

        await session.commit()
        return True

    def _validate_panel_type(self, panel_type: str) -> bool:
        return panel_type in VALID_PANEL_TYPES

    def _validate_metric_panel(
        self,
        panel_type: str,
        metric_aggregation: str | None,
        metric_interval: str | None,
    ) -> None:
        """A metric panel may exist before its metric is chosen; the card prompts for one."""
        if panel_type != "metric_series":
            return

        if metric_aggregation and metric_aggregation not in VALID_METRIC_AGGREGATIONS:
            raise ValueError(
                f"Invalid metric_aggregation '{metric_aggregation}'. "
                f"Must be one of: {', '.join(VALID_METRIC_AGGREGATIONS)}"
            )

        if metric_interval and metric_interval not in VALID_METRIC_INTERVALS:
            raise ValueError(
                f"Invalid metric_interval '{metric_interval}'. "
                f"Must be one of: {', '.join(VALID_METRIC_INTERVALS)}"
            )

    def _validate_traffic_categories(self, traffic_categories: list[str] | None) -> None:
        """
        A panel narrows its raw-log reads to these caller categories. An empty
        list means "all traffic" - the dashboard never persists the full set,
        so a saved panel stays on all traffic even if a new category is added.
        """
        if not traffic_categories:
            return

        invalid = set(traffic_categories) - VALID_TRAFFIC_CATEGORIES
        if invalid:
            raise ValueError(
                f"Invalid traffic categories {sorted(invalid)}. Must be a subset of: "
                f"{sorted(VALID_TRAFFIC_CATEGORIES)}"
            )

    def _generate_panel_id(self) -> str:
        """Generate unique panel ID."""
        return f"panel_{secrets.token_hex(8)}"

    async def _get_cached_panels(self, user_id: int) -> list[dict] | None:
        """
        Retrieve panels from Redis cache.

        Returns:
            List of panels if cached, None if cache miss
        """
        if not self.redis:
            return None

        cache_key = self._cache_key(user_id)
        cached_data = await self.redis.get(cache_key)

        if not cached_data:
            return None

        try:
            return json.loads(cached_data)
        except json.JSONDecodeError:
            await self.redis.delete(cache_key)
            return None

    async def _cache_panels(self, user_id: int, panels: list[dict]) -> None:
        """
        Cache panels in Redis.

        Args:
            user_id: User ID
            panels: List of panel dictionaries to cache
        """
        if not self.redis:
            return

        cache_key = self._cache_key(user_id)
        await self.redis.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(panels),
        )

    async def _invalidate_cache(self, user_id: int) -> None:
        """
        Invalidate cached panels for a user.

        Called after create/update/delete operations.
        """
        if not self.redis:
            return

        cache_key = self._cache_key(user_id)
        await self.redis.delete(cache_key)

    def _cache_key(self, user_id: int) -> str:
        """Generate Redis cache key for user's panels."""
        return f"dashboard:panels:{user_id}"
