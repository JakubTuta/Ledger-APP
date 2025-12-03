import datetime
import secrets
import typing

import bcrypt
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


def create_refresh_token() -> tuple[str, str]:
    """
    Generate cryptographically secure refresh token.

    Returns:
        Tuple of (raw_token, bcrypt_hash)
        - raw_token: To send to client
        - bcrypt_hash: To store in database
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt(settings.BCRYPT_ROUNDS))

    return raw_token, token_hash.decode()


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
    """
    Verify refresh token against stored bcrypt hash.

    Args:
        raw_token: Raw token from client
        stored_hash: Bcrypt hash from database

    Returns:
        True if token matches hash, False otherwise
    """
    try:
        return bcrypt.checkpw(raw_token.encode(), stored_hash.encode())
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
