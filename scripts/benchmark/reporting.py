import json

import models as result_models


def print_report(report: result_models.RunReport) -> None:
    print("\n" + "=" * 70)
    print("LEDGER INGESTION BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Mode:         {report.mode}")
    print(f"Started:      {report.started_at_utc}")
    print(f"Finished:     {report.finished_at_utc}")
    print(f"Wall time:    {report.total_wall_seconds:.1f}s")
    if report.provisioned_email:
        print(f"Account:      {report.provisioned_email}")
    if report.provisioned_project_id:
        print(f"Project ID:   {report.provisioned_project_id}")
    if report.limits_bumped:
        print("Limits:       BYPASSED (rate+quota raised directly in Auth DB)")

    if report.mode == "ramp" and report.stages:
        print()
        print(
            f"{'c':>4}  {'ingress':>12}  {'drain':>12}  {'max_depth':>10}  {'errors':>7}  verdict"
        )
        print("-" * 70)
        for stage in report.stages:
            verdict_str = "OK" if stage.healthy else f"SATURATED ({stage.saturation_cause})"
            print(
                f"{stage.concurrency:>4}  "
                f"{stage.ingress_rate:>10.0f}/s  "
                f"{stage.drain_rate:>10.0f}/s  "
                f"{stage.drain.max_depth:>10}  "
                f"{stage.phase.errors.total:>7}  "
                f"{verdict_str}"
            )

        if report.best_stage is not None:
            best = report.best_stage
            print()
            print(f"BEST HEALTHY STAGE: concurrency={best.concurrency}")
            print(f"  Ingress rate:  {best.ingress_rate:.0f} logs/s (Gateway accept rate)")
            print(f"  Drain rate:    {best.drain_rate:.0f} logs/s (sustainable pipeline rate)")
            if best.db_delta is not None:
                print(f"  DB verify:     {best.db_delta}/{best.phase.accepted} rows matched")
            print(f"  Max queue:     {best.drain.max_depth}")
            print(f"  Latency p50:   {best.phase.latency.p50_ms:.1f}ms")
            print(f"  Latency p99:   {best.phase.latency.p99_ms:.1f}ms")
        else:
            print()
            print("No healthy stage found — pipeline saturated at lowest concurrency tested.")

    elif report.mode == "single" and report.single_phase is not None:
        phase = report.single_phase
        print()
        print(f"Concurrency:  {phase.concurrency}")
        print(f"Duration:     {phase.duration_s:.1f}s")
        print(f"Accepted:     {phase.accepted}")
        print(f"Rejected:     {phase.rejected}")
        print(
            f"Errors:       {phase.errors.total} (429={phase.errors.rate_429} 503={phase.errors.queue_503} 500={phase.errors.server_500} transport={phase.errors.transport})"
        )
        print(f"Ingress rate: {phase.ingress_rate:.0f} logs/s")
        print(f"Latency p50:  {phase.latency.p50_ms:.1f}ms")
        print(f"Latency p99:  {phase.latency.p99_ms:.1f}ms")
        if report.single_drain is not None:
            drain = report.single_drain
            print(f"Drained:      {drain.drained} in {drain.drain_seconds:.1f}s")
            print(f"Max depth:    {drain.max_depth}")
        if report.single_db_delta is not None:
            print(f"DB rows:      {report.single_db_delta}/{phase.accepted}")
        if report.headline_logs_per_second is not None:
            print(f"Drain rate:   {report.headline_logs_per_second:.0f} logs/s")

    print()
    print(f"VERDICT: {report.verdict}")
    if report.headline_logs_per_second is not None and report.mode == "ramp":
        print(
            f"HEADLINE: {report.headline_logs_per_second:.0f} logs/s sustainable "
            f"at concurrency={report.headline_concurrency}"
        )
    print("=" * 70 + "\n")


def write_json(report: result_models.RunReport, path: str) -> None:
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    data = report.model_dump()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"JSON results written to: {path}")
