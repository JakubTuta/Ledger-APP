import asyncio
import ipaddress
import socket
from unittest.mock import patch

import pytest

import ledger_common.net_guard as net_guard


def _resolves_to(*addresses: str):
    async def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addresses]

    return getaddrinfo


class TestBlockedAddresses:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "::ffff:169.254.169.254",  # IPv4-mapped cloud metadata
            "100.64.0.1",  # shared address space (CGNAT)
            "172.20.0.5",  # docker bridge
            "0.0.0.0",
            "224.0.0.1",
        ],
    )
    def test_non_public_addresses_are_blocked(self, address):
        assert net_guard.is_blocked_address(ipaddress.ip_address(address))

    @pytest.mark.parametrize("address", ["93.184.215.14", "2606:4700:4700::1111"])
    def test_public_addresses_are_allowed(self, address):
        assert not net_guard.is_blocked_address(ipaddress.ip_address(address))


@pytest.mark.asyncio
class TestValidateWebhookUrl:
    async def test_blocks_loopback(self):
        with pytest.raises(net_guard.UnsafeWebhookURLError):
            await net_guard.validate_webhook_url("https://127.0.0.1/hook")

    async def test_blocks_link_local_metadata_address(self):
        with pytest.raises(net_guard.UnsafeWebhookURLError):
            await net_guard.validate_webhook_url("https://169.254.169.254/hook")

    async def test_rejects_plain_http_by_default(self):
        with pytest.raises(net_guard.UnsafeWebhookURLError):
            await net_guard.validate_webhook_url("http://example.com/hook")

    async def test_allows_plain_http_when_explicitly_enabled(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", _resolves_to("93.184.215.14")):
            address = await net_guard.validate_webhook_url(
                "http://example.com/hook", allow_http=True
            )

        assert address == ipaddress.ip_address("93.184.215.14")

    async def test_host_with_any_private_address_is_refused(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", _resolves_to("93.184.215.14", "10.0.0.5")):
            with pytest.raises(net_guard.UnsafeWebhookURLError):
                await net_guard.validate_webhook_url("https://hooks.example.com/x")

    async def test_unresolvable_host_is_refused(self):
        async def fail(host, port, *args, **kwargs):
            raise socket.gaierror("no such host")

        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", fail):
            with pytest.raises(net_guard.UnsafeWebhookURLError):
                await net_guard.validate_webhook_url("https://nope.invalid/x")
