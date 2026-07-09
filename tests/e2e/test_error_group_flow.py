import json
import uuid

import httpx
import pytest

from .helpers import poll_until

pytestmark = pytest.mark.e2e


def _exception_log_body(error_type: str, error_message: str, log_id: str) -> dict:
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "e2e-error-test"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "severityNumber": 17,
                                "body": {"stringValue": error_message},
                                "attributes": [
                                    {
                                        "key": "ledger.log_type",
                                        "value": {"stringValue": "exception"},
                                    },
                                    {
                                        "key": "exception.type",
                                        "value": {"stringValue": error_type},
                                    },
                                    {
                                        "key": "exception.message",
                                        "value": {"stringValue": error_message},
                                    },
                                    {
                                        "key": "exception.stacktrace",
                                        "value": {
                                            "stringValue": (
                                                f"Traceback (most recent call last):\n"
                                                f'  File "e2e.py", line 1, in <module>\n'
                                                f"{error_type}: {error_message}"
                                            )
                                        },
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


class TestErrorGroupFlow:
    async def test_ingest_exception_group_appears_resolve_and_reopen(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        project: dict,
        api_key_headers: dict,
    ):
        error_type = f"E2EError{uuid.uuid4().hex[:8]}"
        error_message = "something broke during the e2e run"

        ingest_response = await client.post(
            "/v1/logs",
            content=json.dumps(
                _exception_log_body(error_type, error_message, uuid.uuid4().hex)
            ).encode(),
            headers={**api_key_headers, "Content-Type": "application/json"},
        )
        assert ingest_response.status_code == 200, ingest_response.text

        group_holder: dict = {}

        async def _group_appears() -> bool:
            response = await client.get(
                "/api/v1/error-groups",
                headers=auth_headers,
                params={"project_id": project["project_id"]},
            )
            if response.status_code != 200:
                return False
            groups = response.json()["groups"]
            match = next((g for g in groups if g["error_type"] == error_type), None)
            if match is None:
                return False
            group_holder["group"] = match
            return True

        await poll_until(
            _group_appears, timeout=30.0, interval=1.0, description="error group to appear"
        )

        group = group_holder["group"]
        assert group["status"] == "unresolved"
        assert group["occurrence_count"] >= 1

        resolve_response = await client.patch(
            f"/api/v1/error-groups/{group['id']}/status",
            headers=auth_headers,
            params={"project_id": project["project_id"]},
            json={"status": "resolved"},
        )
        assert resolve_response.status_code == 200, resolve_response.text
        assert resolve_response.json()["status"] == "resolved"
        assert resolve_response.json()["resolved_at"] is not None

        reopen_response = await client.patch(
            f"/api/v1/error-groups/{group['id']}/status",
            headers=auth_headers,
            params={"project_id": project["project_id"]},
            json={"status": "unresolved"},
        )
        assert reopen_response.status_code == 200, reopen_response.text
        assert reopen_response.json()["status"] == "unresolved"

    async def test_second_occurrence_increments_count_on_same_group(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        project: dict,
        api_key_headers: dict,
    ):
        error_type = f"E2ERepeat{uuid.uuid4().hex[:8]}"
        error_message = "recurring failure"

        for _ in range(2):
            response = await client.post(
                "/v1/logs",
                content=json.dumps(
                    _exception_log_body(error_type, error_message, uuid.uuid4().hex)
                ).encode(),
                headers={**api_key_headers, "Content-Type": "application/json"},
            )
            assert response.status_code == 200

        async def _group_has_two_occurrences() -> bool:
            response = await client.get(
                "/api/v1/error-groups",
                headers=auth_headers,
                params={"project_id": project["project_id"]},
            )
            if response.status_code != 200:
                return False
            groups = response.json()["groups"]
            match = next((g for g in groups if g["error_type"] == error_type), None)
            return match is not None and match["occurrence_count"] >= 2

        await poll_until(
            _group_has_two_occurrences,
            timeout=30.0,
            interval=1.0,
            description="error group occurrence_count to reach 2",
        )
