import ipaddress
import time

import aiohttp
import sqlalchemy as sa

import analytics_workers.database as database
import analytics_workers.utils.logging as logging

logger = logging.get_logger("jobs.rir_refresh")

# The five Regional Internet Registries each publish a daily snapshot of
# their address-space delegations in the "delegated-extended" format - free,
# no account or license key, no rate limiting for this file specifically.
_RIR_URLS = (
    "https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest",
    "https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest",
    "https://ftp.apnic.net/pub/stats/apnic/delegated-apnic-extended-latest",
    "https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest",
    "https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest",
)

_ALLOCATED_STATUSES = frozenset({"allocated", "assigned"})
_FETCH_TIMEOUT_SECONDS = 60
_INSERT_BATCH_SIZE = 5000

# IPv6 ranges are keyed on their top 48 bits, matching both the SDK's IPv6
# truncation granularity and ip_country.py's lookup table layout - see that
# module's docstring for why.
_V6_KEY_SHIFT = 128 - 48


def _parse_line(line: str) -> tuple[int, int, int, str] | None:
    """Parse one "registry|cc|type|start|value|date|status[|opaque-id]" line.

    Returns None for anything that isn't an allocated/assigned ipv4/ipv6
    record - this silently and correctly skips the leading version line and
    the per-registry "|*|ipv4|*|N|summary" summary lines, since neither
    matches an ipv4/ipv6 type with an allocated/assigned status.
    """
    parts = line.strip().split("|")
    if len(parts) < 7:
        return None

    _registry, country_code, record_type, start, value, _date, status = parts[:7]

    if status not in _ALLOCATED_STATUSES:
        return None
    if record_type not in ("ipv4", "ipv6"):
        return None
    if len(country_code) != 2 or not country_code.isalpha():
        return None

    try:
        if record_type == "ipv4":
            range_start = int(ipaddress.IPv4Address(start))
            count = int(value)
            if count <= 0:
                return None
            return (4, range_start, range_start + count - 1, country_code.upper())

        network = ipaddress.ip_network(f"{start}/{int(value)}", strict=False)
        range_start = int(network.network_address) >> _V6_KEY_SHIFT
        range_end = int(network.broadcast_address) >> _V6_KEY_SHIFT
        return (6, range_start, range_end, country_code.upper())

    except (ValueError, ipaddress.AddressValueError):
        return None


async def _fetch_ranges(http: aiohttp.ClientSession, url: str) -> list[tuple[int, int, int, str]]:
    async with http.get(url) as response:
        response.raise_for_status()
        text = await response.text()

    ranges = []
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed is not None:
            ranges.append(parsed)
    return ranges


async def _replace_ranges(
    session: sa.ext.asyncio.AsyncSession, ranges: list[tuple[int, int, int, str]]
) -> None:
    await session.execute(sa.text("TRUNCATE TABLE ip_country_ranges"))
    for i in range(0, len(ranges), _INSERT_BATCH_SIZE):
        batch = ranges[i : i + _INSERT_BATCH_SIZE]
        await session.execute(
            sa.text(
                "INSERT INTO ip_country_ranges (family, range_start, range_end, country_code) "
                "VALUES (:family, :range_start, :range_end, :country_code)"
            ),
            [
                {"family": family, "range_start": start, "range_end": end, "country_code": code}
                for family, start, end, code in batch
            ],
        )
    await session.commit()


async def refresh_ip_country_ranges() -> None:
    """Refresh `ip_country_ranges` from the five RIRs' public delegated-
    extended files. The ingestion worker reloads its in-memory lookup table
    from this table on its own schedule (see ip_country.py) - this job only
    owns keeping the database copy current.

    A source that fails to fetch or parse is skipped with a warning rather
    than aborting the whole run, so one RIR being briefly unreachable
    doesn't block refreshing the other four. If every source fails, the
    existing table is left untouched rather than truncated to empty.
    """
    start_time = time.perf_counter()
    ranges: list[tuple[int, int, int, str]] = []

    timeout = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        for url in _RIR_URLS:
            try:
                ranges.extend(await _fetch_ranges(http, url))
            except Exception as e:
                logger.warning(f"rir_refresh: failed to fetch/parse {url}: {e}")

    if not ranges:
        logger.error("rir_refresh: no ranges parsed from any RIR source, leaving table untouched")
        return

    async with database.get_logs_session() as session:
        await _replace_ranges(session, ranges)

    elapsed = time.perf_counter() - start_time
    logger.info(f"rir_refresh: loaded {len(ranges)} ranges in {elapsed:.2f}s")
