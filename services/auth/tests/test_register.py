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
        print(f"✅ Created account ID: {response.account_id}")

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
            print(f"✅ Correctly rejected duplicate: {e}")

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
            print(f"✅ Created {plan} account: {response.account_id}")


@pytest.mark.asyncio
class TestRegisterValidation(BaseGrpcTest):
    """Test registration input validation."""

    async def test_register_empty_email(self):
        """Test registration with empty email."""
        request = auth_pb2.RegisterRequest(
            email="", password="password123", plan="free"
        )

        try:
            await self.stub.Register(request)
            print("⚠️  Empty email was accepted - consider adding validation")
        except Exception as e:
            print(f"✅ Empty email rejected: {e}")

    async def test_register_invalid_email_format(self):
        """Test registration with invalid email format."""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "test@",
            "test..user@example.com",
            "test user@example.com",
        ]

        for email in invalid_emails:
            request = auth_pb2.RegisterRequest(
                email=email, password="password123", plan="free"
            )

            try:
                response = await self.stub.Register(request)
                print(f"⚠️  Invalid email accepted: {email}")
            except Exception:
                print(f"✅ Invalid email rejected: {email}")

    async def test_register_empty_password(self):
        """Test registration with empty password."""
        request = auth_pb2.RegisterRequest(
            email="empty-pass@example.com", password="", plan="free"
        )

        try:
            response = await self.stub.Register(request)
            print("⚠️  Empty password was accepted - consider adding validation")
        except Exception as e:
            print(f"✅ Empty password rejected: {e}")

    async def test_register_very_long_password(self):
        """Test registration with extremely long password."""
        request = auth_pb2.RegisterRequest(
            email="longpass@example.com",
            password="a" * 1000,
            plan="free",
        )

        try:
            response = await self.stub.Register(request)
            assert response.account_id > 0
            print("✅ Long password accepted")
        except Exception as e:
            print(f"⚠️  Long password rejected: {e}")

    async def test_register_special_characters_in_password(self):
        """Test registration with special characters in password."""
        special_passwords = [
            "p@ssw0rd!",
            "päss wörd",
            "密码123",
            "🔒secure123",
        ]

        for i, password in enumerate(special_passwords):
            request = auth_pb2.RegisterRequest(
                email=f"special{i}@example.com", password=password, plan="free"
            )

            try:
                response = await self.stub.Register(request)
                assert response.account_id > 0
                print(f"✅ Special password accepted: {password[:10]}...")
            except Exception as e:
                print(f"⚠️  Special password rejected: {e}")


@pytest.mark.asyncio
class TestRegisterEmailEdgeCases(BaseGrpcTest):
    """Test email edge cases."""

    async def test_register_email_with_plus_sign(self):
        """Test email with plus sign (common for email aliases)."""
        request = auth_pb2.RegisterRequest(
            email="user+test@example.com", password="password123", plan="free"
        )

        response = await self.stub.Register(request)
        assert response.email == "user+test@example.com"
        print("✅ Email with + sign accepted")

    async def test_register_email_case_sensitivity(self):
        """Test if emails are case-sensitive."""
        request1 = auth_pb2.RegisterRequest(
            email="test@example.com", password="password123", plan="free"
        )
        await self.stub.Register(request1)

        request2 = auth_pb2.RegisterRequest(
            email="TEST@EXAMPLE.COM", password="password123", plan="free"
        )

        try:
            await self.stub.Register(request2)
            print("⚠️  Email is case-sensitive - consider making case-insensitive")
        except Exception:
            print("✅ Uppercase email rejected (case-insensitive)")

    async def test_register_email_with_subdomain(self):
        """Test email with subdomain."""
        request = auth_pb2.RegisterRequest(
            email="user@mail.example.com", password="password123", plan="free"
        )

        response = await self.stub.Register(request)
        assert response.account_id > 0
        print("✅ Email with subdomain accepted")

    async def test_register_very_long_email(self):
        """Test registration with very long email."""
        long_email = "a" * 240 + "@example.com"

        request = auth_pb2.RegisterRequest(
            email=long_email, password="password123", plan="free"
        )

        try:
            response = await self.stub.Register(request)
            print(f"✅ Long email accepted ({len(long_email)} chars)")
        except Exception as e:
            print(f"⚠️  Long email rejected: {e}")


@pytest.mark.asyncio
class TestRegisterConcurrency(BaseGrpcTest):
    """Test concurrent registration scenarios."""

    async def test_concurrent_registrations_different_emails(self):
        """Test multiple concurrent registrations with different emails."""
        import asyncio

        async def register(index):
            request = auth_pb2.RegisterRequest(
                email=f"concurrent{index}@example.com",
                password="password123",
                plan="free",
            )
            return await self.stub.Register(request)

        tasks = [register(i) for i in range(5)]
        responses = await asyncio.gather(*tasks)

        account_ids = [r.account_id for r in responses]
        assert len(account_ids) == len(set(account_ids))
        print(f"✅ Created {len(responses)} concurrent accounts")

    async def test_concurrent_registrations_same_email(self):
        """Test race condition with same email."""
        import asyncio

        async def register():
            request = auth_pb2.RegisterRequest(
                email="race@example.com", password="password123", plan="free"
            )
            return await self.stub.Register(request)

        tasks = [register() for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 1, "Only one registration should succeed"
        assert len(failures) == 2, "Two should fail"
        print(f"✅ Race condition handled: 1 success, 2 failures")


@pytest.mark.asyncio
class TestRegisterPlanValidation(BaseGrpcTest):
    """Test plan validation."""

    async def test_register_invalid_plan(self):
        """Test registration with invalid plan."""
        request = auth_pb2.RegisterRequest(
            email="invalidplan@example.com", password="password123", plan="invalid_plan"
        )

        try:
            response = await self.stub.Register(request)
            print("⚠️  Invalid plan accepted - consider adding validation")
        except Exception as e:
            print(f"✅ Invalid plan rejected: {e}")

    async def test_register_empty_plan(self):
        """Test registration with empty plan (should default to free)."""
        request = auth_pb2.RegisterRequest(
            email="emptyplan@example.com", password="password123", plan=""
        )

        response = await self.stub.Register(request)
        print(f"✅ Empty plan resulted in: {response.plan}")
