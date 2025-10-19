import pytest


@pytest.fixture
def mock_settings():
    from analytics_workers.config import Settings

    return Settings(
        ENV="test",
        DEBUG=True,
        ERROR_RATE_TTL=600,
        LOG_VOLUME_TTL=600,
        TOP_ERRORS_TTL=900,
        USAGE_STATS_TTL=3600,
    )
