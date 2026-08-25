import ast
import pathlib

_MAIN_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "analytics_workers" / "main.py"
)


def _setup_jobs_ast() -> ast.FunctionDef:
    tree = ast.parse(_MAIN_PATH.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "setup_jobs"
    )


def _parsed_cron_names(setup_jobs: ast.FunctionDef) -> set[str]:
    names = set()
    for node in ast.walk(setup_jobs):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "_parse_cron_expression"
            and isinstance(node.targets[0], ast.Name)
        ):
            names.add(node.targets[0].id)
    return names


def _scheduled_cron_names(setup_jobs: ast.FunctionDef) -> set[str]:
    names = set()
    for node in ast.walk(setup_jobs):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_job"):
            continue
        for keyword in node.keywords:
            if keyword.arg != "trigger":
                continue
            for trigger_kwarg in keyword.value.keywords:
                if trigger_kwarg.arg is None and isinstance(trigger_kwarg.value, ast.Name):
                    names.add(trigger_kwarg.value.id)
    return names


class TestSchedulerWiring:
    """Guards against cron schedules that are parsed but never registered.

    Commit 581318a dropped ten still-live `add_job` calls while removing two
    retired rollups, leaving their `_parse_cron_expression` results as orphaned
    locals. Ruff cannot catch that - F841 (unused variable) is in the ignore
    list - so the parity is asserted structurally instead.
    """

    def test_every_parsed_cron_is_scheduled(self) -> None:
        setup_jobs = _setup_jobs_ast()
        orphaned = _parsed_cron_names(setup_jobs) - _scheduled_cron_names(setup_jobs)

        assert not orphaned, (
            f"cron schedules parsed but never passed to add_job: {sorted(orphaned)}"
        )

    def test_every_scheduled_cron_is_parsed(self) -> None:
        setup_jobs = _setup_jobs_ast()
        undefined = _scheduled_cron_names(setup_jobs) - _parsed_cron_names(setup_jobs)

        assert not undefined, (
            f"add_job triggers referencing unparsed cron names: {sorted(undefined)}"
        )
