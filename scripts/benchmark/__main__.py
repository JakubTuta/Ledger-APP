import argparse
import asyncio
import datetime
import os
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

# scripts/benchmark/__main__.py -> scripts -> Ledger-APP (the repo root), regardless
# of the caller's cwd - this is what was landing json_output in two different
# directories depending on whether the script was invoked from the repo root or
# from inside scripts/benchmark/.
_LEDGER_APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ledger ingestion throughput benchmark. "
            "Zero args = steady-state --find-max: open-loop pacer, binary search for the "
            "max offered rate the pipeline holds with a flat queue, in-SLO latency, and "
            "exact DB accounting."
        )
    )
    parser.add_argument(
        "--mode", choices=["steady", "ramp", "single"], default=None, help="Benchmark mode"
    )
    parser.add_argument(
        "--base-url", default=None, help="Gateway base URL (default: http://localhost:8020)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=None, help="Worker count for single-run mode"
    )
    parser.add_argument(
        "--batch-size", type=int, default=None, help="Logs per batch (1-1000, default 1000)"
    )
    parser.add_argument("--no-gzip", action="store_true", help="Disable gzip compression")
    parser.add_argument(
        "--wire",
        choices=["protobuf", "json"],
        default=None,
        help="OTLP wire format (default protobuf)",
    )
    parser.add_argument(
        "--log-id-mode",
        choices=["client", "none"],
        default=None,
        help="client: exact-accounting via client-generated ids (default). "
        "none: exercise the server's fallback id path and report collisions",
    )
    parser.add_argument(
        "--duration", type=int, default=None, metavar="SECONDS", help="Single-run duration"
    )
    parser.add_argument("--total-logs", type=int, default=None, help="Single-run log count")

    steady = parser.add_argument_group("steady mode")
    steady.add_argument("--offered-rate", type=float, default=None, help="Fixed offered logs/s")
    steady.add_argument(
        "--find-max", action="store_true", help="Binary search for max sustainable offered rate"
    )
    steady.add_argument("--warmup-seconds", type=float, default=None)
    steady.add_argument("--hold-seconds", type=float, default=None)
    steady.add_argument("--max-inflight", type=int, default=None)
    steady.add_argument("--depth-slope-tolerance", type=float, default=None)
    steady.add_argument("--slo-p50-ms", type=float, default=None)
    steady.add_argument("--slo-p99-ms", type=float, default=None)
    steady.add_argument("--client-cpu-budget", type=float, default=None)

    ramp = parser.add_argument_group("ramp mode (legacy)")
    ramp.add_argument(
        "--ramp-max", type=int, default=None, help="Max concurrency to test (default 64)"
    )
    ramp.add_argument(
        "--ramp-stage-seconds", type=int, default=None, help="Seconds per ramp stage (default 30)"
    )

    parser.add_argument(
        "--api-key", default=None, help="Reuse existing API key (skips provisioning)"
    )
    parser.add_argument("--project-id", type=int, default=None, help="Project ID (with --api-key)")
    parser.add_argument(
        "--respect-limits", action="store_true", help="Do not bypass rate/quota limits"
    )
    parser.add_argument(
        "--no-db-verify", action="store_true", help="Skip Logs DB row count verification"
    )
    parser.add_argument(
        "--destructive-reset",
        action="store_true",
        help="Delete this project's rows before each stage/run (requires --expect-db)",
    )
    parser.add_argument(
        "--expect-db",
        default=None,
        help="Safety confirmation for --destructive-reset: substring that must appear in the DSN",
    )
    parser.add_argument(
        "--json-output", default=None, metavar="FILE", help="Write results JSON to file"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="After writing JSON, regenerate README.md/CLAUDE.md's benchmark sections",
    )
    parser.add_argument("--verbose", action="store_true", help="Extra output")
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> benchmark_config.BenchmarkConfig:
    kwargs: dict = {}
    if args.mode:
        kwargs["mode"] = args.mode
    if args.base_url:
        kwargs["base_url"] = args.base_url
    if args.concurrency is not None:
        kwargs["concurrency"] = args.concurrency
    if args.batch_size is not None:
        kwargs["batch_size"] = args.batch_size
    if args.no_gzip:
        kwargs["gzip"] = False
    if args.wire:
        kwargs["wire"] = args.wire
    if args.log_id_mode:
        kwargs["log_id_mode"] = args.log_id_mode
    if args.duration is not None:
        kwargs["duration_seconds"] = args.duration
        kwargs.setdefault("mode", "single")
    if args.total_logs is not None:
        kwargs["total_logs"] = args.total_logs
        kwargs.setdefault("mode", "single")
    if args.offered_rate is not None:
        kwargs["offered_rate"] = args.offered_rate
    if args.find_max:
        kwargs["find_max"] = True
    if args.warmup_seconds is not None:
        kwargs["warmup_seconds"] = args.warmup_seconds
    if args.hold_seconds is not None:
        kwargs["hold_seconds"] = args.hold_seconds
    if args.max_inflight is not None:
        kwargs["max_inflight"] = args.max_inflight
    if args.depth_slope_tolerance is not None:
        kwargs["depth_slope_tolerance"] = args.depth_slope_tolerance
    if args.slo_p50_ms is not None:
        kwargs["slo_p50_ms"] = args.slo_p50_ms
    if args.slo_p99_ms is not None:
        kwargs["slo_p99_ms"] = args.slo_p99_ms
    if args.client_cpu_budget is not None:
        kwargs["client_cpu_budget"] = args.client_cpu_budget
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
    if args.destructive_reset:
        kwargs["destructive_reset"] = True
    if args.expect_db:
        kwargs["expect_db"] = args.expect_db
    if args.json_output:
        kwargs["json_output"] = args.json_output
    if args.publish:
        kwargs["publish"] = True
    if args.verbose:
        kwargs["verbose"] = True
    return benchmark_config.BenchmarkConfig(**kwargs)


async def _reset_if_requested(cfg: benchmark_config.BenchmarkConfig, project_id: int) -> None:
    if cfg.destructive_reset:
        await drain_module.truncate_project_partitions(cfg.logs_db_dsn, project_id, cfg.expect_db)


def _steady_health_check(
    result: models.SteadyResult,
    cfg: benchmark_config.BenchmarkConfig,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if result.errors.total != 0:
        reasons.append(f"errors={result.errors.total}")
    if result.pacer_stalls != 0:
        reasons.append(f"pacer_stalls={result.pacer_stalls} (client-side backpressure hit)")
    if result.depth_slope_per_s > cfg.depth_slope_tolerance:
        reasons.append(
            f"queue growing at {result.depth_slope_per_s:.2f} envelopes/s "
            f"(tolerance {cfg.depth_slope_tolerance})"
        )
    if result.latency.p99_ms > cfg.slo_p99_ms:
        reasons.append(f"p99={result.latency.p99_ms:.0f}ms > SLO {cfg.slo_p99_ms:.0f}ms")
    if result.latency.p50_ms > cfg.slo_p50_ms:
        reasons.append(f"p50={result.latency.p50_ms:.0f}ms > SLO {cfg.slo_p50_ms:.0f}ms")
    if result.offered_rate > 0:
        drift = abs(result.achieved_ingress_rate - result.offered_rate) / result.offered_rate
        if drift > cfg.ingress_tolerance:
            reasons.append(
                f"achieved {result.achieved_ingress_rate:.0f}/s vs offered "
                f"{result.offered_rate:.0f}/s (drift {drift:.1%}) - client/server couldn't "
                f"sustain the offered rate"
            )
    if result.missing_rows is not None and result.missing_rows != 0:
        reasons.append(f"missing_rows={result.missing_rows}")
    if (
        result.client_cpu_fraction is not None
        and result.client_cpu_fraction > cfg.client_cpu_budget
    ):
        reasons.append(
            f"client_cpu={result.client_cpu_fraction:.2f} cores > budget "
            f"{cfg.client_cpu_budget:.2f} - benchmark client may be the bottleneck, not the server"
        )

    return (len(reasons) == 0, reasons)


async def _run_steady_stage(
    cfg: benchmark_config.BenchmarkConfig,
    api_key: str,
    project_id: int,
    template_pool: list[dict],
    offered_rate: float,
    monitor_client: httpx.AsyncClient,
) -> models.SteadyResult:
    await _reset_if_requested(cfg, project_id)
    stage_started_at = time.time()

    async def depth_sampler() -> int:
        return await drain_module.get_queue_depth(monitor_client, cfg)

    result, run_id = await load_engine.run_steady(
        cfg, api_key, template_pool, offered_rate, depth_sampler
    )

    print(
        f"[steady] offered={offered_rate:.0f}/s achieved={result.achieved_ingress_rate:.0f}/s "
        f"p50={result.latency.p50_ms:.0f}ms p99={result.latency.p99_ms:.0f}ms "
        f"errors={result.errors.total} stalls={result.pacer_stalls} "
        f"slope={result.depth_slope_per_s:.2f}/s | flushing ...",
        flush=True,
    )

    drain_result = await drain_module.wait_for_drain(
        monitor_client, cfg, timeout=float(cfg.ramp_drain_timeout)
    )
    result.post_run_flush_seconds = drain_result.drain_seconds

    if not cfg.no_db_verify:
        if cfg.log_id_mode == "client":
            found = await drain_module.wait_for_stable_count(
                cfg.logs_db_dsn, project_id, run_id, stage_started_at
            )
            result.missing_rows = result.accepted - found
        else:
            found = await drain_module.wait_for_stable_count(
                cfg.logs_db_dsn, project_id, None, stage_started_at
            )
            result.expected_dedupe_collisions = max(0, result.accepted - found)

        try:
            result.table_growth = await drain_module.get_table_growth_stats(
                cfg.logs_db_dsn, stage_started_at
            )
        except Exception as e:
            print(f"[steady] table growth query failed: {e}", flush=True)

    healthy, reasons = _steady_health_check(result, cfg)
    result.healthy = healthy
    result.fail_reasons = reasons

    verdict_label = "OK" if healthy else f"UNHEALTHY ({'; '.join(reasons)})"
    print(f"[steady] offered={offered_rate:.0f}/s -> {verdict_label}", flush=True)

    return result


async def _run_steady_mode(
    cfg: benchmark_config.BenchmarkConfig,
    api_key: str,
    project_id: int,
) -> models.RunReport:
    template_pool = payload_module.build_template_pool(max(2000, cfg.batch_size * 2))
    steady_runs: list[models.SteadyResult] = []

    monitor_limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)
    async with httpx.AsyncClient(
        http2=False, timeout=httpx.Timeout(30.0), limits=monitor_limits
    ) as monitor_client:
        if cfg.find_max:
            start_rate = cfg.offered_rate or 2000.0
            absolute_cap = 500_000.0
            lo = 0.0
            hi: float | None = None
            current = start_rate

            while hi is None:
                result = await _run_steady_stage(
                    cfg, api_key, project_id, template_pool, current, monitor_client
                )
                steady_runs.append(result)
                if result.healthy:
                    lo = current
                    if current * 2 > absolute_cap:
                        hi = absolute_cap
                        break
                    current *= 2
                else:
                    hi = current

            for _ in range(5):
                mid = (lo + hi) / 2
                result = await _run_steady_stage(
                    cfg, api_key, project_id, template_pool, mid, monitor_client
                )
                steady_runs.append(result)
                if result.healthy:
                    lo = mid
                else:
                    hi = mid

            max_rate = lo
            verdict = f"SUSTAINABLE at {max_rate:.0f} logs/s offered (steady-state, --find-max)"
        else:
            if cfg.offered_rate is None:
                print(
                    "[steady] ERROR: --offered-rate or --find-max is required in steady mode",
                    flush=True,
                )
                sys.exit(2)
            result = await _run_steady_stage(
                cfg, api_key, project_id, template_pool, cfg.offered_rate, monitor_client
            )
            steady_runs.append(result)
            max_rate = cfg.offered_rate if result.healthy else None
            verdict = (
                f"SUSTAINABLE at {cfg.offered_rate:.0f} logs/s offered"
                if result.healthy
                else f"UNHEALTHY at {cfg.offered_rate:.0f} logs/s offered "
                f"({'; '.join(result.fail_reasons)})"
            )

    return models.RunReport(
        mode="steady",
        steady_runs=steady_runs,
        max_sustainable_offered_rate=max_rate,
        headline_logs_per_second=max_rate,
        verdict=verdict,
    )


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
            api_key, project_id, provisioned_email = await provisioning.provision(setup_client, cfg)
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

    if cfg.mode == "steady":
        print(
            f"[bench] Steady-state: wire={cfg.wire} log_id_mode={cfg.log_id_mode} "
            f"find_max={cfg.find_max} offered_rate={cfg.offered_rate} "
            f"warmup={cfg.warmup_seconds}s hold={cfg.hold_seconds}s",
            flush=True,
        )
        report = await _run_steady_mode(cfg, api_key, project_id)
        report.provisioned_email = provisioned_email
        report.provisioned_project_id = project_id
        report.api_key_prefix = api_key_prefix
        report.limits_bumped = limits_bumped

    elif cfg.mode == "ramp":
        print(
            f"[bench] Auto-ramp (legacy): c={cfg.ramp_start}..{cfg.ramp_max} step={cfg.ramp_step} "
            f"stage={cfg.ramp_stage_seconds}s gzip={cfg.gzip} wire={cfg.wire}",
            flush=True,
        )
        stages = await ramp_module.run_ramp(cfg, api_key, project_id)

        best_stage = max((s for s in stages if s.healthy), key=lambda s: s.drain_rate, default=None)
        headline_rate = best_stage.drain_rate if best_stage else None
        headline_conc = best_stage.concurrency if best_stage else None

        if best_stage is not None:
            verdict = (
                f"SUSTAINABLE at {headline_rate:.0f} logs/s (concurrency={headline_conc}) "
                f"[legacy ramp mode - drain_rate is a haircut on ingress, not a direct "
                f"measurement; use --mode steady --find-max for a trustworthy headline]"
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
        template_pool = payload_module.build_template_pool(max(2000, cfg.batch_size * 2))
        print(
            f"[bench] Single run: c={cfg.concurrency} gzip={cfg.gzip} wire={cfg.wire} "
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
            drain = await drain_module.wait_for_drain(monitor_client, cfg, timeout=120.0)

            db_delta: int | None = None
            if not cfg.no_db_verify:
                try:
                    if phase.run_id is not None:
                        db_delta = await drain_module.count_log_rows_by_id_prefix(
                            cfg.logs_db_dsn, project_id, phase.run_id
                        )
                    else:
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
    report.started_at_utc = report.started_at_utc or started_at_utc
    report.config_summary = {
        "mode": cfg.mode,
        "base_url": cfg.base_url,
        "batch_size": cfg.batch_size,
        "gzip": cfg.gzip,
        "wire": cfg.wire,
        "log_id_mode": cfg.log_id_mode,
        "offered_rate": cfg.offered_rate,
        "find_max": cfg.find_max,
        "warmup_seconds": cfg.warmup_seconds,
        "hold_seconds": cfg.hold_seconds,
        "max_inflight": cfg.max_inflight,
        "slo_p50_ms": cfg.slo_p50_ms,
        "slo_p99_ms": cfg.slo_p99_ms,
        "client_cpu_budget": cfg.client_cpu_budget,
        "ramp_start": cfg.ramp_start,
        "ramp_step": cfg.ramp_step,
        "ramp_max": cfg.ramp_max,
        "ramp_stage_seconds": cfg.ramp_stage_seconds,
        "limits_bypassed": limits_bumped,
        "destructive_reset": cfg.destructive_reset,
    }
    return report


def main() -> None:
    args = _parse_args()
    cfg = _build_config(args)

    if cfg.mode == "steady" and not cfg.find_max and cfg.offered_rate is None:
        cfg.find_max = True

    if cfg.json_output is None:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        cfg.json_output = os.path.join(
            _LEDGER_APP_ROOT, "benchmark_result", f"bench_result_{stamp}.json"
        )

    try:
        report = asyncio.run(orchestrate(cfg))
    except KeyboardInterrupt:
        print("\n[bench] Interrupted.", flush=True)
        sys.exit(1)

    reporting.print_report(report)

    if cfg.json_output:
        reporting.write_json(report, cfg.json_output)

    if cfg.publish:
        import publish as publish_module

        publish_module.publish_latest(cfg.json_output)


if __name__ == "__main__":
    main()
