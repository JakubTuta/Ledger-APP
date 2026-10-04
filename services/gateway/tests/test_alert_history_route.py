import pytest
from gateway_service.proto import auth_pb2

from .test_base import BaseGatewayTest


def _event(event_id: int, state: str, value: float) -> auth_pb2.AlertEvent:
    return auth_pb2.AlertEvent(
        id=event_id,
        project_id=1,
        rule_name="High error rate",
        metric="error_rate_all",
        comparator=">",
        threshold=5.0,
        unit="%",
        value=value,
        severity=1,
        connectors_sent="[]",
        fired_at="2026-10-04T12:00:00+00:00",
        state=state,
    )


@pytest.mark.asyncio
class TestAlertHistoryRoute(BaseGatewayTest):
    async def test_history_exposes_firing_and_resolved_state(self):
        session_token = self.make_session_token(account_id=1)

        auth_stub = self.get_mock_auth_stub()
        auth_stub.list_alert_events_response = auth_pb2.ListAlertEventsResponse(
            events=[_event(2, "resolved", 0.0), _event(1, "firing", 12.5)],
            has_more=False,
        )

        response = await self.client.get(
            "/api/v1/alerts/history?project_id=1",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        assert response.status_code == 200
        events = response.json()["events"]
        assert [(e["id"], e["state"], e["value"]) for e in events] == [
            (2, "resolved", 0.0),
            (1, "firing", 12.5),
        ]
