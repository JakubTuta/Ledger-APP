import analytics_workers.jobs.rir_refresh as rir_refresh


class TestParseLine:
    def test_valid_ipv4_allocated(self):
        result = rir_refresh._parse_line("apnic|JP|ipv4|1.0.16.0|4096|20110415|allocated")
        assert result == (4, 16781312, 16785407, "JP")

    def test_valid_ipv4_assigned(self):
        result = rir_refresh._parse_line("arin|US|ipv4|8.8.8.0|256|20140101|assigned")
        assert result is not None
        assert result[0] == 4
        assert result[3] == "US"

    def test_valid_ipv6_prefix_field_is_length_not_count(self):
        # For ipv6 rows the 5th field is the CIDR prefix length, not an
        # address count -- this is the well-known quirk of the format. A /32
        # is coarser than the /48 key granularity, so it spans a range of
        # 2**(48-32) = 65536 distinct 48-bit keys, not a single one.
        result = rir_refresh._parse_line("apnic|JP|ipv6|2001:200::|32|20050726|allocated")
        assert result is not None
        family, start, end, code = result
        assert family == 6
        assert code == "JP"
        assert end - start == 65535

    def test_ipv6_finer_than_48_collapses_to_single_key(self):
        result = rir_refresh._parse_line(
            "ripencc|DE|ipv6|2001:db8:abcd:ef00::|56|20200101|allocated"
        )
        assert result is not None
        _family, start, end, _code = result
        assert start == end

    def test_available_status_skipped(self):
        assert rir_refresh._parse_line("apnic|JP|ipv4|1.0.16.0|4096|20110415|available") is None

    def test_reserved_status_skipped(self):
        assert rir_refresh._parse_line("apnic|JP|ipv4|1.0.16.0|4096|20110415|reserved") is None

    def test_asn_type_skipped(self):
        assert rir_refresh._parse_line("apnic|JP|asn|4608|1024|20110415|allocated") is None

    def test_summary_line_skipped(self):
        assert rir_refresh._parse_line("apnic|*|ipv4|*|13107|summary") is None

    def test_version_header_line_skipped(self):
        assert rir_refresh._parse_line("2.3|apnic|20260803|165000|20260803|+1000") is None

    def test_blank_line_skipped(self):
        assert rir_refresh._parse_line("") is None

    def test_comment_line_skipped(self):
        assert rir_refresh._parse_line("# some comment") is None

    def test_wildcard_country_code_skipped(self):
        assert rir_refresh._parse_line("apnic|*|ipv4|1.0.16.0|4096|20110415|allocated") is None

    def test_malformed_ipv4_address_skipped(self):
        assert rir_refresh._parse_line("apnic|JP|ipv4|not-an-ip|4096|20110415|allocated") is None

    def test_non_numeric_count_skipped(self):
        assert rir_refresh._parse_line("apnic|JP|ipv4|1.0.16.0|abc|20110415|allocated") is None

    def test_zero_count_skipped(self):
        assert rir_refresh._parse_line("apnic|JP|ipv4|1.0.16.0|0|20110415|allocated") is None

    def test_truncated_line_skipped(self):
        assert rir_refresh._parse_line("apnic|JP|ipv4") is None

    def test_malformed_ipv6_prefix_skipped(self):
        result = rir_refresh._parse_line("apnic|JP|ipv6|2001:200::|not-a-number|20050726|allocated")
        assert result is None
