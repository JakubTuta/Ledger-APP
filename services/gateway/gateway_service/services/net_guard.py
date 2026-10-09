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

import httpx


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


async def post_to_public_host(http: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """POST `url` over a connection pinned to the address that was validated.

    Letting httpx resolve the name again at connect time leaves a window in
    which a DNS record can answer public for the check and private for the
    connection. The original hostname still drives the Host header and the TLS
    SNI/certificate check, so pinning changes only which IP is dialled.
    """
    address = await validate_webhook_url(url)
    target = httpx.URL(url)
    headers = {**kwargs.pop("headers", {}), "Host": target.netloc.decode("ascii")}
    return await http.post(
        target.copy_with(host=str(address)),
        headers=headers,
        extensions={"sni_hostname": target.host},
        **kwargs,
    )
