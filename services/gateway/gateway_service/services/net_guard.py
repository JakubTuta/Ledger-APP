"""
SSRF guard for connector test-fire delivery (webhook / slack / discord).

Vendored from analytics_workers.jobs.net_guard (Phase 4.1): the gateway
service and the analytics worker are separate deployable services with no
shared package, so this is a deliberate, small, dependency-free copy rather
than a cross-service import. Keep the two in sync if the blocklist changes.
"""

import asyncio
import ipaddress
import socket
import urllib.parse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class UnsafeWebhookURLError(Exception):
    pass


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
        if any(ip in network for network in _BLOCKED_NETWORKS):
            raise UnsafeWebhookURLError(
                f"Webhook host {hostname} resolves to a private/reserved address ({ip})"
            )
