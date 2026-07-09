import datetime

import pytest
from auth_service import database, models
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestAlertEventAckSnooze(BaseGrpcTest):
    """Test alert event acknowledge/snooze operations (no CreateAlertEvent RPC
    exists - events are only ever created by the analytics alert evaluator's
    _fire(), so tests seed rows directly via the ORM)."""

    async def _seed_account_project_and_event(self) -> tuple[int, int, int]:
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="alertevents@example.com", password="password123", plan="free"
            )
        )
        project = await self.stub.CreateProject(
            auth_pb2.CreateProjectRequest(
                account_id=account.account_id,
                name="Alert Events Project",
                slug="alert-events-project",
                environment="production",
            )
        )

        async with database.get_session() as session:
            event = models.AlertEvent(
                project_id=project.project_id,
                rule_name="High Error Rate",
                metric_type="error_rate",
                comparator=">",
                threshold=10.0,
                unit="percent",
                value=25.0,
                severity="critical",
                state="firing",
                connectors_sent=[],
                fired_at=datetime.datetime.now(datetime.timezone.utc),
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            event_id = event.id

        return account.account_id, project.project_id, event_id

    async def test_ack_alert_event_success(self):
        account_id, project_id, event_id = await self._seed_account_project_and_event()

        response = await self.stub.AckAlertEvent(
            auth_pb2.AckAlertEventRequest(
                event_id=event_id, project_id=project_id, account_id=account_id
            )
        )

        assert response.success is True
        assert response.event.id == event_id
        assert response.event.acked_by == account_id
        assert response.event.acked_at

    async def test_ack_alert_event_wrong_project_not_found(self):
        _account_id, _project_id, event_id = await self._seed_account_project_and_event()

        response = await self.stub.AckAlertEvent(
            auth_pb2.AckAlertEventRequest(event_id=event_id, project_id=999999, account_id=1)
        )

        assert response.success is False
        assert "not found" in response.error_message.lower()

    async def test_ack_alert_event_missing_event_not_found(self):
        response = await self.stub.AckAlertEvent(
            auth_pb2.AckAlertEventRequest(event_id=999999, project_id=1, account_id=1)
        )

        assert response.success is False

    async def test_snooze_alert_event_success(self):
        _account_id, project_id, event_id = await self._seed_account_project_and_event()

        response = await self.stub.SnoozeAlertEvent(
            auth_pb2.SnoozeAlertEventRequest(event_id=event_id, project_id=project_id, minutes=60)
        )

        assert response.success is True
        assert response.event.id == event_id
        assert response.event.snoozed_until

        snoozed_until = datetime.datetime.fromisoformat(response.event.snoozed_until)
        now = datetime.datetime.now(datetime.timezone.utc)
        assert snoozed_until > now
        assert snoozed_until <= now + datetime.timedelta(minutes=61)

    async def test_snooze_alert_event_rejects_zero_minutes(self):
        _account_id, project_id, event_id = await self._seed_account_project_and_event()

        response = await self.stub.SnoozeAlertEvent(
            auth_pb2.SnoozeAlertEventRequest(event_id=event_id, project_id=project_id, minutes=0)
        )

        assert response.success is False

    async def test_snooze_alert_event_rejects_over_7_days(self):
        _account_id, project_id, event_id = await self._seed_account_project_and_event()

        response = await self.stub.SnoozeAlertEvent(
            auth_pb2.SnoozeAlertEventRequest(
                event_id=event_id, project_id=project_id, minutes=7 * 24 * 60 + 1
            )
        )

        assert response.success is False

    async def test_snooze_alert_event_wrong_project_not_found(self):
        _account_id, _project_id, event_id = await self._seed_account_project_and_event()

        response = await self.stub.SnoozeAlertEvent(
            auth_pb2.SnoozeAlertEventRequest(event_id=event_id, project_id=999999, minutes=60)
        )

        assert response.success is False
        assert "not found" in response.error_message.lower()

    async def test_ack_then_list_reflects_ack_fields(self):
        account_id, project_id, event_id = await self._seed_account_project_and_event()

        await self.stub.AckAlertEvent(
            auth_pb2.AckAlertEventRequest(
                event_id=event_id, project_id=project_id, account_id=account_id
            )
        )

        listed = await self.stub.ListAlertEvents(
            auth_pb2.ListAlertEventsRequest(project_id=project_id, limit=10)
        )

        assert len(listed.events) == 1
        assert listed.events[0].acked_by == account_id
