"""SSRF guard for outbound requests to user-supplied URLs (webhook / Slack / Discord / monitors).

The address checks live here; the HTTP-client-specific parts that keep a connection on the vetted
address (aiohttp in analytics, httpx in the gateway) are each service's `guarded_http` module.
Stdlib only, so every service can import it.
"""

import asyncio
import ipaddress
import socket
import urllib.parse


class UnsafeWebhookURLError(Exception):
    pass


def is_blocked_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for anything that is not a globally routable unicast address.

    `is_global` covers private, loopback, link-local, shared (100.64/10),
    reserved and documentation ranges; IPv6 forms that embed an IPv4 address
    (::ffff:a.b.c.d, 6to4, Teredo) are judged by the embedded address, so
    `[::ffff:127.0.0.1]` cannot stand in for 127.0.0.1.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None and is_blocked_address(embedded):
            return True
    return not ip.is_global or ip.is_multicast


async def validate_webhook_url(
    url: str, allow_http: bool = False
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Reject non-https and non-public targets; return the vetted address."""
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

    addresses = [ipaddress.ip_address(sockaddr[0]) for *_, sockaddr in addr_infos]
    for ip in addresses:
        if is_blocked_address(ip):
            raise UnsafeWebhookURLError(
                f"Webhook host {hostname} resolves to a private/reserved address ({ip})"
            )
    return addresses[0]
