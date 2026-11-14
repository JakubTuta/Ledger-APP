"""aiohttp plumbing that keeps outbound requests on public addresses (checks: ledger_common.net_guard)."""

import ipaddress
import socket
import urllib.parse

import aiohttp
import aiohttp.abc
import ledger_common.net_guard as net_guard

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5


class GuardedResolver(aiohttp.abc.AbstractResolver):
    """Resolver that never hands aiohttp a non-public address.

    net_guard.validate_webhook_url() checks a hostname once, but the connection resolves
    it again - a DNS record that answers public first and private second slips
    through that gap. Filtering at connect time closes it.
    """

    def __init__(self) -> None:
        self._resolver = aiohttp.ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[aiohttp.abc.ResolveResult]:
        results = await self._resolver.resolve(host, port, family)
        public = [
            r for r in results if not net_guard.is_blocked_address(ipaddress.ip_address(r["host"]))
        ]
        if not public:
            raise OSError(f"{host} resolves only to private/reserved addresses")
        return public

    async def close(self) -> None:
        await self._resolver.close()


def guarded_session(**kwargs) -> aiohttp.ClientSession:
    """A ClientSession whose connections can only reach public addresses."""
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(resolver=GuardedResolver()), **kwargs
    )


async def get_following_safe_redirects(
    http: aiohttp.ClientSession,
    url: str,
    allow_http: bool,
    timeout: aiohttp.ClientTimeout,
) -> int:
    """GET `url`, following redirects only to URLs that pass net_guard.validate_webhook_url.

    aiohttp's own redirect handling would follow a Location pointing at an
    internal address; a literal IP in that Location never reaches the resolver.
    Returns the final status code.
    """
    for _ in range(_MAX_REDIRECTS + 1):
        await net_guard.validate_webhook_url(url, allow_http=allow_http)
        async with http.get(url, timeout=timeout, allow_redirects=False) as response:
            location = response.headers.get("Location")
            if response.status not in _REDIRECT_STATUSES or not location:
                return response.status
        url = urllib.parse.urljoin(url, location)
    raise net_guard.UnsafeWebhookURLError(f"More than {_MAX_REDIRECTS} redirects")
