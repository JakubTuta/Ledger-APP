import asyncio
import sys

import httpx

import config as benchmark_config
import drain as drain_module
import load_engine
import models
import payloads as payload_module


async def run_ramp(
    cfg: benchmark_config.BenchmarkConfig,
    api_key: str,
    project_id: int,
) -> list[models.StageResult]:
    template_pool = payload_module.build_template_pool(
        max(2000, cfg.batch_size * 2)
    )
    stage_concurrencies = range(cfg.ramp_start, cfg.ramp_max + 1, cfg.ramp_step)
    results: list[models.StageResult] = []

    monitor_limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)

    async with httpx.AsyncClient(
        http2=False,
        timeout=httpx.Timeout(30.0),
        limits=monitor_limits,
    ) as monitor_client:
        initial_depth = await drain_module.get_queue_depth(monitor_client, cfg, api_key)
        if initial_depth > 100:
            print(
                f"[ramp] Initial queue depth {initial_depth} > 100 — waiting for drain...",
                flush=True,
            )
            pre_drain = await drain_module.wait_for_drain(
                monitor_client, cfg, api_key, timeout=float(cfg.ramp_drain_timeout)
            )
            if not pre_drain.drained:
                print(
                    "[ramp] ABORT: queue will not drain — stack is not idle. "
                    "Run './scripts/Make.ps1 down && ./scripts/Make.ps1 up' and retry.",
                    flush=True,
                )
                sys.exit(1)

        for concurrency in stage_concurrencies:
            print(
                f"[ramp] Stage c={concurrency} | {cfg.ramp_stage_seconds}s burst ...",
                flush=True,
            )

            phase = await load_engine.run_phase(
                cfg=cfg,
                api_key=api_key,
                concurrency=concurrency,
                template_pool=template_pool,
                duration_seconds=float(cfg.ramp_stage_seconds),
            )

            print(
                f"[ramp] c={concurrency} ingress={phase.ingress_rate:.0f} logs/s "
                f"accepted={phase.accepted} errors={phase.errors.total} | draining ...",
                flush=True,
            )

            drain = await drain_module.wait_for_drain(
                monitor_client,
                cfg,
                api_key,
                timeout=float(cfg.ramp_drain_timeout),
            )

            db_delta: int | None = None
            if not cfg.no_db_verify and drain.drained:
                try:
                    db_delta = await drain_module.count_log_rows(
                        cfg.logs_db_dsn, project_id, phase.started_at
                    )
                except Exception as e:
                    print(f"[ramp] DB verify error: {e}", flush=True)

            total_time = phase.duration_s + drain.drain_seconds
            drain_rate = phase.accepted / total_time if total_time > 0 else 0.0

            db_match = (
                db_delta is None
                or db_delta >= int(phase.accepted * 0.99)
            )
            healthy = (
                phase.errors.total == 0
                and drain.drained
                and drain.max_depth < 90_000
                and db_match
            )

            saturation_cause: str | None = None
            if not healthy:
                if phase.errors.queue_503 > 0:
                    saturation_cause = "queue-full (503)"
                elif not drain.drained:
                    saturation_cause = "drain-timeout"
                elif drain.max_depth >= 90_000:
                    saturation_cause = "queue-near-cap"
                elif not db_match and db_delta is not None:
                    saturation_cause = (
                        f"db-mismatch (accepted={phase.accepted}, db={db_delta})"
                    )
                elif phase.errors.total > 0:
                    saturation_cause = f"send-errors ({phase.errors.total} total)"

            stage = models.StageResult(
                concurrency=concurrency,
                phase=phase,
                drain=drain,
                db_delta=db_delta,
                ingress_rate=phase.ingress_rate,
                drain_rate=drain_rate,
                healthy=healthy,
                saturation_cause=saturation_cause,
            )
            results.append(stage)

            verdict_label = "OK" if healthy else f"SATURATED ({saturation_cause})"
            print(
                f"[ramp] c={concurrency} drain_rate={drain_rate:.0f} logs/s "
                f"max_depth={drain.max_depth} db_delta={db_delta} -> {verdict_label}",
                flush=True,
            )

            if not healthy:
                break

        if cfg.ramp_confirm:
            last_healthy = next((s for s in reversed(results) if s.healthy), None)
            if last_healthy is not None:
                print(
                    f"[ramp] Confirming best stage c={last_healthy.concurrency} ...",
                    flush=True,
                )
                confirm_phase = await load_engine.run_phase(
                    cfg=cfg,
                    api_key=api_key,
                    concurrency=last_healthy.concurrency,
                    template_pool=template_pool,
                    duration_seconds=float(cfg.ramp_stage_seconds),
                )
                await drain_module.wait_for_drain(
                    monitor_client,
                    cfg,
                    api_key,
                    timeout=float(cfg.ramp_drain_timeout),
                )
                print(
                    f"[ramp] Confirm ingress={confirm_phase.ingress_rate:.0f} logs/s "
                    f"accepted={confirm_phase.accepted}",
                    flush=True,
                )

    return results
