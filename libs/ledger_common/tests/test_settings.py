import pytest

import ledger_common.settings as settings


class _Settings(
    settings.RedisSettings,
    settings.AuthDatabaseSettings,
    settings.LogsDatabaseSettings,
    settings.GrpcServerSettings,
    settings.JwtSettings,
    settings.ServiceSettings,
):
    pass


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch):
    for name in ("ENV", "JWT_SECRET", "REDIS_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


def _build(**overrides) -> _Settings:
    return _Settings(_env_file=None, **overrides)


def test_urls_are_built_from_the_individual_settings():
    built = _build(
        REDIS_HOST="cache", REDIS_PASSWORD="pw", AUTH_DB_HOST="authdb", LOGS_DB_PORT=5999
    )

    assert built.REDIS_URL == "redis://:pw@cache:6379/0"
    assert built.AUTH_DATABASE_URL == "postgresql+asyncpg://postgres:postgres@authdb:5432/auth_db"
    assert (
        built.LOGS_DATABASE_URL == "postgresql+asyncpg://postgres:postgres@localhost:5999/logs_db"
    )


def test_redis_url_without_a_password_has_no_credentials():
    assert _build().REDIS_URL == "redis://localhost:6379/0"


def test_grpc_server_options_carry_the_keepalive_constants():
    options = dict(_build().grpc_server_options)

    assert (
        options["grpc.keepalive_time_ms"] == settings.GrpcKeepaliveSettings.GRPC_KEEPALIVE_TIME_MS
    )
    assert options["grpc.max_receive_message_length"] == 100 * 1024 * 1024
    assert "grpc.http2.min_recv_ping_interval_without_data_ms" in options


def test_production_refuses_the_placeholder_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _build(ENV="production")


def test_production_accepts_a_real_jwt_secret():
    assert _build(ENV="production", JWT_SECRET="x" * 40).is_production


def test_development_allows_the_placeholder_jwt_secret():
    assert _build().is_development


def test_jwt_secret_must_be_long_enough():
    with pytest.raises(ValueError):
        _build(JWT_SECRET="short")
