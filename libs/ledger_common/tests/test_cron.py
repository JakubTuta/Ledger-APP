import pytest

import ledger_common.cron as cron


def test_five_fields_map_to_cron_trigger_kwargs():
    assert cron.parse_cron_expression("*/10 3 1 * 0") == {
        "minute": "*/10",
        "hour": "3",
        "day": "1",
        "month": "*",
        "day_of_week": "0",
    }


@pytest.mark.parametrize("expression", ["", "* * * *", "* * * * * *"])
def test_wrong_field_count_is_rejected(expression):
    with pytest.raises(ValueError, match="Expected 5 parts"):
        cron.parse_cron_expression(expression)
