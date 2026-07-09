import json
import uuid

import httpx
import pytest

from .helpers import poll_until

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_slow]


def _endpoint_log_body(duration_ms: int) -> dict:
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "e2e-alert-test"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "severityNumber": 9,
                                "body": {"stringValue": "slow endpoint"},
                                "attributes": [
                                    {
                                        "key": "http.request.method",
                                        "value": {"stringValue": "GET"},
                                    },
                                    {
                                        "key": "http.route",
                                        "value": {"stringValue": "/e2e/slow"},
                                    },
                                    {
                                        "key": "http.response.status_code",
                                        "value": {"intValue": 200},
                                    },
                                    {
                                        "key": "ledger.duration_ms",
                                        "value": {"doubleValue": duration_ms},
                                    },
                                    {
                                        "key": "ledger.log_id",
                                        "value": {"stringValue": uuid.uuid4().hex},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }


class TestAlertFiringFlow:
    async def test_breaching_metric_fires_alert_and_creates_notification(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        project: dict,
        api_key_headers: dict,
    ):
        connector_response = await client.post(
            "/api/v1/connectors",
            headers=auth_headers,
            json={"kind": "in_app", "name": "e2e in-app connector", "config": "{}"},
        )
        assert connector_response.status_code == 201, connector_response.text
        connector_id = connector_response.json()["id"]

        rule_response = await client.post(
            "/api/v1/alerts/rules",
            headers=auth_headers,
            json={
                "project_id": project["project_id"],
                "name": "e2e p95 latency rule",
                "metric": "p95_latency",
                "comparator": ">",
                "threshold": 0,
                "unit": "ms",
                "connector_ids": [connector_id],
            },
        )
        assert rule_response.status_code == 201, rule_response.text

        ingest_response = await client.post(
            "/v1/logs",
            content=json.dumps(_endpoint_log_body(duration_ms=500)).encode(),
            headers={**api_key_headers, "Content-Type": "application/json"},
        )
        assert ingest_response.status_code == 200, ingest_response.text

        async def _alert_fired() -> bool:
            response = await client.get(
                "/api/v1/alerts/history",
                headers=auth_headers,
                params={"project_id": project["project_id"]},
            )
            if response.status_code != 200:
                return False
            events = response.json()["events"]
            return len(events) > 0

        await poll_until(
            _alert_fired,
            timeout=150.0,
            interval=5.0,
            description="alert rule to fire (evaluator runs every minute)",
        )

        history_response = await client.get(
            "/api/v1/alerts/history",
            headers=auth_headers,
            params={"project_id": project["project_id"]},
        )
        event = history_response.json()["events"][0]
        assert event["metric"] == "p95_latency"
        assert event["acked_at"] is None

        ack_response = await client.post(
            f"/api/v1/alerts/history/{event['id']}/ack",
            headers=auth_headers,
            params={"project_id": project["project_id"]},
        )
        assert ack_response.status_code == 200, ack_response.text
        assert ack_response.json()["acked_at"] is not None

        async def _notification_created() -> bool:
            response = await client.get("/api/v1/notifications", headers=auth_headers)
            if response.status_code != 200:
                return False
            notifications = response.json().get("notifications", [])
            return any(n.get("kind") == "alert_firing" for n in notifications)

        await poll_until(
            _notification_created,
            timeout=10.0,
            interval=1.0,
            description="in_app notification for the fired alert",
        )
