import httpx
import pytest

from .helpers import poll_until

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_slow]


class TestHeartbeatMonitorFlow:
    async def test_heartbeat_ping_then_check_transitions_to_up(
        self, client: httpx.AsyncClient, auth_headers: dict, project: dict
    ):
        create_response = await client.post(
            "/api/v1/monitors",
            headers=auth_headers,
            json={
                "project_id": project["project_id"],
                "kind": "heartbeat",
                "name": "e2e heartbeat monitor",
                "interval_s": 60,
                "grace_s": 30,
            },
        )
        assert create_response.status_code == 201, create_response.text
        monitor = create_response.json()
        assert monitor["state"] == "unknown"

        ping_response = await client.post(f"/api/v1/monitors/{monitor['token']}/ping")
        assert ping_response.status_code == 204, ping_response.text

        async def _monitor_is_up() -> bool:
            response = await client.get(
                "/api/v1/monitors",
                headers=auth_headers,
                params={"project_id": project["project_id"]},
            )
            if response.status_code != 200:
                return False
            monitors = response.json()
            match = next((m for m in monitors if m["id"] == monitor["id"]), None)
            return match is not None and match["state"] == "up"

        await poll_until(
            _monitor_is_up,
            timeout=90.0,
            interval=5.0,
            description="heartbeat monitor to transition to up (checker runs every minute)",
        )

    async def test_ping_with_invalid_token_returns_404(self, client: httpx.AsyncClient):
        response = await client.post("/api/v1/monitors/not-a-real-token/ping")
        assert response.status_code == 404

    async def test_delete_monitor(
        self, client: httpx.AsyncClient, auth_headers: dict, project: dict
    ):
        create_response = await client.post(
            "/api/v1/monitors",
            headers=auth_headers,
            json={
                "project_id": project["project_id"],
                "kind": "heartbeat",
                "name": "e2e monitor to delete",
            },
        )
        monitor_id = create_response.json()["id"]

        delete_response = await client.delete(
            f"/api/v1/monitors/{monitor_id}",
            headers=auth_headers,
            params={"project_id": project["project_id"]},
        )
        assert delete_response.status_code == 204

        list_response = await client.get(
            "/api/v1/monitors",
            headers=auth_headers,
            params={"project_id": project["project_id"]},
        )
        monitor_ids = [m["id"] for m in list_response.json()]
        assert monitor_id not in monitor_ids
