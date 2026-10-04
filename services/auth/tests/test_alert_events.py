import datetime

import auth_service.database as database
import auth_service.models as models
import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest

PROJECT_ID = 1


@pytest.mark.asyncio
class TestListAlertEvents(BaseGrpcTest):
    async def _insert_event(self, state: str, value: float) -> None:
        async with database.get_session() as session:
            session.add(
                models.AlertEvent(
                    project_id=PROJECT_ID,
                    rule_name="High error rate",
                    metric_type="error_rate_all",
                    comparator=">",
                    threshold=5.0,
                    unit="%",
                    value=value,
                    severity="warning",
                    state=state,
                    connectors_sent=[],
                    fired_at=datetime.datetime.now(datetime.timezone.utc),
                )
            )
            await session.commit()

    async def test_events_carry_firing_or_resolved_state(self):
        await self._insert_event("firing", 12.5)
        await self._insert_event("resolved", 0.0)

        response = await self.stub.ListAlertEvents(
            auth_pb2.ListAlertEventsRequest(project_id=PROJECT_ID, limit=10)
        )

        assert [(e.state, e.value) for e in response.events] == [
            ("resolved", 0.0),
            ("firing", 12.5),
        ]
