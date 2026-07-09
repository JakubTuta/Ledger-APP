import json
import uuid

import httpx
import pytest

from .helpers import poll_until

pytestmark = pytest.mark.e2e


def _otlp_log_body(message: str, log_id: str, severity_number: int = 9) -> dict:
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "e2e-test-service"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "severityNumber": severity_number,
                                "body": {"stringValue": message},
                                "attributes": [
                                    {
                                        "key": "ledger.log_type",
                                        "value": {"stringValue": "console"},
                                    },
                                    {
                                        "key": "ledger.log_id",
                                        "value": {"stringValue": log_id},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }


class TestIngestQueryFlow:
    async def test_register_login_project_key_ingest_query(
        self,
        client: httpx.AsyncClient,
        registered_account: dict,
        auth_headers: dict,
        project: dict,
        api_key: dict,
        api_key_headers: dict,
    ):
        # register + project + api-key already happened via fixtures; confirm
        # login independently works with the same credentials as a real
        # second step in the flow (not just relying on the register response).
        login_response = await client.post(
            "/api/v1/accounts/login",
            json={
                "email": registered_account["email"],
                "password": registered_account["password"],
            },
        )
        assert login_response.status_code == 200, login_response.text
        assert login_response.json()["account_id"] == registered_account["account_id"]

        log_id = uuid.uuid4().hex
        message = f"e2e ingest test {log_id}"
        ingest_response = await client.post(
            "/v1/logs",
            content=json.dumps(_otlp_log_body(message, log_id)).encode(),
            headers={**api_key_headers, "Content-Type": "application/json"},
        )
        assert ingest_response.status_code == 200, ingest_response.text

        async def _log_is_queryable() -> bool:
            response = await client.get(
                "/api/v1/logs",
                headers=auth_headers,
                params={
                    "project_id": project["project_id"],
                    "period": "today",
                    "limit": 50,
                },
            )
            if response.status_code != 200:
                return False
            logs = response.json()["logs"]
            return any(log["message"] == message for log in logs)

        await poll_until(
            _log_is_queryable,
            timeout=30.0,
            interval=1.0,
            description="log ingest to become queryable",
        )

    async def test_ingest_without_api_key_is_rejected(self, client: httpx.AsyncClient):
        response = await client.post(
            "/v1/logs",
            content=json.dumps(_otlp_log_body("should be rejected", uuid.uuid4().hex)).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 401

    async def test_query_requires_project_membership(
        self, client: httpx.AsyncClient, auth_headers: dict
    ):
        response = await client.get(
            "/api/v1/logs",
            headers=auth_headers,
            params={"project_id": 999999999, "period": "today"},
        )
        assert response.status_code in (403, 404)
