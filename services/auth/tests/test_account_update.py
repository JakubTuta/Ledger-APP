import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestUpdateAccountName(BaseGrpcTest):
    """Test account name updates."""

    async def test_update_name_success(self):
        """Test successful name update."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="nameupdate@example.com", password="Password123", plan="free"
            )
        )

        update_request = auth_pb2.UpdateAccountNameRequest(
            account_id=register_response.account_id, name="Updated Name"
        )
        update_response = await self.stub.UpdateAccountName(update_request)

        assert update_response.success is True
        assert update_response.name == "Updated Name"

        account = await self.stub.GetAccount(
            auth_pb2.GetAccountRequest(account_id=register_response.account_id)
        )
        assert account.name == "Updated Name"
        print(f"✅ Name updated successfully to: {account.name}")

    async def test_update_name_with_whitespace(self):
        """Test name update trims whitespace."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="whitespace@example.com", password="Password123", plan="free"
            )
        )

        update_request = auth_pb2.UpdateAccountNameRequest(
            account_id=register_response.account_id, name="  Trimmed Name  "
        )
        update_response = await self.stub.UpdateAccountName(update_request)

        assert update_response.success is True
        assert update_response.name == "Trimmed Name"
        print(f"✅ Name correctly trimmed whitespace")

    async def test_update_name_empty_fails(self):
        """Test empty name update fails."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="emptyname@example.com", password="Password123", plan="free"
            )
        )

        update_request = auth_pb2.UpdateAccountNameRequest(
            account_id=register_response.account_id, name=""
        )

        try:
            await self.stub.UpdateAccountName(update_request)
            assert False, "Should have raised error for empty name"
        except Exception as e:
            assert "empty" in str(e).lower()
            print(f"✅ Correctly rejected empty name")

    async def test_update_name_whitespace_only_fails(self):
        """Test whitespace-only name update fails."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="whitespaceonly@example.com",
                password="Password123",
                plan="free",
            )
        )

        update_request = auth_pb2.UpdateAccountNameRequest(
            account_id=register_response.account_id, name="   "
        )

        try:
            await self.stub.UpdateAccountName(update_request)
            assert False, "Should have raised error for whitespace-only name"
        except Exception as e:
            assert "empty" in str(e).lower()
            print(f"✅ Correctly rejected whitespace-only name")

    async def test_update_name_too_long_fails(self):
        """Test name that's too long fails."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="longname@example.com", password="Password123", plan="free"
            )
        )

        long_name = "a" * 256
        update_request = auth_pb2.UpdateAccountNameRequest(
            account_id=register_response.account_id, name=long_name
        )

        try:
            await self.stub.UpdateAccountName(update_request)
            assert False, "Should have raised error for name too long"
        except Exception as e:
            assert "too long" in str(e).lower()
            print(f"✅ Correctly rejected name that's too long")

    async def test_update_name_nonexistent_account_fails(self):
        """Test updating name for non-existent account fails."""
        update_request = auth_pb2.UpdateAccountNameRequest(
            account_id=99999, name="Test Name"
        )

        try:
            await self.stub.UpdateAccountName(update_request)
            assert False, "Should have raised error for non-existent account"
        except Exception as e:
            assert "not found" in str(e).lower()
            print(f"✅ Correctly rejected non-existent account")


@pytest.mark.asyncio
class TestChangePassword(BaseGrpcTest):
    """Test password change functionality."""

    async def test_change_password_success(self):
        """Test successful password change."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="pwchange@example.com", password="OldPass123", plan="free"
            )
        )

        change_request = auth_pb2.ChangePasswordRequest(
            account_id=register_response.account_id,
            old_password="OldPass123",
            new_password="NewPass456",
        )
        change_response = await self.stub.ChangePassword(change_request)

        assert change_response.success is True

        login_old = auth_pb2.LoginRequest(
            email="pwchange@example.com", password="OldPass123"
        )
        try:
            await self.stub.Login(login_old)
            assert False, "Old password should not work"
        except Exception:
            pass

        login_new = auth_pb2.LoginRequest(
            email="pwchange@example.com", password="NewPass456"
        )
        login_response = await self.stub.Login(login_new)
        assert login_response.account_id == register_response.account_id
        print(f"✅ Password changed successfully")

    async def test_change_password_wrong_old_password_fails(self):
        """Test password change with wrong old password fails."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="wrongold@example.com", password="RealPass123", plan="free"
            )
        )

        change_request = auth_pb2.ChangePasswordRequest(
            account_id=register_response.account_id,
            old_password="WrongOld123",
            new_password="NewPass456",
        )

        try:
            await self.stub.ChangePassword(change_request)
            assert False, "Should have raised error for wrong old password"
        except Exception as e:
            assert "incorrect" in str(e).lower()
            print(f"✅ Correctly rejected wrong old password")

    async def test_change_password_too_short_fails(self):
        """Test password change with too short password fails."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="short@example.com", password="Password123", plan="free"
            )
        )

        change_request = auth_pb2.ChangePasswordRequest(
            account_id=register_response.account_id,
            old_password="Password123",
            new_password="short1",
        )

        try:
            await self.stub.ChangePassword(change_request)
            assert False, "Should have raised error for password too short"
        except Exception as e:
            assert "complexity" in str(e).lower() or "requirements" in str(e).lower()
            print(f"✅ Correctly rejected password that's too short")

    async def test_change_password_too_long_fails(self):
        """Test password change with too long password fails."""
        register_response = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="long@example.com", password="Password123", plan="free"
            )
        )

        long_password = "P" + "a" * 64 + "ssword123"
        change_request = auth_pb2.ChangePasswordRequest(
            account_id=register_response.account_id,
            old_password="Password123",
            new_password=long_password,
        )

        try:
            await self.stub.ChangePassword(change_request)
            assert False, "Should have raised error for password too long"
        except Exception as e:
            assert "complexity" in str(e).lower() or "requirements" in str(e).lower()
            print(f"✅ Correctly rejected password that's too long")

    async def test_change_password_nonexistent_account_fails(self):
        """Test changing password for non-existent account fails."""
        change_request = auth_pb2.ChangePasswordRequest(
            account_id=99999,
            old_password="OldPass123",
            new_password="NewPass456",
        )

        try:
            await self.stub.ChangePassword(change_request)
            assert False, "Should have raised error for non-existent account"
        except Exception as e:
            assert "not found" in str(e).lower()
            print(f"✅ Correctly rejected non-existent account")
