import pydantic
import pytest
from gateway_service import config
from gateway_service.services import grpc_pool


class TestGrpcPoolSizeSetting:
    def test_defaults_to_two(self, monkeypatch):
        monkeypatch.delenv("GRPC_POOL_SIZE", raising=False)

        assert config.Settings(_env_file=None).GRPC_POOL_SIZE == 2

    def test_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("GRPC_POOL_SIZE", "5")

        assert config.Settings(_env_file=None).GRPC_POOL_SIZE == 5

    @pytest.mark.parametrize("value", ["0", "33"])
    def test_rejects_values_outside_one_to_thirty_two(self, monkeypatch, value):
        monkeypatch.setenv("GRPC_POOL_SIZE", value)

        with pytest.raises(pydantic.ValidationError):
            config.Settings(_env_file=None)


class _RecordingPool:
    created: list = []

    def __init__(self, service_name: str, address: str, pool_size: int):
        self.pool_size = pool_size
        _RecordingPool.created.append(self)

    async def initialize(self) -> None:
        pass


@pytest.mark.asyncio
class TestAddServicePoolSize:
    @pytest.fixture(autouse=True)
    def recording_pool(self, monkeypatch):
        _RecordingPool.created = []
        monkeypatch.setattr(grpc_pool, "GRPCChannelPool", _RecordingPool)

    async def test_uses_the_configured_pool_size(self, monkeypatch):
        monkeypatch.setattr(config.settings, "GRPC_POOL_SIZE", 7)

        await grpc_pool.GRPCPoolManager().add_service("query", "localhost:50053")

        assert _RecordingPool.created[0].pool_size == 7

    async def test_explicit_size_overrides_the_setting(self, monkeypatch):
        monkeypatch.setattr(config.settings, "GRPC_POOL_SIZE", 7)

        await grpc_pool.GRPCPoolManager().add_service("query", "localhost:50053", pool_size=3)

        assert _RecordingPool.created[0].pool_size == 3
