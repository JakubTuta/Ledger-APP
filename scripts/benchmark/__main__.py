import argparse
import asyncio
import datetime
import sys
import time

import httpx

import config as benchmark_config
import drain as drain_module
import load_engine
import models
import payloads as payload_module
import provisioning
import ramp as ramp_module
import reporting


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ledger ingestion throughput benchmark. "
            "Zero args = best mode: auto-ramp, gzip, fresh key with limit bypass, DB verify, auto JSON output."
        )
    )
    parser.add_argument("--base-url", default=None, help="Gateway base URL (default: http://localhost:8020)")
    parser.add_argument("--concurrency", type=int, default=None, help="Worker count for single-run mode")
    parser.add_argument("--batch-size", type=int, default=None, help="Logs per batch (1-1000, default 1000)")
    parser.add_argument("--no-gzip", action="store_true", help="Disable gzip compression")
    parser.add_argument("--duration", type=int, default=None, metavar="SECONDS", help="Single-run duration")
    parser.add_argument("--total-logs", type=int, default=None, help="Single-run log count")
    parser.add_argument("--no-ramp", action="store_true", help="Skip auto-ramp, use --duration or --total-logs")
    parser.add_argument("--ramp-max", type=int, default=None, help="Max concurrency to test (default 64)")
    parser.add_argument("--ramp-stage-seconds", type=int, default=None, help="Seconds per ramp stage (default 30)")
    parser.add_argument("--api-key", default=None, help="Reuse existing API key (skips provisioning)")
    parser.add_argument("--project-id", type=int, default=None, help="Project ID (with --api-key)")
    parser.add_argument("--respect-limits", action="store_true", help="Do not bypass rate/quota limits")
    parser.add_argument("--no-db-verify", action="store_true", help="Skip Logs DB row count verification")
    parser.add_argument("--json-output", default=None, metavar="FILE", help="Write results JSON to file")
    parser.add_argument("--verbose", action="store_true", help="Extra output")
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> benchmark_config.BenchmarkConfig:
    kwargs: dict = {}
    if args.base_url:
        kwargs["base_url"] = args.base_url
    if args.concurrency is not None:
        kwargs["concurrency"] = args.concurrency
    if args.batch_size is not None:
        kwargs["batch_size"] = args.batch_size
    if args.no_gzip:
        kwargs["gzip"] = False
    if args.duration is not None:
        kwargs["duration_seconds"] = args.duration
        kwargs["ramp"] = False
    if args.total_logs is not None:
        kwargs["total_logs"] = args.total_logs
        kwargs["ramp"] = False
    if args.no_ramp:
        kwargs["ramp"] = False
    if args.ramp_max is not None:
        kwargs["ramp_max"] = args.ramp_max
    if args.ramp_stage_seconds is not None:
        kwargs["ramp_stage_seconds"] = args.ramp_stage_seconds
    if args.api_key:
        kwargs["api_key"] = args.api_key
    if args.project_id is not None:
        kwargs["project_id"] = args.project_id
    if args.respect_limits:
        kwargs["respect_limits"] = True
    if args.no_db_verify:
        kwargs["no_db_verify"] = True
    if args.json_output:
        kwargs["json_output"] = args.json_output
    if args.verbose:
        kwargs["verbose"] = True
    return benchmark_config.BenchmarkConfig(**kwargs)


async def orchestrate(cfg: benchmark_config.BenchmarkConfig) -> models.RunReport:
    wall_start = time.time()
    started_at_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    api_key = cfg.api_key
    project_id = cfg.project_id
    provisioned_email: str | None = None
    limits_bumped = False

    setup_limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)
    async with httpx.AsyncClient(
        http2=False,
        timeout=httpx.Timeout(30.0),
        limits=setup_limits,
    ) as setup_client:
        if api_key is None:
            print("[bench] Provisioning fresh account/project/api-key ...", flush=True)
            api_key, project_id, provisioned_email = await provisioning.provision(
                setup_client, cfg
            )
            limits_bumped = not cfg.respect_limits
            print(
                f"[bench] Project ID: {project_id} | limits: {'bypassed' if limits_bumped else 'default'}",
                flush=True,
            )
        else:
            if project_id is None:
                project_id = await provisioning.resolve_existing_key(cfg, api_key)
            print(f"[bench] Using existing key | Project ID: {project_id}", flush=True)

    api_key_prefix = (api_key[:16] + "...") if api_key else None
    report: models.RunReport

    if cfg.ramp:
        print(
            f"[bench] Auto-ramp: c={cfg.ramp_start}..{cfg.ramp_max} step={cfg.ramp_step} "
            f"stage={cfg.ramp_stage_seconds}s gzip={cfg.gzip}",
            flush=True,
        )
        stages = await ramp_module.run_ramp(cfg, api_key, project_id)

        best_stage = next((s for s in reversed(stages) if s.healthy), None)
        headline_rate = best_stage.drain_rate if best_stage else None
        headline_conc = best_stage.concurrency if best_stage else None

        if best_stage is not None:
            verdict = (
                f"SUSTAINABLE at {headline_rate:.0f} logs/s "
                f"(concurrency={headline_conc})"
            )
        else:
            verdict = "OVERLOADED at lowest tested concurrency"

        report = models.RunReport(
            mode="ramp",
            provisioned_email=provisioned_email,
            provisioned_project_id=project_id,
            api_key_prefix=api_key_prefix,
            limits_bumped=limits_bumped,
            stages=stages,
            best_stage=best_stage,
            headline_logs_per_second=headline_rate,
            headline_concurrency=headline_conc,
            verdict=verdict,
            started_at_utc=started_at_utc,
        )

    else:
        template_pool = payload_module.build_template_pool(
            max(2000, cfg.batch_size * 2)
        )
        print(
            f"[bench] Single run: c={cfg.concurrency} gzip={cfg.gzip} "
            f"duration={cfg.duration_seconds}s total_logs={cfg.total_logs}",
            flush=True,
        )

        phase = await load_engine.run_phase(
            cfg=cfg,
            api_key=api_key,
            concurrency=cfg.concurrency,
            template_pool=template_pool,
            duration_seconds=float(cfg.duration_seconds) if cfg.duration_seconds else None,
            total_logs=cfg.total_logs,
        )

        drain_client_limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        async with httpx.AsyncClient(
            http2=False,
            timeout=httpx.Timeout(30.0),
            limits=drain_client_limits,
        ) as monitor_client:
            print("[bench] Draining queue ...", flush=True)
            drain = await drain_module.wait_for_drain(
                monitor_client, cfg, api_key, timeout=120.0
            )

            db_delta: int | None = None
            if not cfg.no_db_verify:
                try:
                    db_delta = await drain_module.count_log_rows(
                        cfg.logs_db_dsn, project_id, phase.started_at
                    )
                except Exception as e:
                    print(f"[bench] DB verify error: {e}", flush=True)

        total_time = phase.duration_s + drain.drain_seconds
        drain_rate = phase.accepted / total_time if total_time > 0 else 0.0

        db_match = db_delta is None or db_delta >= int(phase.accepted * 0.99)
        verdict_parts: list[str] = []
        if phase.errors.total > 0:
            verdict_parts.append(f"errors={phase.errors.total}")
        if not drain.drained:
            verdict_parts.append("queue-not-drained")
        if not db_match:
            verdict_parts.append(f"db-mismatch(accepted={phase.accepted},db={db_delta})")

        if not verdict_parts:
            verdict = f"SUSTAINABLE at {drain_rate:.0f} logs/s"
        else:
            verdict = "OVERLOADED (" + ", ".join(verdict_parts) + ")"

        report = models.RunReport(
            mode="single",
            provisioned_email=provisioned_email,
            provisioned_project_id=project_id,
            api_key_prefix=api_key_prefix,
            limits_bumped=limits_bumped,
            single_phase=phase,
            single_drain=drain,
            single_db_delta=db_delta,
            headline_logs_per_second=drain_rate,
            headline_concurrency=cfg.concurrency,
            verdict=verdict,
            started_at_utc=started_at_utc,
        )

    report.finished_at_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report.total_wall_seconds = time.time() - wall_start
    report.config_summary = {
        "base_url": cfg.base_url,
        "batch_size": cfg.batch_size,
        "gzip": cfg.gzip,
        "ramp": cfg.ramp,
        "ramp_start": cfg.ramp_start,
        "ramp_step": cfg.ramp_step,
        "ramp_max": cfg.ramp_max,
        "ramp_stage_seconds": cfg.ramp_stage_seconds,
        "limits_bypassed": limits_bumped,
    }
    return report


def main() -> None:
    args = _parse_args()
    cfg = _build_config(args)

    if cfg.json_output is None and cfg.ramp:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        cfg.json_output = f"benchmark_result/bench_result_{stamp}.json"

    try:
        report = asyncio.run(orchestrate(cfg))
    except KeyboardInterrupt:
        print("\n[bench] Interrupted.", flush=True)
        sys.exit(1)

    reporting.print_report(report)

    if cfg.json_output:
        reporting.write_json(report, cfg.json_output)


if __name__ == "__main__":
    main()
