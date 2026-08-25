import pathlib
import re

import sqlalchemy as sa

_SERVICE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "query_service"

# A bound parameter immediately followed by a Postgres '::' cast. SQLAlchemy's
# own bindparam regex is `(?<![:\w\\]):(\w+)(?!:)` - the trailing `(?!:)` makes
# it back off a character rather than skip the match, so `:start::date` binds a
# parameter named `star` and leaves `:start::date` in the SQL for Postgres to
# reject with a syntax error. Write `CAST(:start AS date)` instead.
_PARAM_CAST = re.compile(r"(?<![:\w\\]):(\w+)::")

_COMMENT_LINE = re.compile(r"^\s*#")


def _sql_offenders() -> list[str]:
    offenders = []
    for path in sorted(_SERVICE_ROOT.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _COMMENT_LINE.match(line):
                continue
            for match in _PARAM_CAST.finditer(line):
                relative = path.relative_to(_SERVICE_ROOT.parent)
                offenders.append(f"{relative}:{lineno}: :{match.group(1)}::")
    return offenders


class TestSqlBindParams:
    def test_sqlalchemy_truncates_a_param_name_before_a_cast(self):
        """Pins the upstream behaviour this guard exists for."""
        assert list(sa.text("SELECT :start::date")._bindparams) == ["star"]
        assert list(sa.text("SELECT CAST(:start AS date)")._bindparams) == ["start"]

    def test_no_bound_parameter_is_followed_by_a_cast(self):
        offenders = _sql_offenders()

        assert not offenders, (
            "bound parameter followed by '::' - SQLAlchemy binds a truncated name "
            "and Postgres rejects the leftover placeholder; use CAST(...) instead:\n"
            + "\n".join(offenders)
        )
