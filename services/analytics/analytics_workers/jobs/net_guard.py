import asyncio
import ipaddress
import socket
import urllib.parse

import aiohttp
import aiohttp.abc

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5


class UnsafeWebhookURLError(Exception):
    pass


def is_blocked_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for anything that is not a globally routable unicast address.

    `is_global` covers private, loopback, link-local, shared (100.64/10),
    reserved and documentation ranges; IPv6 forms that embed an IPv4 address
    (::ffff:a.b.c.d, 6to4, Teredo) are judged by the embedded address.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None and is_blocked_address(embedded):
            return True
    return not ip.is_global or ip.is_multicast


async def validate_webhook_url(url: str, allow_http: bool = False) -> None:
    parsed = urllib.parse.urlparse(url)

    allowed_schemes = {"https"} | ({"http"} if allow_http else set())
    if parsed.scheme not in allowed_schemes:
        raise UnsafeWebhookURLError(f"Webhook URL must use https: {url}")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeWebhookURLError(f"Webhook URL missing host: {url}")

    loop = asyncio.get_running_loop()
    try:
        addr_infos = await loop.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise UnsafeWebhookURLError(f"Cannot resolve webhook host {hostname}: {e}")

    if not addr_infos:
        raise UnsafeWebhookURLError(f"Webhook host {hostname} did not resolve to any address")

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if is_blocked_address(ip):
            raise UnsafeWebhookURLError(
                f"Webhook host {hostname} resolves to a private/reserved address ({ip})"
            )


class GuardedResolver(aiohttp.abc.AbstractResolver):
    """Resolver that never hands aiohttp a non-public address.

    validate_webhook_url() checks a hostname once, but the connection resolves
    it again - a DNS record that answers public first and private second slips
    through that gap. Filtering at connect time closes it.
    """

    def __init__(self) -> None:
        self._resolver = aiohttp.ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[aiohttp.abc.ResolveResult]:
        results = await self._resolver.resolve(host, port, family)
        public = [r for r in results if not is_blocked_address(ipaddress.ip_address(r["host"]))]
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
    """GET `url`, following redirects only to URLs that pass validate_webhook_url.

    aiohttp's own redirect handling would follow a Location pointing at an
    internal address; a literal IP in that Location never reaches the resolver.
    Returns the final status code.
    """
    for _ in range(_MAX_REDIRECTS + 1):
        await validate_webhook_url(url, allow_http=allow_http)
        async with http.get(url, timeout=timeout, allow_redirects=False) as response:
            location = response.headers.get("Location")
            if response.status not in _REDIRECT_STATUSES or not location:
                return response.status
        url = urllib.parse.urljoin(url, location)
    raise UnsafeWebhookURLError(f"More than {_MAX_REDIRECTS} redirects")
