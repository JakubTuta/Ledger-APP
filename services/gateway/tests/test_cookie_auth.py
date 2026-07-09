import pytest

import gateway_service.proto.auth_pb2 as auth_pb2

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestLoginSetsRefreshCookie(BaseGatewayTest):
    async def test_login_sets_httponly_refresh_cookie(self, setup_method):
        response = await self.client.post(
            "/api/v1/accounts/login",
            json={"email": "test@example.com", "password": "Password123"},
        )

        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie
        assert "httponly" in set_cookie.lower()
        assert "path=/api/v1/accounts" in set_cookie.lower()

    async def test_login_response_body_also_includes_refresh_token(self, setup_method):
        """Back-compat: the refresh token is still in the body too, for
        clients that haven't migrated to cookie-only auth."""
        response = await self.client.post(
            "/api/v1/accounts/login",
            json={"email": "test@example.com", "password": "Password123"},
        )

        assert response.json()["refresh_token"]

    async def test_register_also_sets_refresh_cookie(self, setup_method):
        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "newuser@example.com",
                "password": "Password123",
                "name": "New User",
            },
        )

        assert response.status_code == 201
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie


@pytest.mark.asyncio
class TestRefreshViaCookie(BaseGatewayTest):
    async def test_refresh_with_no_body_uses_cookie(self, setup_method):
        self.client.cookies.set("refresh_token", "cookie-supplied-token")

        response = await self.client.post("/api/v1/accounts/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"]
        assert data["refresh_token"]

    async def test_refresh_rotates_cookie(self, setup_method):
        self.client.cookies.set("refresh_token", "cookie-supplied-token")

        response = await self.client.post("/api/v1/accounts/refresh")

        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie

    async def test_refresh_without_body_or_cookie_returns_401(self, setup_method):
        response = await self.client.post("/api/v1/accounts/refresh")

        assert response.status_code == 401

    async def test_refresh_body_token_takes_precedence_over_cookie(self, setup_method):
        """_get_refresh_token_from_request prefers an explicit body token
        (back-compat) over the cookie when both are present."""
        stub = self.get_mock_auth_stub()
        seen_tokens = []

        async def capture_refresh(request, timeout=None):
            seen_tokens.append(request.refresh_token)
            return auth_pb2.RefreshTokenResponse(
                access_token="tok",
                refresh_token="new-tok",
                expires_in=900,
                account_id=1,
                email="test@example.com",
            )

        stub.RefreshToken = capture_refresh
        self.client.cookies.set("refresh_token", "cookie-token")

        await self.client.post("/api/v1/accounts/refresh", json={"refresh_token": "body-token"})

        assert seen_tokens == ["body-token"]


@pytest.mark.asyncio
class TestLogoutClearsRefreshCookie(BaseGatewayTest):
    async def test_logout_clears_cookie(self, setup_method):
        token = self.make_session_token(account_id=1)
        self.client.cookies.set("refresh_token", "some-token")

        response = await self.client.post(
            "/api/v1/accounts/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie
        # Cleared cookies carry an immediately-expired Max-Age/Expires.
        assert "max-age=0" in set_cookie.lower() or "1970" in set_cookie
