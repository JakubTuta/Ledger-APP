import secrets
from datetime import datetime, timezone

import auth_service.config as config
import auth_service.models as models
import auth_service.utils.jwt_utils as jwt_utils
import bcrypt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


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

    # ==================== Accounts ====================

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

        result = await session.execute(
            select(models.Account).where(models.Account.email == email)
        )
        if result.scalar_one_or_none():
            raise ValueError("Email already registered")

        password_hash = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt(rounds=config.settings.BCRYPT_ROUNDS)
        ).decode()

        account = models.Account(
            email=email,
            password_hash=password_hash,
            name=name,
            plan=plan,
            status="active",
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

    # ==================== Projects ====================

    async def create_project(
        self,
        session: AsyncSession,
        account_id: int,
        name: str,
        slug: str,
        environment: str = "production",
    ) -> models.Project:
        """Create new project."""

        result = await session.execute(
            select(models.Project).where(models.Project.slug == slug)
        )
        if result.scalar_one_or_none():
            raise ValueError(f"Slug '{slug}' already exists")

        project = models.Project(
            account_id=account_id,
            name=name,
            slug=slug,
            environment=environment,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        return project

    async def get_projects_for_account(
        self,
        session: AsyncSession,
        account_id: int,
    ) -> list[models.Project]:
        """Get all projects for account."""

        result = await session.execute(
            select(models.Project).where(models.Project.account_id == account_id)
        )
        return list(result.scalars().all())

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

    # ==================== API Keys ====================

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
                raise ValueError(
                    f"API key with name '{name}' already exists for this project"
                )

        random_part = secrets.token_urlsafe(32)
        full_key = f"ledger_{random_part}"
        key_prefix = full_key[:20]

        key_hash = bcrypt.hashpw(full_key.encode(), bcrypt.gensalt(rounds=10)).decode()

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

        Gateway calls this method to validate API keys.
        """

        cache_key = f"api_key:{hash(api_key)}"
        cached = await self.redis.hgetall(cache_key)

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
                    "current_usage": int(cached.get(b"current_usage", 0)),
                },
            )

        result = await session.execute(
            select(models.ApiKey).where(models.ApiKey.status == "active")
        )
        api_keys = result.scalars().all()

        for key_record in api_keys:
            if bcrypt.checkpw(api_key.encode(), key_record.key_hash.encode()):
                if key_record.expires_at and key_record.expires_at < datetime.now(
                    timezone.utc
                ):
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
                    "current_usage": 0,  # TODO: Get from daily_usage table
                }

                await self.redis.hset(cache_key, mapping=project_info)
                await self.redis.expire(cache_key, config.settings.CACHE_TTL_SECONDS)

                return (True, project.id, project_info)

        return (False, None, {"error": "Invalid API key"})

    async def revoke_api_key(
        self,
        session: AsyncSession,
        key_id: int,
    ) -> None:
        """Revoke API key."""

        result = await session.execute(
            select(models.ApiKey).where(models.ApiKey.id == key_id)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise ValueError("API key not found")

        api_key.status = "revoked"
        await session.commit()

        pattern = "api_key:*"
        async for key in self.redis.scan_iter(match=pattern):
            await self.redis.delete(key)
            await self.redis.delete(key)

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

    # ==================== Refresh Tokens ====================

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
        """
        Validate refresh token and return associated account.

        Args:
            session: Database session
            raw_token: Raw refresh token from client

        Returns:
            Account if token is valid, None otherwise
        """
        result = await session.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.revoked == False,
                models.RefreshToken.expires_at > datetime.now(timezone.utc),
            )
        )
        refresh_tokens = result.scalars().all()

        for token_record in refresh_tokens:
            if jwt_utils.verify_refresh_token(raw_token, token_record.token_hash):
                token_record.last_used_at = datetime.now(timezone.utc)
                await session.commit()

                account = await self.get_account_by_id(session, token_record.account_id)
                return account

        return None

    async def revoke_refresh_token(
        self,
        session: AsyncSession,
        raw_token: str,
    ) -> bool:
        """
        Revoke a specific refresh token.

        Args:
            session: Database session
            raw_token: Raw refresh token to revoke

        Returns:
            True if token was found and revoked, False otherwise
        """
        result = await session.execute(
            select(models.RefreshToken).where(models.RefreshToken.revoked == False)
        )
        refresh_tokens = result.scalars().all()

        for token_record in refresh_tokens:
            if jwt_utils.verify_refresh_token(raw_token, token_record.token_hash):
                token_record.revoked = True
                await session.commit()
                return True

        return False

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
