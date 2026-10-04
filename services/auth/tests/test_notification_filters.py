import datetime

import auth_service.database as database
import auth_service.models as models
import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest

OCT_1 = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc)
OCT_2 = datetime.datetime(2026, 10, 2, 12, 0, tzinfo=datetime.timezone.utc)
OCT_3 = datetime.datetime(2026, 10, 3, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.mark.asyncio
class TestListNotificationFilters(BaseGrpcTest):
    async def _seed(self) -> int:
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(email="inbox@example.com", password="password123", plan="pro")
        )
        rows = [
            (1, "alert_firing", OCT_1),
            (1, "alert_resolved", OCT_2),
            (2, "alert_firing", OCT_3),
            (2, "quota_warning", OCT_3),
        ]
        async with database.get_session() as session:
            for project_id, kind, created_at in rows:
                session.add(
                    models.Notification(
                        user_id=account.account_id,
                        project_id=project_id,
                        kind=kind,
                        severity="info",
                        payload={},
                        created_at=created_at,
                    )
                )
            await session.commit()
        return account.account_id

    async def _list(self, user_id: int, **filters) -> list[tuple[int, str]]:
        response = await self.stub.ListNotifications(
            auth_pb2.ListNotificationsRequest(user_id=user_id, **filters)
        )
        return sorted((n.project_id, n.kind) for n in response.notifications)

    async def test_filters_by_project(self):
        user_id = await self._seed()

        assert await self._list(user_id, project_id=1) == [
            (1, "alert_firing"),
            (1, "alert_resolved"),
        ]

    async def test_filters_by_kind(self):
        user_id = await self._seed()

        assert await self._list(user_id, kind="alert_firing") == [
            (1, "alert_firing"),
            (2, "alert_firing"),
        ]

    async def test_created_range_is_inclusive_after_and_exclusive_before(self):
        user_id = await self._seed()

        assert await self._list(
            user_id, created_after=OCT_2.isoformat(), created_before=OCT_3.isoformat()
        ) == [(1, "alert_resolved")]

    async def test_filters_combine(self):
        user_id = await self._seed()

        assert await self._list(
            user_id, project_id=2, kind="alert_firing", created_after=OCT_3.isoformat()
        ) == [(2, "alert_firing")]
