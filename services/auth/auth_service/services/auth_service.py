import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import auth_service.config as config
import auth_service.models as models
import auth_service.utils.jwt_utils as jwt_utils
import bcrypt
import pyotp
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AuthService:
    """
    Core authentication service.

    Responsibilities:
    - Account management (register, login)
    - Project management
    - API key generation and validation

    Note: Gateway handles rate limiting and JWT validation.
    This service provides the data Gateway needs.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def register(
        self,
        session: AsyncSession,
        email: str,
        password: str,
        name: str,
        plan: str = "free",
    ) -> models.Account:
        """Register new account."""

        if not self._validate_password(password):
            raise ValueError("Password does not meet complexity requirements")

        result = await session.execute(select(models.Account).where(models.Account.email == email))
        if result.scalar_one_or_none():
            raise ValueError("Email already registered")

        password_hash = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt(rounds=config.settings.BCRYPT_ROUNDS)
        ).decode()

        verification_token = secrets.token_hex(32)

        account = models.Account(
            email=email,
            password_hash=password_hash,
            name=name,
            plan=plan,
            status="active",
            email_verified=False,
            email_verification_token=verification_token,
            email_verification_sent_at=datetime.now(timezone.utc),
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)

        return account

    async def login(
        self,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> models.Account:
        """Verify credentials and return account."""

        if not self._validate_password(password):
            raise ValueError("Invalid credentials")

        result = await session.execute(
            select(models.Account).where(
                models.Account.email == email, models.Account.status == "active"
            )
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError("Invalid credentials")

        if not bcrypt.checkpw(password.encode(), account.password_hash.encode()):
            raise ValueError("Invalid credentials")

        return account

    async def get_account_by_id(
        self,
        session: AsyncSession,
        account_id: int,
    ) -> models.Account | None:
        """Get account by ID."""

        result = await session.execute(
            select(models.Account).where(models.Account.id == account_id)
        )
        return result.scalar_one_or_none()

    async def update_account_name(
        self,
        session: AsyncSession,
        account_id: int,
        name: str,
    ) -> models.Account:
        """Update account name."""

        if not name or not name.strip():
            raise ValueError("Name cannot be empty")

        if len(name) > 255:
            raise ValueError("Name is too long (max 255 characters)")

        result = await session.execute(
            select(models.Account).where(models.Account.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError("Account not found")

        account.name = name.strip()
        await session.commit()
        await session.refresh(account)

        return account

    async def change_password(
        self,
        session: AsyncSession,
        account_id: int,
        old_password: str,
        new_password: str,
    ) -> models.Account:
        """Change account password."""

        if not self._validate_password(new_password):
            raise ValueError("New password does not meet complexity requirements")

        result = await session.execute(
            select(models.Account).where(models.Account.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError("Account not found")

        if not bcrypt.checkpw(old_password.encode(), account.password_hash.encode()):
            raise ValueError("Current password is incorrect")

        new_password_hash = bcrypt.hashpw(
            new_password.encode(), bcrypt.gensalt(rounds=config.settings.BCRYPT_ROUNDS)
        ).decode()

        account.password_hash = new_password_hash
        await session.commit()
        await session.refresh(account)

        return account

    def _validate_password(self, password: str) -> bool:
        """Validate password length."""
        if len(password) < 8 or len(password) > 64:
            return False
        return True

    async def get_notification_preferences(
        self,
        session: AsyncSession,
        account_id: int,
    ) -> dict:
        """Get notification preferences for account."""

        result = await session.execute(
            select(models.Account).where(models.Account.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError("Account not found")

        return account.notification_preferences

    async def update_notification_preferences(
        self,
        session: AsyncSession,
        account_id: int,
        preferences: dict,
    ) -> dict:
        """Update notification preferences for account."""

        result = await session.execute(
            select(models.Account).where(models.Account.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError("Account not found")

        self._validate_notification_preferences(preferences)

        account.notification_preferences = preferences
        await session.commit()
        await session.refresh(account)

        return account.notification_preferences

    def _validate_notification_preferences(self, preferences: dict) -> None:
        """Validate notification preferences structure."""
        if not isinstance(preferences, dict):
            raise ValueError("Preferences must be a dictionary")

        if "enabled" not in preferences:
            raise ValueError("Preferences must include 'enabled' field")

        if not isinstance(preferences["enabled"], bool):
            raise ValueError("'enabled' field must be a boolean")

        if "projects" not in preferences:
            raise ValueError("Preferences must include 'projects' field")

        if not isinstance(preferences["projects"], dict):
            raise ValueError("'projects' field must be a dictionary")

        for project_id, settings in preferences["projects"].items():
            if not isinstance(settings, dict):
                raise ValueError(f"Settings for project {project_id} must be a dictionary")

            if "enabled" in settings and not isinstance(settings["enabled"], bool):
                raise ValueError(f"'enabled' field for project {project_id} must be a boolean")

            if "levels" in settings and not isinstance(settings["levels"], list):
                raise ValueError(f"'levels' field for project {project_id} must be a list")

            if "types" in settings and not isinstance(settings["types"], list):
                raise ValueError(f"'types' field for project {project_id} must be a list")

    _EMAIL_VERIFICATION_TTL_HOURS = 24

    async def verify_email(
        self,
        session: AsyncSession,
        token: str,
    ) -> None:
        """Verify an account's email using its verification token."""
        if not token:
            raise ValueError("Invalid or expired verification token")

        result = await session.execute(
            select(models.Account).where(models.Account.email_verification_token == token)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError("Invalid or expired verification token")

        if account.email_verified:
            # Already verified (token wasn't cleared yet, or double-submit) —
            # treat as success rather than an error.
            account.email_verification_token = None
            await session.commit()
            return

        sent_at = account.email_verification_sent_at
        if sent_at is None or datetime.now(timezone.utc) - sent_at > timedelta(
            hours=self._EMAIL_VERIFICATION_TTL_HOURS
        ):
            raise ValueError("Invalid or expired verification token")

        account.email_verified = True
        account.email_verification_token = None
        account.email_verification_sent_at = None
        await session.commit()

    async def resend_verification_email(
        self,
        session: AsyncSession,
        account_id: int,
    ) -> tuple[bool, str, str | None]:
        """
        Regenerate and return a fresh verification token for the account.

        Returns:
            (already_verified, email, verification_token) — verification_token
            is None when already_verified is True.
        """
        account = await self.get_account_by_id(session, account_id)
        if not account:
            raise ValueError("Account not found")

        if account.email_verified:
            return True, account.email, None

        verification_token = secrets.token_hex(32)
        account.email_verification_token = verification_token
        account.email_verification_sent_at = datetime.now(timezone.utc)
        await session.commit()

        return False, account.email, verification_token

    def _hash_backup_code(self, code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    def _generate_backup_codes(self, count: int = 10) -> list[str]:
        return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]

    async def setup_2fa(
        self,
        session: AsyncSession,
        account_id: int,
    ) -> tuple[str, str]:
        """
        Generate a pending TOTP secret for the account (not yet enabled).

        Returns:
            (secret, provisioning_uri)
        """
        account = await self.get_account_by_id(session, account_id)
        if not account:
            raise ValueError("Account not found")

        secret = pyotp.random_base32()
        account.totp_secret = secret
        await session.commit()

        provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=account.email, issuer_name="Ledger"
        )
        return secret, provisioning_uri

    async def verify_2fa_setup(
        self,
        session: AsyncSession,
        account_id: int,
        code: str,
    ) -> list[str]:
        """Verify the pending TOTP secret and enable 2FA. Returns plaintext backup codes."""
        account = await self.get_account_by_id(session, account_id)
        if not account:
            raise ValueError("Account not found")

        if not account.totp_secret:
            raise ValueError("No pending 2FA setup — call setup first")

        if not pyotp.TOTP(account.totp_secret).verify(code.strip(), valid_window=1):
            raise ValueError("Invalid verification code")

        backup_codes = self._generate_backup_codes()
        account.totp_enabled = True
        account.totp_backup_codes = [self._hash_backup_code(c) for c in backup_codes]
        await session.commit()

        return backup_codes

    async def disable_2fa(
        self,
        session: AsyncSession,
        account_id: int,
        password: str,
    ) -> None:
        """Disable 2FA for the account. Requires current password re-entry."""
        account = await self.get_account_by_id(session, account_id)
        if not account:
            raise ValueError("Account not found")

        if not bcrypt.checkpw(password.encode(), account.password_hash.encode()):
            raise ValueError("Current password is incorrect")

        if not account.totp_enabled:
            raise ValueError("2FA is not enabled for this account")

        account.totp_enabled = False
        account.totp_secret = None
        account.totp_backup_codes = None
        await session.commit()

    async def verify_totp_code_or_backup(
        self,
        session: AsyncSession,
        account_id: int,
        code: str,
    ) -> models.Account:
        """
        Verify a TOTP code (or a backup code, consuming it) for an account
        that has 2FA enabled. Used at the tail end of the 2FA login flow.
        """
        account = await self.get_account_by_id(session, account_id)
        if not account or not account.totp_enabled or not account.totp_secret:
            raise ValueError("2FA is not enabled for this account")

        code = code.strip()

        if pyotp.TOTP(account.totp_secret).verify(code, valid_window=1):
            return account

        code_hash = self._hash_backup_code(code)
        backup_codes = account.totp_backup_codes or []
        if code_hash in backup_codes:
            remaining = [c for c in backup_codes if c != code_hash]
            account.totp_backup_codes = remaining
            await session.commit()
            return account

        raise ValueError("Invalid 2FA code")

    async def list_sessions(
        self,
        session: AsyncSession,
        account_id: int,
        current_raw_token: str | None = None,
    ) -> list[models.RefreshToken]:
        """List active (non-revoked, non-expired) sessions for an account."""
        result = await session.execute(
            select(models.RefreshToken)
            .where(
                models.RefreshToken.account_id == account_id,
                models.RefreshToken.revoked == False,  # noqa: E712
                models.RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .order_by(models.RefreshToken.last_used_at.desc().nulls_last())
        )
        return list(result.scalars().all())

    async def revoke_session(
        self,
        session: AsyncSession,
        account_id: int,
        session_id: int,
    ) -> None:
        """Revoke a single session, scoped to the requesting account."""
        result = await session.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.id == session_id,
                models.RefreshToken.account_id == account_id,
            )
        )
        token_record = result.scalar_one_or_none()
        if not token_record:
            raise ValueError("Session not found")

        token_record.revoked = True
        await session.commit()

    async def revoke_all_sessions(
        self,
        session: AsyncSession,
        account_id: int,
        current_raw_token: str | None = None,
        include_current: bool = False,
    ) -> int:
        """Revoke all sessions for an account, optionally excluding the current one."""
        current_hash = (
            jwt_utils.hash_refresh_token(current_raw_token) if current_raw_token else None
        )

        result = await session.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.account_id == account_id,
                models.RefreshToken.revoked == False,  # noqa: E712
            )
        )
        tokens = result.scalars().all()

        count = 0
        for token in tokens:
            if (
                not include_current
                and current_hash is not None
                and token.token_hash == current_hash
            ):
                continue
            token.revoked = True
            count += 1

        await session.commit()
        return count

    async def create_project(
        self,
        session: AsyncSession,
        account_id: int,
        name: str,
        slug: str,
        environment: str = "production",
    ) -> models.Project:
        """Create new project and add creator as owner member."""

        result = await session.execute(select(models.Project).where(models.Project.slug == slug))
        if result.scalar_one_or_none():
            raise ValueError(f"Slug '{slug}' already exists")

        project = models.Project(
            account_id=account_id,
            name=name,
            slug=slug,
            environment=environment,
            daily_quota=config.settings.DEFAULT_DAILY_QUOTA,
        )
        session.add(project)
        await session.flush()

        member = models.ProjectMember(
            project_id=project.id,
            account_id=account_id,
            role="owner",
        )
        session.add(member)
        await session.commit()
        await session.refresh(project)

        return project

    async def get_projects_for_account(
        self,
        session: AsyncSession,
        account_id: int,
    ) -> list[tuple[models.Project, str]]:
        """Get all projects account is a member of, with role per project."""

        result = await session.execute(
            select(models.Project, models.ProjectMember.role)
            .join(
                models.ProjectMember,
                models.ProjectMember.project_id == models.Project.id,
            )
            .where(models.ProjectMember.account_id == account_id)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_project_by_id(
        self,
        session: AsyncSession,
        project_id: int,
    ) -> models.Project | None:
        """Get project by ID."""

        result = await session.execute(
            select(models.Project).where(models.Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_daily_usage(
        self,
        session: AsyncSession,
        project_id: int,
        date: str,
    ) -> models.DailyUsage | None:
        """Get daily usage for a project on a specific date."""
        from datetime import datetime

        date_obj = datetime.fromisoformat(date)
        start_of_day = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day.replace(hour=23, minute=59, second=59, microsecond=999999)

        result = await session.execute(
            select(models.DailyUsage).where(
                models.DailyUsage.project_id == project_id,
                models.DailyUsage.date >= start_of_day,
                models.DailyUsage.date <= end_of_day,
            )
        )
        return result.scalar_one_or_none()

    async def create_api_key(
        self,
        session: AsyncSession,
        project_id: int,
        name: str | None = None,
    ) -> tuple[str, models.ApiKey]:
        """
        Create API key.
        Returns: (full_key, api_key_record)
        WARNING: full_key is shown only once!
        """

        if name:
            result = await session.execute(
                select(models.ApiKey).where(
                    models.ApiKey.project_id == project_id,
                    models.ApiKey.name == name,
                    models.ApiKey.status == "active",
                )
            )
            if result.scalar_one_or_none():
                raise ValueError(f"API key with name '{name}' already exists for this project")

        random_part = secrets.token_urlsafe(32)
        full_key = f"ledger_{random_part}"
        key_prefix = full_key[:20]

        key_hash = hashlib.sha256(full_key.encode()).hexdigest()

        api_key = models.ApiKey(
            project_id=project_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=name,
            status="active",
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        return full_key, api_key

    async def validate_api_key(
        self,
        session: AsyncSession,
        api_key: str,
    ) -> tuple[bool, int | None, dict]:
        """
        Validate API key and return project info.

        Returns: (is_valid, project_id, project_info)
        Uses a single O(1) indexed lookup by SHA-256 hash.
        """

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        cache_key = f"api_key:{key_hash}"

        try:
            cached = await self.redis.hgetall(cache_key)
        except RedisError as e:
            logger.warning("Redis HGETALL failed for api_key cache (treating as miss): %s", e)
            cached = {}
        if cached:
            return (
                True,
                int(cached[b"project_id"]),
                {
                    "project_id": int(cached[b"project_id"]),
                    "account_id": int(cached.get(b"account_id", 0)),
                    "daily_quota": int(cached[b"daily_quota"]),
                    "retention_days": int(cached[b"retention_days"]),
                    "rate_limit_per_minute": int(cached[b"rate_limit_per_minute"]),
                    "rate_limit_per_hour": int(cached[b"rate_limit_per_hour"]),
                },
            )

        result = await session.execute(
            select(models.ApiKey).where(
                models.ApiKey.key_hash == key_hash,
                models.ApiKey.status == "active",
            )
        )
        key_record = result.scalar_one_or_none()

        if not key_record:
            return (False, None, {"error": "Invalid API key"})

        if key_record.expires_at and key_record.expires_at < datetime.now(timezone.utc):
            return (False, None, {"error": "API key expired"})

        project = await self.get_project_by_id(session, key_record.project_id)
        if not project:
            return (False, None, {"error": "Project not found"})

        key_record.last_used_at = datetime.now(timezone.utc)
        await session.commit()

        project_info = {
            "project_id": project.id,
            "account_id": project.account_id,
            "daily_quota": project.daily_quota,
            "retention_days": project.retention_days,
            "rate_limit_per_minute": key_record.rate_limit_per_minute,
            "rate_limit_per_hour": key_record.rate_limit_per_hour,
        }

        try:
            await self.redis.hset(cache_key, mapping=project_info)
            await self.redis.expire(cache_key, config.settings.CACHE_TTL_SECONDS)
        except RedisError as e:
            logger.warning("Redis HSET failed for api_key cache: %s", e)

        return (True, project.id, project_info)

    async def revoke_api_key(
        self,
        session: AsyncSession,
        key_id: int,
        requester_account_id: int | None = None,
    ) -> None:
        """
        Revoke API key and purge its cache entry.

        If requester_account_id is provided, the requester must be the
        *owner* of the key's project — members with 'member' role cannot
        revoke API keys (they can grant/revoke ingest access for everyone
        on the project).
        """

        result = await session.execute(select(models.ApiKey).where(models.ApiKey.id == key_id))
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise ValueError("API key not found")

        if requester_account_id is not None:
            role = await self.get_project_role(session, api_key.project_id, requester_account_id)
            if role != "owner":
                raise PermissionError("Only project owners can revoke API keys")

        key_hash = api_key.key_hash
        api_key.status = "revoked"
        await session.commit()

        await self.redis.delete(f"api_key:{key_hash}")

    async def list_api_keys(
        self,
        session: AsyncSession,
        project_id: int,
    ) -> list[models.ApiKey]:
        """List all API keys for a project."""

        result = await session.execute(
            select(models.ApiKey)
            .where(models.ApiKey.project_id == project_id)
            .order_by(models.ApiKey.created_at.desc())
        )
        api_keys = result.scalars().all()

        return list(api_keys)

    def _generate_invite_code(self) -> tuple[str, str]:
        """Generate invite code and its SHA-256 hash. Returns (raw_code, code_hash)."""
        raw_bytes = secrets.token_bytes(9)
        code = base64.b32encode(raw_bytes).decode()[:12].upper()
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        return code, code_hash

    def _hash_invite_code(self, code: str) -> str:
        normalized = code.replace("-", "").upper()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _format_invite_code(self, code: str) -> str:
        return f"{code[:4]}-{code[4:8]}-{code[8:12]}"

    async def get_project_role(
        self,
        session: AsyncSession,
        project_id: int,
        account_id: int,
    ) -> str | None:
        """Return member's role or None if not a member."""
        result = await session.execute(
            select(models.ProjectMember.role).where(
                models.ProjectMember.project_id == project_id,
                models.ProjectMember.account_id == account_id,
            )
        )
        row = result.scalar_one_or_none()
        return row

    async def generate_invite_code(
        self,
        session: AsyncSession,
        project_id: int,
        requester_account_id: int,
    ) -> tuple[str, datetime]:
        """Generate invite code for a project. Requester must be owner."""
        role = await self.get_project_role(session, project_id, requester_account_id)
        if role != "owner":
            raise PermissionError("Only project owners can generate invite codes")

        code, code_hash = self._generate_invite_code()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        invite = models.ProjectInviteCode(
            project_id=project_id,
            code_hash=code_hash,
            created_by=requester_account_id,
            expires_at=expires_at,
        )
        session.add(invite)
        await session.commit()

        return self._format_invite_code(code), expires_at

    async def accept_invite_code(
        self,
        session: AsyncSession,
        code: str,
        account_id: int,
    ) -> models.Project:
        """Accept invite code and add account as project member."""
        code_hash = self._hash_invite_code(code)

        result = await session.execute(
            select(models.ProjectInviteCode).where(
                models.ProjectInviteCode.code_hash == code_hash,
                models.ProjectInviteCode.used_at == None,  # noqa: E711
                models.ProjectInviteCode.expires_at > datetime.now(timezone.utc),
            )
        )
        invite = result.scalar_one_or_none()
        if not invite:
            raise ValueError("Invalid or expired invite code")

        existing_role = await self.get_project_role(session, invite.project_id, account_id)
        if existing_role is not None:
            raise ValueError("Already a member of this project")

        member = models.ProjectMember(
            project_id=invite.project_id,
            account_id=account_id,
            role="member",
        )
        session.add(member)

        invite.used_at = datetime.now(timezone.utc)
        invite.used_by = account_id
        await session.commit()

        project = await self.get_project_by_id(session, invite.project_id)
        return project

    async def list_project_members(
        self,
        session: AsyncSession,
        project_id: int,
        requester_account_id: int,
    ) -> list[dict]:
        """List all members of a project. Requester must be a member."""
        role = await self.get_project_role(session, project_id, requester_account_id)
        if role is None:
            raise PermissionError("Not a member of this project")

        result = await session.execute(
            select(models.ProjectMember, models.Account)
            .join(models.Account, models.Account.id == models.ProjectMember.account_id)
            .where(models.ProjectMember.project_id == project_id)
            .order_by(models.ProjectMember.joined_at)
        )
        rows = result.all()

        return [
            {
                "account_id": member.account_id,
                "email": account.email,
                "name": account.name,
                "role": member.role,
                "joined_at": member.joined_at.isoformat(),
            }
            for member, account in rows
        ]

    async def update_project(
        self,
        session: AsyncSession,
        project_id: int,
        requester_account_id: int,
        retention_days: int | None = None,
        daily_quota: int | None = None,
    ) -> models.Project:
        """Update a project's retention/quota settings. Requester must be owner."""
        requester_role = await self.get_project_role(session, project_id, requester_account_id)
        if requester_role != "owner":
            raise PermissionError("Only project owners can update project settings")

        result = await session.execute(
            select(models.Project).where(models.Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        if retention_days is not None:
            if not (1 <= retention_days <= 365):
                raise ValueError("retention_days must be between 1 and 365")
            project.retention_days = retention_days

        if daily_quota is not None:
            if daily_quota < 1:
                raise ValueError("daily_quota must be a positive integer")
            project.daily_quota = daily_quota

        await session.flush()
        return project

    async def remove_project_member(
        self,
        session: AsyncSession,
        project_id: int,
        account_id: int,
        requester_account_id: int,
    ) -> None:
        """Remove a member from a project. Requester must be owner."""
        requester_role = await self.get_project_role(session, project_id, requester_account_id)
        if requester_role != "owner":
            raise PermissionError("Only project owners can remove members")

        if account_id == requester_account_id:
            raise ValueError(
                "Owners cannot remove themselves — use leave_project or transfer ownership"
            )

        result = await session.execute(
            select(models.ProjectMember).where(
                models.ProjectMember.project_id == project_id,
                models.ProjectMember.account_id == account_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ValueError("Member not found in project")

        await session.delete(member)
        await session.commit()

        await self.redis.delete(f"member:{project_id}:{account_id}")

    async def leave_project(
        self,
        session: AsyncSession,
        project_id: int,
        account_id: int,
    ) -> None:
        """Leave a project. Owners cannot leave if they are the sole owner."""
        role = await self.get_project_role(session, project_id, account_id)
        if role is None:
            raise ValueError("Not a member of this project")

        if role == "owner":
            result = await session.execute(
                select(models.ProjectMember).where(
                    models.ProjectMember.project_id == project_id,
                    models.ProjectMember.role == "owner",
                )
            )
            owners = result.scalars().all()
            if len(owners) <= 1:
                raise ValueError(
                    "Cannot leave — you are the sole owner. Delete the project or transfer ownership first."
                )

        result = await session.execute(
            select(models.ProjectMember).where(
                models.ProjectMember.project_id == project_id,
                models.ProjectMember.account_id == account_id,
            )
        )
        member = result.scalar_one_or_none()
        await session.delete(member)
        await session.commit()

        await self.redis.delete(f"member:{project_id}:{account_id}")

    async def create_refresh_token(
        self,
        session: AsyncSession,
        account_id: int,
        device_info: str | None = None,
    ) -> tuple[str, models.RefreshToken]:
        """
        Create refresh token for account.

        Args:
            session: Database session
            account_id: Account ID to create token for
            device_info: Optional device/browser info

        Returns:
            Tuple of (raw_token, refresh_token_record)
            WARNING: raw_token is shown only once!
        """
        raw_token, token_hash = jwt_utils.create_refresh_token()

        expires_at = jwt_utils.get_token_expiration("refresh")

        refresh_token = models.RefreshToken(
            account_id=account_id,
            token_hash=token_hash,
            device_info=device_info,
            expires_at=expires_at,
            revoked=False,
        )
        session.add(refresh_token)
        await session.commit()
        await session.refresh(refresh_token)

        return raw_token, refresh_token

    async def validate_refresh_token(
        self,
        session: AsyncSession,
        raw_token: str,
    ) -> models.Account | None:
        token_hash = jwt_utils.hash_refresh_token(raw_token)

        result = await session.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.token_hash == token_hash,
                models.RefreshToken.revoked == False,
                models.RefreshToken.expires_at > datetime.now(timezone.utc),
            )
        )
        token_record = result.scalars().first()

        if not token_record:
            return None

        token_record.last_used_at = datetime.now(timezone.utc)
        await session.commit()

        return await self.get_account_by_id(session, token_record.account_id)

    async def revoke_refresh_token(
        self,
        session: AsyncSession,
        raw_token: str,
    ) -> bool:
        token_hash = jwt_utils.hash_refresh_token(raw_token)

        result = await session.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.token_hash == token_hash,
                models.RefreshToken.revoked == False,
            )
        )
        token_record = result.scalars().first()

        if not token_record:
            return False

        token_record.revoked = True
        await session.commit()
        return True

    async def revoke_all_refresh_tokens(
        self,
        session: AsyncSession,
        account_id: int,
    ) -> int:
        """
        Revoke all refresh tokens for an account (logout from all devices).

        Args:
            session: Database session
            account_id: Account ID

        Returns:
            Number of tokens revoked
        """
        result = await session.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.account_id == account_id,
                models.RefreshToken.revoked == False,
            )
        )
        tokens = result.scalars().all()

        count = 0
        for token in tokens:
            token.revoked = True
            count += 1

        await session.commit()
        return count
