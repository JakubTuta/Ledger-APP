import grpc
import pytest

from .test_base import BaseGatewayTest


@pytest.mark.asyncio
class TestRegisterEndpoint(BaseGatewayTest):
    """Test account registration through gateway."""

    async def test_register_success(self):
        """Test successful registration."""
        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "test@example.com",
                "password": "Password123",
                "name": "Test User",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["account_id"] > 0
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
        assert "message" in data
        print(f"✅ Created account ID: {data['account_id']}")

    async def test_register_duplicate_email(self):
        """Test registering with duplicate email returns 409."""
        stub = self.get_mock_auth_stub()

        async def mock_register_duplicate(request):
            raise grpc.RpcError()

        original_register = stub.Register

        async def register_with_error(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.ALREADY_EXISTS
            error.details = lambda: "Email already registered"
            raise error

        stub.Register = register_with_error

        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "duplicate@example.com",
                "password": "Password123",
                "name": "Test User",
            },
        )

        assert response.status_code == 409
        assert "already registered" in response.json()["detail"].lower()
        print("✅ Correctly rejected duplicate email")

        stub.Register = original_register

    async def test_register_validation_short_password(self):
        """Test password validation."""
        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "test@example.com",
                "password": "short",
                "name": "Test User",
            },
        )

        assert response.status_code == 422
        print("✅ Short password rejected by Pydantic validation")

    async def test_register_validation_missing_uppercase(self):
        """Test password must have uppercase."""
        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "test@example.com",
                "password": "password123",
                "name": "Test User",
            },
        )

        assert response.status_code == 422
        assert "uppercase" in str(response.json()).lower()
        print("✅ Password without uppercase rejected")

    async def test_register_validation_missing_lowercase(self):
        """Test password must have lowercase."""
        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "test@example.com",
                "password": "PASSWORD123",
                "name": "Test User",
            },
        )

        assert response.status_code == 422
        assert "lowercase" in str(response.json()).lower()
        print("✅ Password without lowercase rejected")

    async def test_register_validation_missing_digit(self):
        """Test password must have digit."""
        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "test@example.com",
                "password": "Password",
                "name": "Test User",
            },
        )

        assert response.status_code == 422
        assert "digit" in str(response.json()).lower()
        print("✅ Password without digit rejected")

    async def test_register_validation_invalid_email(self):
        """Test invalid email format."""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "test@",
            "test..user@example.com",
        ]

        for email in invalid_emails:
            response = await self.client.post(
                "/api/v1/accounts/register",
                json={
                    "email": email,
                    "password": "Password123",
                    "name": "Test User",
                },
            )

            assert response.status_code == 422
            print(f"✅ Invalid email rejected: {email}")

    async def test_register_email_case_insensitive(self):
        """Test email is converted to lowercase."""
        response = await self.client.post(
            "/api/v1/accounts/register",
            json={
                "email": "TEST@EXAMPLE.COM",
                "password": "Password123",
                "name": "Test User",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        print("✅ Email converted to lowercase")


@pytest.mark.asyncio
class TestLoginEndpoint(BaseGatewayTest):
    """Test login functionality."""

    async def test_login_success(self):
        """Test successful login."""
        response = await self.client.post(
            "/api/v1/accounts/login",
            json={
                "email": "test@example.com",
                "password": "Password123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["account_id"] > 0
        assert data["expires_in"] == 3600
        print(f"✅ Login successful, token: {data['access_token'][:20]}...")

    async def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        stub = self.get_mock_auth_stub()

        async def mock_login_invalid(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.UNAUTHENTICATED
            error.details = lambda: "Invalid credentials"
            raise error

        stub.Login = mock_login_invalid

        response = await self.client.post(
            "/api/v1/accounts/login",
            json={
                "email": "test@example.com",
                "password": "WrongPassword123",
            },
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
        print("✅ Invalid credentials rejected")

    async def test_login_email_case_insensitive(self):
        """Test login email is case-insensitive."""
        response = await self.client.post(
            "/api/v1/accounts/login",
            json={
                "email": "TEST@EXAMPLE.COM",
                "password": "Password123",
            },
        )

        assert response.status_code == 200
        print("✅ Login with uppercase email successful")


@pytest.mark.asyncio
class TestLogoutEndpoint(BaseGatewayTest):
    """Test logout functionality."""

    async def test_logout_success(self):
        """Test successful logout."""
        token = "test_token_123"
        await self.mock_redis.setex(f"session:{token}", 3600, '{"account_id": 1}')

        response = await self.client.post(
            "/api/v1/accounts/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204
        session_data = await self.mock_redis.get(f"session:{token}")
        assert session_data is None
        print("✅ Logout successful, session cleared")

    async def test_logout_without_token(self):
        """Test logout without authorization header."""
        response = await self.client.post("/api/v1/accounts/logout")

        assert response.status_code == 401
        assert "authorization" in response.json()["detail"].lower()
        print("✅ Logout without token rejected")


@pytest.mark.asyncio
class TestGetCurrentAccount(BaseGatewayTest):
    """Test getting current account info."""

    async def test_get_account_success(self):
        """Test getting current account."""
        api_key = "test_api_key_123"
        await self.mock_redis.set_cached_api_key(
            api_key,
            {
                "project_id": 1,
                "account_id": 1,
                "rate_limit_per_minute": 1000,
                "rate_limit_per_hour": 50000,
                "daily_quota": 1000000,
                "current_usage": 0,
            },
        )

        response = await self.client.get(
            "/api/v1/accounts/me",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == 1
        assert data["email"] == "test@example.com"
        print("✅ Current account info retrieved")

    async def test_get_account_without_auth(self):
        """Test getting account without authentication."""
        response = await self.client.get("/api/v1/accounts/me")

        assert response.status_code == 401
        print("✅ Unauthenticated request rejected")


@pytest.mark.asyncio
class TestUpdateAccountName(BaseGatewayTest):
    """Test updating account name."""

    async def test_update_name_success(self):
        """Test successful name update."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        response = await self.client.patch(
            "/api/v1/accounts/me/name",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert "message" in data
        print("✅ Account name updated successfully")

    async def test_update_name_without_auth(self):
        """Test updating name without authentication."""
        response = await self.client.patch(
            "/api/v1/accounts/me/name",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 401
        print("✅ Unauthenticated name update rejected")

    async def test_update_name_empty_fails(self):
        """Test updating name with empty string fails."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        response = await self.client.patch(
            "/api/v1/accounts/me/name",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": ""},
        )

        assert response.status_code == 422
        print("✅ Empty name rejected")

    async def test_update_name_too_long_fails(self):
        """Test updating name that's too long fails."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        long_name = "a" * 256
        response = await self.client.patch(
            "/api/v1/accounts/me/name",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": long_name},
        )

        assert response.status_code == 422
        print("✅ Name that's too long rejected")

    async def test_update_name_grpc_error(self):
        """Test handling gRPC errors."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        stub = self.get_mock_auth_stub()

        async def mock_update_error(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.INVALID_ARGUMENT
            error.details = lambda: "Invalid name"
            raise error

        stub.UpdateAccountName = mock_update_error

        response = await self.client.patch(
            "/api/v1/accounts/me/name",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Test Name"},
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()
        print("✅ gRPC error handled correctly")


@pytest.mark.asyncio
class TestChangePassword(BaseGatewayTest):
    """Test changing account password."""

    async def test_change_password_success(self):
        """Test successful password change."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        response = await self.client.post(
            "/api/v1/accounts/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "old_password": "OldPassword123",
                "new_password": "NewPassword456",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print("✅ Password changed successfully")

    async def test_change_password_without_auth(self):
        """Test changing password without authentication."""
        response = await self.client.post(
            "/api/v1/accounts/me/password",
            json={
                "old_password": "OldPassword123",
                "new_password": "NewPassword456",
            },
        )

        assert response.status_code == 401
        print("✅ Unauthenticated password change rejected")

    async def test_change_password_weak_new_password(self):
        """Test changing to a weak password fails."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        response = await self.client.post(
            "/api/v1/accounts/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "old_password": "OldPassword123",
                "new_password": "weak",
            },
        )

        assert response.status_code == 422
        print("✅ Weak password rejected")

    async def test_change_password_no_uppercase(self):
        """Test new password without uppercase fails."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        response = await self.client.post(
            "/api/v1/accounts/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "old_password": "OldPassword123",
                "new_password": "lowercase123",
            },
        )

        assert response.status_code == 422
        assert "uppercase" in str(response.json()).lower()
        print("✅ Password without uppercase rejected")

    async def test_change_password_no_lowercase(self):
        """Test new password without lowercase fails."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        response = await self.client.post(
            "/api/v1/accounts/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "old_password": "OldPassword123",
                "new_password": "UPPERCASE123",
            },
        )

        assert response.status_code == 422
        assert "lowercase" in str(response.json()).lower()
        print("✅ Password without lowercase rejected")

    async def test_change_password_no_digit(self):
        """Test new password without digit fails."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        response = await self.client.post(
            "/api/v1/accounts/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "old_password": "OldPassword123",
                "new_password": "NoDigitPassword",
            },
        )

        assert response.status_code == 422
        assert "digit" in str(response.json()).lower()
        print("✅ Password without digit rejected")

    async def test_change_password_wrong_old_password(self):
        """Test changing password with wrong old password."""
        token = "test_token_123"
        await self.mock_redis.setex(
            f"session:{token}", 3600, '{"account_id": 1}'
        )

        stub = self.get_mock_auth_stub()

        async def mock_wrong_old_password(request):
            error = grpc.RpcError()
            error.code = lambda: grpc.StatusCode.INVALID_ARGUMENT
            error.details = lambda: "Current password is incorrect"
            raise error

        stub.ChangePassword = mock_wrong_old_password

        response = await self.client.post(
            "/api/v1/accounts/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "old_password": "WrongOldPassword123",
                "new_password": "NewPassword456",
            },
        )

        assert response.status_code == 400
        assert "incorrect" in response.json()["detail"].lower()
        print("✅ Wrong old password rejected")
