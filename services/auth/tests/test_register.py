import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestRegisterEndpoint(BaseGrpcTest):
    """Test account registration."""

    async def test_register_success(self):
        """Test successful registration."""

        request = auth_pb2.RegisterRequest(
            email="test@example.com", password="password123", plan="free"
        )

        response = await self.stub.Register(request)

        assert response.account_id > 0
        assert response.email == "test@example.com"
        assert response.plan == "free"

        print(f"Created account ID: {response.account_id}")

    async def test_register_duplicate_email(self):
        """Test registering with duplicate email fails."""

        request1 = auth_pb2.RegisterRequest(
            email="duplicate@example.com", password="password123", plan="free"
        )
        await self.stub.Register(request1)

        request2 = auth_pb2.RegisterRequest(
            email="duplicate@example.com", password="different_password", plan="pro"
        )

        try:
            await self.stub.Register(request2)
            assert False, "Should have raised error"
        except Exception as e:
            assert "already registered" in str(e).lower()
            print(f"Correctly rejected duplicate: {e}")

    async def test_register_different_plans(self):
        """Test registering with different plans."""

        plans = ["free", "pro", "enterprise"]

        for i, plan in enumerate(plans):
            request = auth_pb2.RegisterRequest(
                email=f"user{i}@example.com", password="password123", plan=plan
            )

            response = await self.stub.Register(request)

            assert response.account_id > 0
            assert response.plan == plan
            print(f"Created {plan} account: {response.account_id}")
            print(f"Created {plan} account: {response.account_id}")
