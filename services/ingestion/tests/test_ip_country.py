import ingestion_service.services.ip_country as ip_country


def _v4_range(start: str, end: str, code: str) -> tuple[int, int, int, str]:
    import ipaddress

    return (4, int(ipaddress.ip_address(start)), int(ipaddress.ip_address(end)), code)


def _v6_range(start: str, end: str, code: str) -> tuple[int, int, int, str]:
    import ipaddress

    shift = ip_country._V6_KEY_SHIFT
    return (
        6,
        int(ipaddress.ip_address(start)) >> shift,
        int(ipaddress.ip_address(end)) >> shift,
        code,
    )


class TestIpCountryLookup:
    def test_v4_match(self):
        lookup = ip_country.IpCountryLookup()
        lookup.load([_v4_range("203.0.113.0", "203.0.113.255", "DE")])
        assert lookup.lookup("203.0.113.0/24") == "DE"

    def test_v4_no_match_returns_none(self):
        lookup = ip_country.IpCountryLookup()
        lookup.load([_v4_range("203.0.113.0", "203.0.113.255", "DE")])
        assert lookup.lookup("198.51.100.0/24") is None

    def test_v6_match(self):
        lookup = ip_country.IpCountryLookup()
        lookup.load([_v6_range("2001:db8::", "2001:db8:ffff:ffff:ffff:ffff:ffff:ffff", "FR")])
        assert lookup.lookup("2001:db8:abcd::/48") == "FR"

    def test_multiple_ranges_bisect_correctly(self):
        lookup = ip_country.IpCountryLookup()
        lookup.load(
            [
                _v4_range("1.0.0.0", "1.0.0.255", "AU"),
                _v4_range("8.8.8.0", "8.8.8.255", "US"),
                _v4_range("203.0.113.0", "203.0.113.255", "DE"),
            ]
        )
        assert lookup.lookup("8.8.8.0/24") == "US"
        assert lookup.lookup("1.0.0.0/24") == "AU"
        assert lookup.lookup("203.0.113.0/24") == "DE"

    def test_empty_table_returns_none(self):
        lookup = ip_country.IpCountryLookup()
        lookup.load([])
        assert lookup.lookup("8.8.8.0/24") is None

    def test_unparseable_prefix_returns_none(self):
        lookup = ip_country.IpCountryLookup()
        lookup.load([_v4_range("203.0.113.0", "203.0.113.255", "DE")])
        assert lookup.lookup("not-a-prefix") is None

    def test_private_range_not_in_table_returns_none(self):
        lookup = ip_country.IpCountryLookup()
        lookup.load([_v4_range("203.0.113.0", "203.0.113.255", "DE")])
        assert lookup.lookup("10.1.2.0/24") is None

    def test_get_lookup_returns_singleton(self):
        assert ip_country.get_lookup() is ip_country.get_lookup()
