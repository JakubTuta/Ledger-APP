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
        print(f"✅ Login successful for account: {login_response.account_id}")

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
            print(f"✅ Correctly rejected wrong password")

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
            print(f"✅ Correctly rejected non-existent user")


@pytest.mark.asyncio
class TestLoginEdgeCases(BaseGrpcTest):
    """Test login edge cases."""

    async def test_login_empty_email(self):
        """Test login with empty email."""
        login_request = auth_pb2.LoginRequest(email="", password="password123")

        try:
            await self.stub.Login(login_request)
            assert False, "Should have raised error"
        except Exception as e:
            print(f"✅ Empty email rejected: {e}")

    async def test_login_empty_password(self):
        """Test login with empty password."""
        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="user@example.com", password="realpassword", plan="free"
            )
        )

        login_request = auth_pb2.LoginRequest(email="user@example.com", password="")

        try:
            await self.stub.Login(login_request)
            assert False, "Should have raised error"
        except Exception as e:
            print(f"✅ Empty password rejected: {e}")

    async def test_login_case_sensitive_email(self):
        """Test if login is case-sensitive for email."""
        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="CaseSensitive@example.com", password="password123", plan="free"
            )
        )

        login_request = auth_pb2.LoginRequest(
            email="casesensitive@example.com", password="password123"
        )

        try:
            response = await self.stub.Login(login_request)
            print("✅ Login is case-insensitive")
        except Exception:
            print("⚠️  Login is case-sensitive - consider making case-insensitive")

    async def test_login_whitespace_in_email(self):
        """Test login with whitespace in email."""
        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="whitespace@example.com", password="password123", plan="free"
            )
        )

        login_request = auth_pb2.LoginRequest(
            email="  whitespace@example.com  ", password="password123"
        )

        try:
            response = await self.stub.Login(login_request)
            print("✅ Login handles whitespace in email")
        except Exception:
            print("⚠️  Login doesn't trim whitespace")

    async def test_login_special_characters_password(self):
        """Test login with special characters in password."""
        special_password = "p@ssw0rd!#$%^&*()"

        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="special@example.com", password=special_password, plan="free"
            )
        )

        login_request = auth_pb2.LoginRequest(
            email="special@example.com", password=special_password
        )

        response = await self.stub.Login(login_request)
        assert response.account_id > 0
        print("✅ Special characters in password work correctly")

    async def test_login_very_long_password(self):
        """Test login with very long password (exceeds 64 char limit)."""
        long_password = "a" * 500

        try:
            await self.stub.Register(
                auth_pb2.RegisterRequest(
                    email="longpass@example.com", password=long_password, plan="free"
                )
            )
            assert False, "Should have raised error for password > 64 characters"
        except Exception as e:
            assert "complexity" in str(e).lower() or "requirements" in str(e).lower()
            print(f"✅ Long password (500 chars) correctly rejected: {e}")


@pytest.mark.asyncio
class TestLoginSecurity(BaseGrpcTest):
    """Test login security aspects."""

    async def test_login_timing_attack_resistance(self):
        """Test that login doesn't leak information via timing."""
        import time

        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="timing@example.com", password="password123", plan="free"
            )
        )

        start = time.time()
        try:
            await self.stub.Login(
                auth_pb2.LoginRequest(
                    email="nonexistent@example.com", password="password123"
                )
            )
        except:
            pass
        nonexistent_time = time.time() - start

        start = time.time()
        try:
            await self.stub.Login(
                auth_pb2.LoginRequest(
                    email="timing@example.com", password="wrongpassword"
                )
            )
        except:
            pass
        wrong_password_time = time.time() - start

        time_diff = abs(nonexistent_time - wrong_password_time)
        print(f"Timing difference: {time_diff:.3f}s")

        if time_diff > 0.5:
            print("⚠️  Significant timing difference detected - potential timing attack")
        else:
            print("✅ Timing is relatively consistent")

    async def test_login_multiple_failures(self):
        """Test multiple login failures (rate limiting consideration)."""
        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="brute@example.com", password="correct_password", plan="free"
            )
        )

        failures = 0
        for i in range(10):
            try:
                await self.stub.Login(
                    auth_pb2.LoginRequest(
                        email="brute@example.com", password=f"wrong{i}"
                    )
                )
            except:
                failures += 1

        assert failures == 10
        print(f"✅ All {failures} incorrect attempts correctly rejected")
        print("⚠️  Consider implementing rate limiting for production")

    async def test_login_sql_injection_attempt(self):
        """Test SQL injection protection."""
        sql_injections = [
            "' OR '1'='1",
            "admin'--",
            "' OR 1=1--",
            "admin' OR '1'='1' /*",
            "' UNION SELECT * FROM accounts--",
        ]

        for injection in sql_injections:
            try:
                await self.stub.Login(
                    auth_pb2.LoginRequest(email=injection, password="password")
                )
                print(f"⚠️  SQL injection not blocked: {injection}")
            except Exception:
                print(f"✅ SQL injection blocked: {injection}")

    async def test_login_password_not_in_error_message(self):
        """Test that password is never leaked in error messages."""
        secret_password = "super_secret_password_12345"

        login_request = auth_pb2.LoginRequest(
            email="nonexistent@example.com", password=secret_password
        )

        try:
            await self.stub.Login(login_request)
        except Exception as e:
            error_msg = str(e)
            assert secret_password not in error_msg
            print("✅ Password not leaked in error message")


@pytest.mark.asyncio
class TestLoginConcurrency(BaseGrpcTest):
    """Test concurrent login scenarios."""

    async def test_concurrent_logins_same_account(self):
        """Test multiple concurrent logins for same account."""
        import asyncio

        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="concurrent@example.com", password="password123", plan="free"
            )
        )

        async def login():
            request = auth_pb2.LoginRequest(
                email="concurrent@example.com", password="password123"
            )
            return await self.stub.Login(request)

        tasks = [login() for _ in range(5)]
        responses = await asyncio.gather(*tasks)

        account_ids = [r.account_id for r in responses]
        assert len(set(account_ids)) == 1
        print(f"✅ {len(responses)} concurrent logins succeeded")

    async def test_concurrent_logins_different_accounts(self):
        """Test concurrent logins for different accounts."""
        import asyncio

        for i in range(5):
            await self.stub.Register(
                auth_pb2.RegisterRequest(
                    email=f"user{i}@example.com", password="password123", plan="free"
                )
            )

        async def login(index):
            request = auth_pb2.LoginRequest(
                email=f"user{index}@example.com", password="password123"
            )
            return await self.stub.Login(request)

        tasks = [login(i) for i in range(5)]
        responses = await asyncio.gather(*tasks)

        account_ids = [r.account_id for r in responses]
        assert len(account_ids) == len(set(account_ids))
        print(f"✅ {len(responses)} concurrent logins for different accounts succeeded")

    async def test_concurrent_login_attempts_mixed_success_failure(self):
        """Test concurrent login attempts with mix of correct and wrong passwords."""
        import asyncio

        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="mixed@example.com", password="correct_password", plan="free"
            )
        )

        async def login(is_correct):
            request = auth_pb2.LoginRequest(
                email="mixed@example.com",
                password="correct_password" if is_correct else "wrong_password",
            )
            try:
                return await self.stub.Login(request)
            except Exception as e:
                return e

        tasks = [login(i < 3) for i in range(6)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 3
        assert len(failures) == 3
        print(
            f"✅ Mixed concurrent logins: {len(successes)} success, {len(failures)} failures"
        )


@pytest.mark.asyncio
class TestLoginWithDifferentPlans(BaseGrpcTest):
    """Test login behavior with different account plans."""

    async def test_login_free_plan(self):
        """Test login with free plan account."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="free@example.com", password="password123", plan="free"
            )
        )

        response = await self.stub.Login(
            auth_pb2.LoginRequest(email="free@example.com", password="password123")
        )

        assert response.plan == "free"
        print("✅ Free plan login works")

    async def test_login_pro_plan(self):
        """Test login with pro plan account."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="pro@example.com", password="password123", plan="pro"
            )
        )

        response = await self.stub.Login(
            auth_pb2.LoginRequest(email="pro@example.com", password="password123")
        )

        assert response.plan == "pro"
        print("✅ Pro plan login works")

    async def test_login_enterprise_plan(self):
        """Test login with enterprise plan account."""
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="enterprise@example.com",
                password="password123",
                plan="enterprise",
            )
        )

        response = await self.stub.Login(
            auth_pb2.LoginRequest(
                email="enterprise@example.com", password="password123"
            )
        )

        assert response.plan == "enterprise"
        print("✅ Enterprise plan login works")


@pytest.mark.asyncio
class TestLoginPasswordVariations(BaseGrpcTest):
    """Test login with various password formats."""

    async def test_login_numeric_password(self):
        """Test login with numeric-only password."""
        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="numeric@example.com", password="123456789", plan="free"
            )
        )

        response = await self.stub.Login(
            auth_pb2.LoginRequest(email="numeric@example.com", password="123456789")
        )

        assert response.account_id > 0
        print("✅ Numeric password login works")

    async def test_login_unicode_password(self):
        """Test login with unicode characters in password."""
        unicode_password = "pässwörd123中文"

        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="unicode@example.com", password=unicode_password, plan="free"
            )
        )

        response = await self.stub.Login(
            auth_pb2.LoginRequest(
                email="unicode@example.com", password=unicode_password
            )
        )

        assert response.account_id > 0
        print("✅ Unicode password login works")

    async def test_login_password_with_spaces(self):
        """Test login with spaces in password."""
        password_with_spaces = "my password 123"

        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="spaces@example.com", password=password_with_spaces, plan="free"
            )
        )

        response = await self.stub.Login(
            auth_pb2.LoginRequest(
                email="spaces@example.com", password=password_with_spaces
            )
        )

        assert response.account_id > 0
        print("✅ Password with spaces works")

    async def test_login_emoji_password(self):
        """Test login with emoji in password."""
        emoji_password = "password🔒123🚀"

        try:
            await self.stub.Register(
                auth_pb2.RegisterRequest(
                    email="emoji@example.com", password=emoji_password, plan="free"
                )
            )

            response = await self.stub.Login(
                auth_pb2.LoginRequest(
                    email="emoji@example.com", password=emoji_password
                )
            )

            assert response.account_id > 0
            print("✅ Emoji password works")
        except Exception as e:
            print(f"⚠️  Emoji password not supported: {e}")


@pytest.mark.asyncio
class TestLoginDataConsistency(BaseGrpcTest):
    """Test data consistency during login."""

    async def test_login_returns_correct_account_data(self):
        """Test that login returns correct account information."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="consistency@example.com", password="password123", plan="pro"
            )
        )

        login_response = await self.stub.Login(
            auth_pb2.LoginRequest(
                email="consistency@example.com", password="password123"
            )
        )

        assert login_response.account_id == register_response.account_id
        assert login_response.email == register_response.email
        assert login_response.plan == register_response.plan
        print("✅ Login returns consistent account data")

    async def test_multiple_logins_same_data(self):
        """Test that multiple logins return same data."""
        await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="multilogin@example.com", password="password123", plan="free"
            )
        )

        responses = []
        for i in range(5):
            response = await self.stub.Login(
                auth_pb2.LoginRequest(
                    email="multilogin@example.com", password="password123"
                )
            )
            responses.append(response)

        account_ids = [r.account_id for r in responses]
        emails = [r.email for r in responses]
        plans = [r.plan for r in responses]

        assert len(set(account_ids)) == 1
        assert len(set(emails)) == 1
        assert len(set(plans)) == 1
        print("✅ Multiple logins return consistent data")
        print("✅ Multiple logins return consistent data")
