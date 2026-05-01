import datetime
import hashlib
import hmac
import secrets
import typing

import jwt

import auth_service.config as config


settings = config.get_settings()


def create_access_token(account_id: int, email: str) -> str:
    """
    Generate JWT access token for authenticated user.

    Args:
        account_id: User's account ID
        email: User's email address

    Returns:
        Signed JWT access token string
    """
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(account_id),
        "email": email,
        "type": "access",
        "exp": expires_at,
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }

    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    return token


def hash_refresh_token(raw_token: str) -> str:
    return hmac.new(
        key=settings.JWT_SECRET.encode(),
        msg=raw_token.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


def create_refresh_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_refresh_token(raw_token)
    return raw_token, token_hash


def verify_access_token(token: str) -> typing.Dict[str, typing.Any]:
    """
    Verify and decode JWT access token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        jwt.ExpiredSignatureError: Token has expired
        jwt.InvalidTokenError: Token is invalid
    """
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])

    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")

    return payload


def verify_refresh_token(raw_token: str, stored_hash: str) -> bool:
    try:
        expected = hash_refresh_token(raw_token)
        return hmac.compare_digest(expected, stored_hash)
    except Exception:
        return False


def get_token_expiration(token_type: str) -> datetime.datetime:
    """
    Calculate expiration datetime for token type.

    Args:
        token_type: Either "access" or "refresh"

    Returns:
        Expiration datetime in UTC
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    if token_type == "access":
        return now + datetime.timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    elif token_type == "refresh":
        return now + datetime.timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    else:
        raise ValueError(f"Invalid token type: {token_type}")
