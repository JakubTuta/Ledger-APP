import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestLoginEndpoint(BaseGrpcTest):
    """Test account login."""

    async def test_login_success(self):
        """Test successful login."""

        register_request = auth_pb2.RegisterRequest(
            email="login@example.com", password="mypassword123", plan="free"
        )
        register_response = await self.stub.Register(register_request)

        login_request = auth_pb2.LoginRequest(
            email="login@example.com", password="mypassword123"
        )
        login_response = await self.stub.Login(login_request)

        assert login_response.account_id == register_response.account_id
        assert login_response.email == "login@example.com"
        assert login_response.plan == "free"

        print(f"Login successful for account: {login_response.account_id}")

    async def test_login_wrong_password(self):
        """Test login with wrong password fails."""

        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="test@example.com", password="correct_password", plan="free"
            )
        )

        login_request = auth_pb2.LoginRequest(
            email="test@example.com", password="wrong_password"
        )

        try:
            await self.stub.Login(login_request)
            assert False, "Should have raised error"
        except Exception as e:
            assert "invalid" in str(e).lower()
            print(f"Correctly rejected wrong password")

    async def test_login_nonexistent_user(self):
        """Test login with non-existent email fails."""

        login_request = auth_pb2.LoginRequest(
            email="nonexistent@example.com", password="password123"
        )

        try:
            await self.stub.Login(login_request)
            assert False, "Should have raised error"
        except Exception as e:
            assert "invalid" in str(e).lower()
            print(f"Correctly rejected non-existent user")
            print(f"Correctly rejected non-existent user")
