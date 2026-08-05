"""
Regenerates the benchmark-derived sections of README.md and CLAUDE.md from the
latest steady-state result JSON. Never hand-edit the text between the
BENCH:README / BENCH:PERF markers - run this instead.

    python -m scripts.benchmark.publish              # write from the latest result
    python -m scripts.benchmark.publish --check       # exit non-zero if regenerating would change a file
    python -m scripts.benchmark.publish --file PATH   # publish a specific result JSON
"""

import argparse
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LEDGER_APP_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_DEFAULT_RESULT_DIR = os.path.join(_LEDGER_APP_ROOT, "benchmark_result")
_README_PATH = os.path.join(_LEDGER_APP_ROOT, "README.md")
_CLAUDE_MD_PATH = os.path.join(_LEDGER_APP_ROOT, "CLAUDE.md")

_README_START = "<!-- BENCH:README:START -->"
_README_END = "<!-- BENCH:README:END -->"
_PERF_START = "<!-- BENCH:PERF:START -->"
_PERF_END = "<!-- BENCH:PERF:END -->"


def latest_result(result_dir: str | None = None) -> dict:
    """Newest result by embedded finished_at_utc - not file mtime, which git
    checkouts/copies don't preserve reliably."""
    result_dir = result_dir or _DEFAULT_RESULT_DIR
    paths = glob.glob(os.path.join(result_dir, "*.json"))
    if not paths:
        raise SystemExit(f"publish: no result JSON files found under {result_dir}")

    best_path = None
    best_ts = ""
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        ts = data.get("finished_at_utc", "")
        if ts > best_ts:
            best_ts = ts
            best_path = path

    if best_path is None:
        raise SystemExit(f"publish: no parseable result JSON under {result_dir}")
    return load_report(best_path)


def load_report(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _validate_publishable(report: dict) -> None:
    if report.get("mode") != "steady" or report.get("max_sustainable_offered_rate") is None:
        raise SystemExit(
            "publish: refusing - this result isn't a steady-state run with a "
            "max_sustainable_offered_rate (run --mode steady --find-max first). "
            "ramp-mode drain_rate is a haircut on ingress, not a measurement, and "
            "must never be published as the headline throughput number."
        )


def _headline_run(report: dict) -> dict | None:
    target = report["max_sustainable_offered_rate"]
    candidates = [
        r
        for r in report.get("steady_runs", [])
        if r.get("healthy") and abs(r["offered_rate"] - target) < 1e-6
    ]
    if candidates:
        return candidates[0]
    healthy = [r for r in report.get("steady_runs", []) if r.get("healthy")]
    if not healthy:
        return None
    return max(healthy, key=lambda r: r["offered_rate"])


def render_readme_line(report: dict) -> str:
    _validate_publishable(report)
    run = _headline_run(report)
    rate = report["max_sustainable_offered_rate"]
    wire = report.get("config_summary", {}).get("wire", "protobuf")
    p99 = run["latency"]["p99_ms"] if run else 0.0
    return (
        f"{_README_START}measured {rate:,.0f} logs/s sustained on a single node at full power "
        f"(unconstrained CPU, p99 ingest latency < {p99:.0f}ms, flat queue depth, {wire} wire). "
        f"Container resource limits in `docker-compose.prod.yaml` are deliberately conservative "
        f"and cap this lower. Raw runs: [`benchmark_result/`](benchmark_result/).{_README_END}"
    )


def render_claude_table(report: dict) -> str:
    _validate_publishable(report)
    run = _headline_run(report)
    rate = report["max_sustainable_offered_rate"]
    cfg_summary = report.get("config_summary", {})
    wire = cfg_summary.get("wire", "protobuf")
    batch_size = cfg_summary.get("batch_size", "?")
    slo_p50 = cfg_summary.get("slo_p50_ms", "?")
    slo_p99 = cfg_summary.get("slo_p99_ms", "?")
    p50 = run["latency"]["p50_ms"] if run else 0.0
    p99 = run["latency"]["p99_ms"] if run else 0.0
    missing_rows = run.get("missing_rows") if run else None

    lines = [
        _PERF_START,
        f"Run: {report.get('finished_at_utc', '?')} | wire={wire} | batch_size={batch_size} | "
        f"signals=logs (spans/metrics mixed-signal load not implemented)",
        "",
        "| Metric                       | Result                | Notes |",
        "| ----------------------------- | ---------------------- | ----- |",
        f"| Max sustainable offered rate | {rate:,.0f} logs/s | steady-state open-loop, `--find-max` |",
        f"| Latency at max rate (p50/p99) | {p50:.0f}ms / {p99:.0f}ms | SLO p50<={slo_p50}ms p99<={slo_p99}ms |",
        f"| Missing rows | {missing_rows} | exact accounting via client-generated `log_id`, must read 0 |",
        "| Profile | bench-unlimited | no CPU/memory caps - see `docker-compose.bench-unlimited.yaml`; "
        "rerun on `bench-prod-parity` to size the shipped deployment |",
        _PERF_END,
    ]
    return "\n".join(lines)


def apply(path: str, start_marker: str, end_marker: str, inner_text: str) -> bool:
    """
    Replaces the text between start_marker and end_marker (both kept) with
    inner_text's own start/end markers. Returns True if the file changed.
    Raises if the markers aren't found - silently appending would hide a typo'd
    marker forever instead of failing the publish.
    """
    with open(path, encoding="utf-8") as f:
        content = f.read()

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise SystemExit(
            f"publish: markers {start_marker!r}/{end_marker!r} not found (or out of order) in {path}"
        )

    new_content = content[:start_idx] + inner_text + content[end_idx + len(end_marker) :]
    if new_content == content:
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def check(path: str, start_marker: str, end_marker: str, inner_text: str) -> bool:
    """Returns True if applying would change the file, without writing it."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise SystemExit(
            f"publish: markers {start_marker!r}/{end_marker!r} not found (or out of order) in {path}"
        )
    new_content = content[:start_idx] + inner_text + content[end_idx + len(end_marker) :]
    return new_content != content


def publish_latest(
    json_path: str | None = None, dry_run: bool = False, result_dir: str | None = None
) -> bool:
    report = load_report(json_path) if json_path else latest_result(result_dir)
    readme_line = render_readme_line(report)
    claude_table = render_claude_table(report)

    if dry_run:
        readme_changed = check(_README_PATH, _README_START, _README_END, readme_line)
        claude_changed = check(_CLAUDE_MD_PATH, _PERF_START, _PERF_END, claude_table)
        changed = readme_changed or claude_changed
        if changed:
            print("publish --check: README.md and/or CLAUDE.md are out of date", flush=True)
        else:
            print("publish --check: up to date", flush=True)
        return changed

    readme_changed = apply(_README_PATH, _README_START, _README_END, readme_line)
    claude_changed = apply(_CLAUDE_MD_PATH, _PERF_START, _PERF_END, claude_table)
    print(
        f"publish: README.md {'updated' if readme_changed else 'unchanged'}, "
        f"CLAUDE.md {'updated' if claude_changed else 'unchanged'}",
        flush=True,
    )
    return readme_changed or claude_changed


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit non-zero if files would change")
    parser.add_argument("--file", default=None, help="Publish a specific result JSON")
    parser.add_argument("--dir", default=_DEFAULT_RESULT_DIR, help="Directory to scan for results")
    args = parser.parse_args()

    changed = publish_latest(json_path=args.file, dry_run=args.check, result_dir=args.dir)
    if args.check and changed:
        sys.exit(1)


if __name__ == "__main__":
    _cli()
