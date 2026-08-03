import array
import bisect
import dataclasses
import ipaddress
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# IPv6 ranges are keyed on their top 48 bits rather than the full 128-bit
# address -- matching the SDK's own IPv6 truncation granularity, so a
# lookup only ever needs to resolve at the precision it was given. Shifting
# the 128-bit network address right by this many bits yields the 48-bit key.
_V6_KEY_SHIFT = 128 - 48


@dataclasses.dataclass
class _FamilyTable:
    starts: array.array
    ends: array.array
    codes: bytes  # 2 ASCII bytes per entry, same order/index as starts/ends


def _empty_table() -> _FamilyTable:
    return _FamilyTable(array.array("Q"), array.array("Q"), b"")


class IpCountryLookup:
    """Bisect-searchable IP-range -> country-code table, held in memory.

    Loaded from the `ip_country_ranges` table (populated by the analytics
    `rir_refresh` job from the five RIRs' public delegated-extended
    statistics files). Memory layout is two parallel `array("Q")` of range
    bounds plus a flat `bytes` buffer of 2-char country codes, deliberately
    not a `list[tuple[int, int, str]]`: the latter runs ~50-80MB of Python
    object overhead for ~250k ranges, this layout is ~4-6MB for the same
    data -- a 10x difference that's easy to introduce by accident.

    IPv4 and IPv6 get separate tables (different key spaces), each bisected
    independently by address family.
    """

    def __init__(self) -> None:
        self._v4 = _empty_table()
        self._v6 = _empty_table()

    def load(self, ranges: list[tuple[int, int, int, str]]) -> None:
        """`ranges`: (family, range_start, range_end, country_code) rows,
        family 4 or 6, bounds already reduced to that family's key space
        (full 32-bit value for v4, top-48-bits value for v6) -- see
        `_row_to_range_key` in the RIR refresh job for how rows are built.
        """
        v4_rows = sorted((s, e, c) for fam, s, e, c in ranges if fam == 4)
        v6_rows = sorted((s, e, c) for fam, s, e, c in ranges if fam == 6)
        self._v4 = self._build_table(v4_rows)
        self._v6 = self._build_table(v6_rows)
        logger.info("ip_country: loaded %d IPv4 and %d IPv6 ranges", len(v4_rows), len(v6_rows))

    @staticmethod
    def _build_table(rows: list[tuple[int, int, str]]) -> _FamilyTable:
        starts = array.array("Q", (row[0] for row in rows))
        ends = array.array("Q", (row[1] for row in rows))
        codes = b"".join(row[2].encode("ascii") for row in rows)
        return _FamilyTable(starts, ends, codes)

    def lookup(self, ip_prefix: str) -> str | None:
        """`ip_prefix` is a CIDR string such as "203.0.113.0/24" or
        "2001:db8:abcd::/48" (the SDK's `ip_prefix` attribute, already
        truncated). Returns an ISO 3166-1 alpha-2 country code, or None if
        unmatched (includes private/reserved ranges, which are never
        present in the loaded table).
        """
        try:
            network = ipaddress.ip_network(ip_prefix, strict=False)
        except ValueError:
            return None

        if network.version == 4:
            return self._bisect_lookup(self._v4, int(network.network_address))
        return self._bisect_lookup(self._v6, int(network.network_address) >> _V6_KEY_SHIFT)

    @staticmethod
    def _bisect_lookup(table: _FamilyTable, key: int) -> str | None:
        index = bisect.bisect_right(table.starts, key) - 1
        if index < 0 or key > table.ends[index]:
            return None
        return table.codes[index * 2 : index * 2 + 2].decode("ascii")


_lookup = IpCountryLookup()


def get_lookup() -> IpCountryLookup:
    return _lookup


async def reload_from_db(session: AsyncSession) -> None:
    """Reload the in-memory table from `ip_country_ranges`. Called once at
    worker startup and then on the worker's own refresh schedule -- there is
    no cross-process invalidation, so a newly-started worker always gets the
    latest table but a long-running one only picks up changes on its next
    scheduled reload.
    """
    result = await session.execute(
        text("SELECT family, range_start, range_end, country_code FROM ip_country_ranges")
    )
    ranges = [(row.family, row.range_start, row.range_end, row.country_code) for row in result]
    get_lookup().load(ranges)
