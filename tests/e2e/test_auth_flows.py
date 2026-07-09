import httpx
import pyotp
import pytest

pytestmark = pytest.mark.e2e


class TestRefreshRotation:
    async def test_refresh_rotates_tokens_and_old_one_stops_working(
        self, client: httpx.AsyncClient, registered_account: dict
    ):
        old_refresh_token = registered_account["refresh_token"]

        response = await client.post(
            "/api/v1/accounts/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert response.status_code == 200, response.text
        new_tokens = response.json()
        # Access tokens are JWTs with second-granularity iat/exp - minting a
        # second one for the same account within the same wall-clock second
        # produces a byte-identical token, so only the refresh token (which
        # embeds its own random value, not just account+timestamp) is a
        # reliable rotation signal here.
        assert new_tokens["refresh_token"] != old_refresh_token

        replay_response = await client.post(
            "/api/v1/accounts/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert replay_response.status_code == 401

    async def test_refresh_via_cookie_with_no_body(
        self, client: httpx.AsyncClient, registered_account: dict
    ):
        login_response = await client.post(
            "/api/v1/accounts/login",
            json={
                "email": registered_account["email"],
                "password": registered_account["password"],
            },
        )
        assert login_response.status_code == 200
        refresh_cookie = login_response.json()["refresh_token"]

        # The refresh cookie is Set-Cookie'd with Secure=True (ENV=production
        # in this stack's .env), which httpx's cookie jar correctly refuses
        # to auto-resend over plain http://localhost - same as a real
        # browser would. Attach it explicitly to exercise the cookie-based
        # refresh path itself rather than re-testing browser cookie policy.
        client.cookies.set("refresh_token", refresh_cookie)
        refresh_response = await client.post("/api/v1/accounts/refresh")
        assert refresh_response.status_code == 200, refresh_response.text
        assert refresh_response.json()["account_id"] == registered_account["account_id"]


class TestSessionManagement:
    async def test_list_sessions_shows_current_session(
        self, client: httpx.AsyncClient, registered_account: dict, auth_headers: dict
    ):
        client.cookies.set("refresh_token", registered_account["refresh_token"])
        response = await client.get("/api/v1/accounts/sessions", headers=auth_headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] >= 1
        assert any(s["is_current"] for s in data["sessions"])

    async def test_revoke_all_sessions_invalidates_refresh_token(
        self, client: httpx.AsyncClient, registered_account: dict, auth_headers: dict
    ):
        revoke_response = await client.post(
            "/api/v1/accounts/sessions/revoke-all", headers=auth_headers
        )
        assert revoke_response.status_code == 200, revoke_response.text

        refresh_response = await client.post(
            "/api/v1/accounts/refresh",
            json={"refresh_token": registered_account["refresh_token"]},
        )
        assert refresh_response.status_code == 401


class TestTwoFactorAuth:
    async def test_enable_2fa_then_login_requires_totp_code(
        self, client: httpx.AsyncClient, registered_account: dict, auth_headers: dict
    ):
        setup_response = await client.post("/api/v1/accounts/2fa/setup", headers=auth_headers)
        assert setup_response.status_code == 200, setup_response.text
        secret = setup_response.json()["secret"]

        code = pyotp.TOTP(secret).now()
        verify_response = await client.post(
            "/api/v1/accounts/2fa/verify",
            headers=auth_headers,
            json={"code": code},
        )
        assert verify_response.status_code == 200, verify_response.text
        assert len(verify_response.json()["backup_codes"]) > 0

        login_response = await client.post(
            "/api/v1/accounts/login",
            json={
                "email": registered_account["email"],
                "password": registered_account["password"],
            },
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert login_data["requires_2fa"] is True
        assert login_data.get("access_token") is None
        totp_session_token = login_data["totp_session_token"]

        login_code = pyotp.TOTP(secret).now()
        complete_response = await client.post(
            "/api/v1/accounts/2fa/login",
            json={"totp_session_token": totp_session_token, "code": login_code},
        )
        assert complete_response.status_code == 200, complete_response.text
        assert complete_response.json()["account_id"] == registered_account["account_id"]

        # One-shot: the same totp_session_token can't be replayed.
        replay_response = await client.post(
            "/api/v1/accounts/2fa/login",
            json={"totp_session_token": totp_session_token, "code": login_code},
        )
        assert replay_response.status_code == 401

    async def test_disable_2fa_requires_correct_password(
        self, client: httpx.AsyncClient, registered_account: dict, auth_headers: dict
    ):
        setup_response = await client.post("/api/v1/accounts/2fa/setup", headers=auth_headers)
        secret = setup_response.json()["secret"]
        await client.post(
            "/api/v1/accounts/2fa/verify",
            headers=auth_headers,
            json={"code": pyotp.TOTP(secret).now()},
        )

        wrong_password_response = await client.post(
            "/api/v1/accounts/2fa/disable",
            headers=auth_headers,
            json={"password": "WrongPassword123"},
        )
        assert wrong_password_response.status_code == 400

        disable_response = await client.post(
            "/api/v1/accounts/2fa/disable",
            headers=auth_headers,
            json={"password": registered_account["password"]},
        )
        assert disable_response.status_code == 200, disable_response.text

        login_response = await client.post(
            "/api/v1/accounts/login",
            json={
                "email": registered_account["email"],
                "password": registered_account["password"],
            },
        )
        assert login_response.status_code == 200
        assert login_response.json().get("requires_2fa") in (None, False)
