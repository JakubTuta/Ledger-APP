"""httpx plumbing that dials only a vetted public address (checks: ledger_common.net_guard)."""

import httpx
import ledger_common.net_guard as net_guard


async def post_to_public_host(http: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """POST `url` over a connection pinned to the address that was validated.

    Letting httpx resolve the name again at connect time leaves a window in
    which a DNS record can answer public for the check and private for the
    connection. The original hostname still drives the Host header and the TLS
    SNI/certificate check, so pinning changes only which IP is dialled.
    """
    address = await net_guard.validate_webhook_url(url)
    target = httpx.URL(url)
    headers = {**kwargs.pop("headers", {}), "Host": target.netloc.decode("ascii")}
    return await http.post(
        target.copy_with(host=str(address)),
        headers=headers,
        extensions={"sni_hostname": target.host},
        **kwargs,
    )
