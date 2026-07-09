import pyotp
import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


async def _register_and_login(stub, email: str, password: str = "Password123"):
    await stub.Register(auth_pb2.RegisterRequest(email=email, password=password, plan="free"))
    login = await stub.Login(auth_pb2.LoginRequest(email=email, password=password))
    return login


@pytest.mark.asyncio
class TestEmailVerification(BaseGrpcTest):
    async def test_verify_email_success(self):
        register = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="verify@example.com", password="Password123", plan="free"
            )
        )
        assert register.email_verification_token

        response = await self.stub.VerifyEmail(
            auth_pb2.VerifyEmailRequest(token=register.email_verification_token)
        )

        assert response.success is True

        account = await self.stub.GetAccount(
            auth_pb2.GetAccountRequest(account_id=register.account_id)
        )
        assert account.email_verified is True

    async def test_verify_email_invalid_token_fails(self):
        with pytest.raises(Exception) as exc_info:
            await self.stub.VerifyEmail(auth_pb2.VerifyEmailRequest(token="not-a-real-token"))
        assert "INVALID_ARGUMENT" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    async def test_verify_email_token_single_use(self):
        register = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="singleuse@example.com", password="Password123", plan="free"
            )
        )
        await self.stub.VerifyEmail(
            auth_pb2.VerifyEmailRequest(token=register.email_verification_token)
        )

        with pytest.raises(Exception):
            await self.stub.VerifyEmail(
                auth_pb2.VerifyEmailRequest(token=register.email_verification_token)
            )

    async def test_resend_verification_email_issues_new_token(self):
        register = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="resend@example.com", password="Password123", plan="free"
            )
        )

        response = await self.stub.ResendVerificationEmail(
            auth_pb2.ResendVerificationEmailRequest(account_id=register.account_id)
        )

        assert response.success is True
        assert response.already_verified is False
        assert response.verification_token
        assert response.verification_token != register.email_verification_token

    async def test_resend_verification_email_already_verified(self):
        register = await self.stub.Register(
            auth_pb2.RegisterRequest(
                email="alreadyverified@example.com", password="Password123", plan="free"
            )
        )
        await self.stub.VerifyEmail(
            auth_pb2.VerifyEmailRequest(token=register.email_verification_token)
        )

        response = await self.stub.ResendVerificationEmail(
            auth_pb2.ResendVerificationEmailRequest(account_id=register.account_id)
        )

        assert response.already_verified is True


@pytest.mark.asyncio
class TestTwoFactorAuth(BaseGrpcTest):
    async def test_setup_2fa_returns_secret_and_uri(self):
        login = await _register_and_login(self.stub, "2fasetup@example.com")

        response = await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))

        assert response.secret
        assert "otpauth://totp/" in response.provisioning_uri

    async def test_verify_2fa_setup_enables_2fa_and_returns_backup_codes(self):
        login = await _register_and_login(self.stub, "2faverify@example.com")
        setup = await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))

        code = pyotp.TOTP(setup.secret).now()
        response = await self.stub.Verify2FASetup(
            auth_pb2.Verify2FASetupRequest(account_id=login.account_id, code=code)
        )

        assert response.success is True
        assert len(response.backup_codes) > 0

        account = await self.stub.GetAccount(
            auth_pb2.GetAccountRequest(account_id=login.account_id)
        )
        assert account.totp_enabled is True

    async def test_verify_2fa_setup_wrong_code_fails(self):
        login = await _register_and_login(self.stub, "2fawrong@example.com")
        await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))

        with pytest.raises(Exception):
            await self.stub.Verify2FASetup(
                auth_pb2.Verify2FASetupRequest(account_id=login.account_id, code="000000")
            )

    async def test_login_with_2fa_enabled_requires_second_factor(self):
        email = "2falogin@example.com"
        password = "Password123"
        login = await _register_and_login(self.stub, email, password)
        setup = await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))
        code = pyotp.TOTP(setup.secret).now()
        await self.stub.Verify2FASetup(
            auth_pb2.Verify2FASetupRequest(account_id=login.account_id, code=code)
        )

        second_login = await self.stub.Login(auth_pb2.LoginRequest(email=email, password=password))

        assert second_login.requires_2fa is True
        assert not second_login.access_token

    async def test_verify_totp_login_completes_with_valid_code(self):
        email = "2facomplete@example.com"
        password = "Password123"
        login = await _register_and_login(self.stub, email, password)
        setup = await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))
        enable_code = pyotp.TOTP(setup.secret).now()
        await self.stub.Verify2FASetup(
            auth_pb2.Verify2FASetupRequest(account_id=login.account_id, code=enable_code)
        )

        login_code = pyotp.TOTP(setup.secret).now()
        response = await self.stub.VerifyTOTPLogin(
            auth_pb2.VerifyTOTPLoginRequest(
                account_id=login.account_id, code=login_code, device_info="pytest"
            )
        )

        assert response.success is True
        assert response.access_token
        assert response.refresh_token

    async def test_verify_totp_login_wrong_code_fails(self):
        login = await _register_and_login(self.stub, "2fabadcode@example.com")
        setup = await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))
        enable_code = pyotp.TOTP(setup.secret).now()
        await self.stub.Verify2FASetup(
            auth_pb2.Verify2FASetupRequest(account_id=login.account_id, code=enable_code)
        )

        with pytest.raises(Exception):
            await self.stub.VerifyTOTPLogin(
                auth_pb2.VerifyTOTPLoginRequest(
                    account_id=login.account_id, code="000000", device_info="pytest"
                )
            )

    async def test_verify_totp_login_backup_code_is_single_use(self):
        login = await _register_and_login(self.stub, "2fabackup@example.com")
        setup = await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))
        enable_code = pyotp.TOTP(setup.secret).now()
        verify = await self.stub.Verify2FASetup(
            auth_pb2.Verify2FASetupRequest(account_id=login.account_id, code=enable_code)
        )
        backup_code = verify.backup_codes[0]

        response = await self.stub.VerifyTOTPLogin(
            auth_pb2.VerifyTOTPLoginRequest(
                account_id=login.account_id, code=backup_code, device_info="pytest"
            )
        )
        assert response.success is True

        with pytest.raises(Exception):
            await self.stub.VerifyTOTPLogin(
                auth_pb2.VerifyTOTPLoginRequest(
                    account_id=login.account_id, code=backup_code, device_info="pytest"
                )
            )

    async def test_disable_2fa_requires_correct_password(self):
        email = "2fadisable@example.com"
        password = "Password123"
        login = await _register_and_login(self.stub, email, password)
        setup = await self.stub.Setup2FA(auth_pb2.Setup2FARequest(account_id=login.account_id))
        enable_code = pyotp.TOTP(setup.secret).now()
        await self.stub.Verify2FASetup(
            auth_pb2.Verify2FASetupRequest(account_id=login.account_id, code=enable_code)
        )

        with pytest.raises(Exception):
            await self.stub.Disable2FA(
                auth_pb2.Disable2FARequest(account_id=login.account_id, password="WrongPass123")
            )

        response = await self.stub.Disable2FA(
            auth_pb2.Disable2FARequest(account_id=login.account_id, password=password)
        )
        assert response.success is True

        account = await self.stub.GetAccount(
            auth_pb2.GetAccountRequest(account_id=login.account_id)
        )
        assert account.totp_enabled is False


@pytest.mark.asyncio
class TestRefreshTokenRotation(BaseGrpcTest):
    async def test_refresh_token_issues_new_tokens(self):
        login = await _register_and_login(self.stub, "refresh@example.com")

        response = await self.stub.RefreshToken(
            auth_pb2.RefreshTokenRequest(refresh_token=login.refresh_token)
        )

        assert response.access_token
        assert response.refresh_token
        assert response.refresh_token != login.refresh_token
        assert response.account_id == login.account_id

    async def test_refresh_token_old_token_revoked_after_rotation(self):
        login = await _register_and_login(self.stub, "refreshrotate@example.com")

        await self.stub.RefreshToken(
            auth_pb2.RefreshTokenRequest(refresh_token=login.refresh_token)
        )

        with pytest.raises(Exception) as exc_info:
            await self.stub.RefreshToken(
                auth_pb2.RefreshTokenRequest(refresh_token=login.refresh_token)
            )
        assert "UNAUTHENTICATED" in str(exc_info.value)

    async def test_refresh_token_invalid_token_rejected(self):
        with pytest.raises(Exception) as exc_info:
            await self.stub.RefreshToken(
                auth_pb2.RefreshTokenRequest(refresh_token="not-a-real-refresh-token")
            )
        assert "UNAUTHENTICATED" in str(exc_info.value)


@pytest.mark.asyncio
class TestSessionManagement(BaseGrpcTest):
    async def test_list_sessions_shows_current_session(self):
        login = await _register_and_login(self.stub, "sessions@example.com")

        response = await self.stub.ListSessions(
            auth_pb2.ListSessionsRequest(
                account_id=login.account_id,
                current_refresh_token=login.refresh_token,
            )
        )

        assert len(response.sessions) == 1
        assert response.sessions[0].is_current is True

    async def test_list_sessions_multiple_devices(self):
        email = "multidevice@example.com"
        password = "Password123"
        login1 = await _register_and_login(self.stub, email, password)
        await self.stub.Login(auth_pb2.LoginRequest(email=email, password=password))

        response = await self.stub.ListSessions(
            auth_pb2.ListSessionsRequest(
                account_id=login1.account_id,
                current_refresh_token=login1.refresh_token,
            )
        )

        assert len(response.sessions) == 2
        current_flags = [s.is_current for s in response.sessions]
        assert current_flags.count(True) == 1

    async def test_revoke_session_removes_it_from_list(self):
        email = "revoke@example.com"
        password = "Password123"
        login1 = await _register_and_login(self.stub, email, password)
        await self.stub.Login(auth_pb2.LoginRequest(email=email, password=password))

        sessions = await self.stub.ListSessions(
            auth_pb2.ListSessionsRequest(account_id=login1.account_id)
        )
        assert len(sessions.sessions) == 2
        target_id = sessions.sessions[0].id

        response = await self.stub.RevokeSession(
            auth_pb2.RevokeSessionRequest(account_id=login1.account_id, session_id=target_id)
        )
        assert response.success is True

        sessions_after = await self.stub.ListSessions(
            auth_pb2.ListSessionsRequest(account_id=login1.account_id)
        )
        assert len(sessions_after.sessions) == 1
        assert sessions_after.sessions[0].id != target_id

    async def test_revoke_session_not_found(self):
        login = await _register_and_login(self.stub, "revokenotfound@example.com")

        with pytest.raises(Exception) as exc_info:
            await self.stub.RevokeSession(
                auth_pb2.RevokeSessionRequest(account_id=login.account_id, session_id=999999)
            )
        assert "NOT_FOUND" in str(exc_info.value)

    async def test_revoke_all_sessions_excludes_current_by_default(self):
        email = "revokeall@example.com"
        password = "Password123"
        login1 = await _register_and_login(self.stub, email, password)
        await self.stub.Login(auth_pb2.LoginRequest(email=email, password=password))
        await self.stub.Login(auth_pb2.LoginRequest(email=email, password=password))

        response = await self.stub.RevokeAllSessions(
            auth_pb2.RevokeAllSessionsRequest(
                account_id=login1.account_id,
                current_refresh_token=login1.refresh_token,
                include_current=False,
            )
        )
        assert response.revoked_count == 2

        sessions_after = await self.stub.ListSessions(
            auth_pb2.ListSessionsRequest(account_id=login1.account_id)
        )
        assert len(sessions_after.sessions) == 1

    async def test_revoke_all_sessions_including_current(self):
        email = "revokeallincludingcurrent@example.com"
        password = "Password123"
        login1 = await _register_and_login(self.stub, email, password)
        await self.stub.Login(auth_pb2.LoginRequest(email=email, password=password))

        response = await self.stub.RevokeAllSessions(
            auth_pb2.RevokeAllSessionsRequest(
                account_id=login1.account_id,
                current_refresh_token=login1.refresh_token,
                include_current=True,
            )
        )
        assert response.revoked_count == 2

        sessions_after = await self.stub.ListSessions(
            auth_pb2.ListSessionsRequest(account_id=login1.account_id)
        )
        assert len(sessions_after.sessions) == 0
