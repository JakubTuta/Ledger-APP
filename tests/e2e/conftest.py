import os
import uuid

import httpx
import pytest
import pytest_asyncio

E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8020")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "e2e: end-to-end test against the live local stack")
    config.addinivalue_line(
        "markers", "e2e_slow: end-to-end test that waits on a cron-driven background job"
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _stack_healthy() -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{E2E_BASE_URL}/health")
        except httpx.ConnectError as e:
            pytest.exit(
                f"E2E suite requires the stack to be running at {E2E_BASE_URL} "
                f"(./scripts/Make.ps1 up). Connection failed: {e}",
                returncode=1,
            )
        if response.status_code != 200:
            pytest.exit(
                f"E2E suite requires a healthy stack at {E2E_BASE_URL}/health, "
                f"got HTTP {response.status_code}.",
                returncode=1,
            )


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=30.0) as c:
        yield c


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:12]


@pytest_asyncio.fixture
async def registered_account(client: httpx.AsyncClient) -> dict:
    email = f"e2e-{_unique_suffix()}@e2e.local"
    password = "E2ePassword123"

    response = await client.post(
        "/api/v1/accounts/register",
        json={"email": email, "password": password, "name": "E2E Test User"},
    )
    assert response.status_code == 201, response.text
    data = response.json()

    return {
        "email": email,
        "password": password,
        "account_id": data["account_id"],
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }


@pytest_asyncio.fixture
async def auth_headers(registered_account: dict) -> dict:
    return {"Authorization": f"Bearer {registered_account['access_token']}"}


@pytest_asyncio.fixture
async def project(client: httpx.AsyncClient, auth_headers: dict) -> dict:
    slug = f"e2e-{_unique_suffix()}"
    response = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": f"E2E {slug}", "slug": slug, "environment": "production"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest_asyncio.fixture
async def api_key(client: httpx.AsyncClient, auth_headers: dict, project: dict) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project['project_id']}/api-keys",
        headers=auth_headers,
        json={"name": "e2e-key"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest_asyncio.fixture
async def api_key_headers(api_key: dict) -> dict:
    return {"Authorization": f"Bearer {api_key['full_key']}"}
