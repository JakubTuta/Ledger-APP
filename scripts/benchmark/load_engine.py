import asyncio
import dataclasses
import os
import random
import time
import uuid

import httpx
import psutil

import config as benchmark_config
import models
import payloads as payload_module

_RESERVOIR_MAX = 200_000


def new_run_id() -> str:
    return uuid.uuid4().hex[:10]


def _log_ids_for_batch(run_id: str, worker_id: int, start_seq: int, count: int) -> list[str]:
    return [f"{run_id}-{worker_id}-{start_seq + i}" for i in range(count)]


class _CpuSampler:
    """
    Samples the benchmark client's own process CPU during a phase/hold, so a
    run can prove it wasn't the bottleneck instead of assuming it. psutil's
    cpu_percent is relative to one core (150% == 1.5 cores busy).
    """

    def __init__(self) -> None:
        self._proc = psutil.Process(os.getpid())
        self._samples: list[float] = []
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _loop(self) -> None:
        self._proc.cpu_percent(interval=None)
        while not self._stop.is_set():
            await asyncio.sleep(1.0)
            self._samples.append(self._proc.cpu_percent(interval=None))

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> float | None:
        self._stop.set()
        if self._task is not None:
            await self._task
        if not self._samples:
            return None
        return (sum(self._samples) / len(self._samples)) / 100.0


@dataclasses.dataclass
class _WorkerStats:
    accepted: int = 0
    rejected: int = 0
    requests: int = 0
    err_429: int = 0
    err_402: int = 0
    err_503: int = 0
    err_500: int = 0
    err_transport: int = 0
    latencies: list[float] = dataclasses.field(default_factory=list)


class _Counter:
    def __init__(self, value: int | None) -> None:
        self._value = value
        self._lock = asyncio.Lock()

    async def take(self, batch_size: int) -> int | None:
        if self._value is None:
            return batch_size
        async with self._lock:
            if self._value <= 0:
                return None
            n = min(batch_size, self._value)
            self._value -= n
            return n


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = min(int(len(values) * p), len(values) - 1)
    return values[idx]


def _compute_latency_stats(samples: list[float]) -> models.LatencyStats:
    if not samples:
        return models.LatencyStats()
    ms = sorted(v * 1000 for v in samples)
    return models.LatencyStats(
        p50_ms=_percentile(ms, 0.50),
        p95_ms=_percentile(ms, 0.95),
        p99_ms=_percentile(ms, 0.99),
        mean_ms=sum(ms) / len(ms),
        min_ms=ms[0],
        max_ms=ms[-1],
    )


async def _timer(seconds: float, event: asyncio.Event) -> None:
    await asyncio.sleep(seconds)
    event.set()


async def run_phase(
    cfg: benchmark_config.BenchmarkConfig,
    api_key: str,
    concurrency: int,
    template_pool: list[dict],
    duration_seconds: float | None = None,
    total_logs: int | None = None,
    run_id: str | None = None,
) -> models.PhaseResult:
    """Closed-loop burst: `concurrency` workers post as fast as the server lets them."""
    if duration_seconds is None and total_logs is None:
        raise ValueError("Provide duration_seconds or total_logs")

    run_id = run_id or new_run_id()
    stop_event = asyncio.Event()
    counter = _Counter(total_logs)
    started_at = time.time()
    start_mono = time.monotonic()

    base_headers = {"Authorization": f"Bearer {api_key}"}
    limits = httpx.Limits(
        max_connections=concurrency + 4,
        max_keepalive_connections=concurrency,
    )

    async def worker(wid: int, client: httpx.AsyncClient) -> _WorkerStats:
        rng = random.Random(wid)
        stats = _WorkerStats()
        seq = 0

        while not stop_event.is_set():
            batch_size = await counter.take(cfg.batch_size)
            if batch_size is None:
                break

            log_ids = (
                _log_ids_for_batch(run_id, wid, seq, batch_size)
                if cfg.log_id_mode == "client"
                else None
            )
            seq += batch_size
            body, content_type = payload_module.build_batch_body(
                template_pool, batch_size, rng, wire=cfg.wire, log_ids=log_ids
            )
            compressed, extra_headers = payload_module.maybe_gzip(body, cfg.gzip)
            headers = {"Content-Type": content_type, **extra_headers}

            t0 = time.monotonic()
            try:
                resp = await client.post(
                    f"{cfg.base_url}/v1/logs",
                    content=compressed,
                    headers=headers,
                )
                latency = time.monotonic() - t0
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
                stats.err_transport += 1
                continue
            except Exception:
                stats.err_transport += 1
                continue

            stats.requests += 1

            if resp.status_code == 200:
                rejected = payload_module.parse_partial_success(
                    resp.headers.get("content-type", ""), resp.content
                )
                stats.rejected += rejected
                stats.accepted += batch_size - rejected
                if len(stats.latencies) < _RESERVOIR_MAX:
                    stats.latencies.append(latency)
                else:
                    idx = rng.randint(0, _RESERVOIR_MAX - 1)
                    stats.latencies[idx] = latency
            elif resp.status_code == 429:
                stats.err_429 += 1
                if cfg.respect_limits:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "1")))
            elif resp.status_code == 402:
                stats.err_402 += 1
                if cfg.respect_limits:
                    stop_event.set()
            elif resp.status_code == 503:
                stats.err_503 += 1
            else:
                stats.err_500 += 1

        return stats

    timer_task: asyncio.Task | None = None
    if duration_seconds is not None:
        timer_task = asyncio.create_task(_timer(duration_seconds, stop_event))

    cpu_sampler = _CpuSampler()
    cpu_sampler.start()

    async with httpx.AsyncClient(
        http2=False,
        timeout=httpx.Timeout(cfg.request_timeout),
        limits=limits,
        headers=base_headers,
    ) as client:
        worker_results: list[_WorkerStats] = await asyncio.gather(
            *[worker(i, client) for i in range(concurrency)]
        )

    if timer_task is not None:
        timer_task.cancel()

    client_cpu_fraction = await cpu_sampler.stop()
    elapsed = time.monotonic() - start_mono

    total_accepted = sum(r.accepted for r in worker_results)
    total_rejected = sum(r.rejected for r in worker_results)
    total_requests = sum(r.requests for r in worker_results)
    errors = models.ErrorBreakdown(
        rate_429=sum(r.err_429 for r in worker_results),
        quota_402=sum(r.err_402 for r in worker_results),
        queue_503=sum(r.err_503 for r in worker_results),
        server_500=sum(r.err_500 for r in worker_results),
        transport=sum(r.err_transport for r in worker_results),
    )

    all_latencies: list[float] = []
    for r in worker_results:
        all_latencies.extend(r.latencies)
    if len(all_latencies) > _RESERVOIR_MAX:
        all_latencies = random.Random(0).sample(all_latencies, _RESERVOIR_MAX)

    ingress_rate = total_accepted / elapsed if elapsed > 0 else 0.0

    return models.PhaseResult(
        concurrency=concurrency,
        duration_s=elapsed,
        total_requests=total_requests,
        accepted=total_accepted,
        rejected=total_rejected,
        errors=errors,
        latency=_compute_latency_stats(all_latencies),
        ingress_rate=ingress_rate,
        started_at=started_at,
        client_cpu_fraction=client_cpu_fraction,
        run_id=run_id if cfg.log_id_mode == "client" else None,
    )


def _linreg_slope(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


async def run_steady(
    cfg: benchmark_config.BenchmarkConfig,
    api_key: str,
    template_pool: list[dict],
    offered_rate: float,
    depth_sampler,
    run_id: str | None = None,
) -> tuple[models.SteadyResult, str]:
    """
    Open-loop pacer: batch k is launched at t0 + k*batch_size/offered_rate
    regardless of whether earlier batches have returned, bounded by
    `--max-inflight`. Hitting that bound is a `pacer_stall` and is itself a
    saturation signal - unlike run_phase's closed-loop workers, this can't
    silently degrade into "however fast the server answers" and call it the
    offered rate.

    `depth_sampler` is an async callable returning the current queue depth;
    it's sampled every 250ms for the whole warmup+hold window.
    """
    run_id = run_id or new_run_id()
    batch_size = cfg.batch_size
    interval = batch_size / offered_rate
    total_seconds = cfg.warmup_seconds + cfg.hold_seconds
    num_batches = max(1, round(total_seconds / interval))

    base_headers = {"Authorization": f"Bearer {api_key}"}
    limits = httpx.Limits(
        max_connections=cfg.max_inflight + 8,
        max_keepalive_connections=cfg.max_inflight,
    )

    inflight = 0
    pacer_stalls = 0
    cv = asyncio.Condition()

    accepted = 0
    rejected = 0
    total_requests = 0
    errors = models.ErrorBreakdown()
    latencies: list[float] = []
    lock = asyncio.Lock()

    depth_series: list[int] = []
    depth_timestamps: list[float] = []
    stop_sampling = asyncio.Event()

    start_mono = time.monotonic()

    async def sample_depth_loop() -> None:
        while not stop_sampling.is_set():
            try:
                depth = await depth_sampler()
                depth_series.append(depth)
                depth_timestamps.append(time.monotonic() - start_mono)
            except Exception:
                pass
            await asyncio.sleep(0.25)

    async def send_one(batch_index: int, client: httpx.AsyncClient, is_warmup: bool) -> None:
        nonlocal inflight, accepted, rejected, total_requests
        rng = random.Random(batch_index)
        # batch_index alone namespaces the whole batch (each launched exactly
        # once), so "worker_id"=batch_index / start_seq=0 gives every record in
        # the run a globally unique id with no cross-worker coordination needed.
        # Warmup batches never get a client log_id: they're excluded from
        # accepted/total_requests below, so counting their rows in the DB
        # verification query would make found > accepted and produce a
        # negative "missing" count.
        log_ids = (
            _log_ids_for_batch(run_id, batch_index, 0, batch_size)
            if cfg.log_id_mode == "client" and not is_warmup
            else None
        )
        body, content_type = payload_module.build_batch_body(
            template_pool, batch_size, rng, wire=cfg.wire, log_ids=log_ids
        )
        compressed, extra_headers = payload_module.maybe_gzip(body, cfg.gzip)
        headers = {"Content-Type": content_type, **extra_headers}

        t0 = time.monotonic()
        try:
            resp = await client.post(f"{cfg.base_url}/v1/logs", content=compressed, headers=headers)
            latency = time.monotonic() - t0
            status = resp.status_code
            body_bytes = resp.content
            resp_content_type = resp.headers.get("content-type", "")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
            status = None
            latency = None
        except Exception:
            status = None
            latency = None

        async with lock:
            if not is_warmup:
                total_requests += 1
            if status is None:
                if not is_warmup:
                    errors.transport += 1
            elif status == 200:
                rej = payload_module.parse_partial_success(resp_content_type, body_bytes)
                if not is_warmup:
                    rejected += rej
                    accepted += batch_size - rej
                    if latency is not None:
                        latencies.append(latency)
            elif status == 429:
                if not is_warmup:
                    errors.rate_429 += 1
            elif status == 402:
                if not is_warmup:
                    errors.quota_402 += 1
            elif status == 503:
                if not is_warmup:
                    errors.queue_503 += 1
            else:
                if not is_warmup:
                    errors.server_500 += 1

        async with cv:
            inflight -= 1
            cv.notify_all()

    cpu_sampler = _CpuSampler()
    cpu_sampler.start()
    sampler_task = asyncio.create_task(sample_depth_loop())

    async with httpx.AsyncClient(
        http2=False,
        timeout=httpx.Timeout(cfg.request_timeout),
        limits=limits,
        headers=base_headers,
    ) as client:
        tasks: list[asyncio.Task] = []
        for k in range(num_batches):
            target = start_mono + k * interval
            now = time.monotonic()
            if target > now:
                await asyncio.sleep(target - now)

            # Warmup/hold membership is decided by the batch's scheduled slot,
            # not by when its response happens to land - a slow request
            # crossing the boundary shouldn't get counted on the wrong side.
            is_warmup = (k * interval) < cfg.warmup_seconds

            async with cv:
                if inflight >= cfg.max_inflight:
                    pacer_stalls += 1
                    await cv.wait_for(lambda: inflight < cfg.max_inflight)
                inflight += 1

            tasks.append(asyncio.create_task(send_one(k, client, is_warmup)))

        await asyncio.gather(*tasks)

    stop_sampling.set()
    await sampler_task
    client_cpu_fraction = await cpu_sampler.stop()

    # Deliberately cfg.hold_seconds (the nominal window batches were launched
    # into), not measured wall time since warmup ended: gather() also waits out
    # the tail latency of whatever was still in flight when the last batch was
    # launched, which would otherwise inflate the denominator and understate
    # achieved_ingress_rate by however long the slowest in-flight request took.
    achieved_ingress_rate = accepted / cfg.hold_seconds if cfg.hold_seconds > 0 else 0.0

    # Slope over the last 2/3 of the hold - the first third can still carry
    # ramp-up noise from the warmup/hold boundary.
    hold_depths = [
        (t, d) for t, d in zip(depth_timestamps, depth_series) if t >= cfg.warmup_seconds
    ]
    slope_window = hold_depths[len(hold_depths) // 3 :] if hold_depths else []
    depth_slope = _linreg_slope([t for t, _ in slope_window], [float(d) for _, d in slope_window])

    return (
        models.SteadyResult(
            offered_rate=offered_rate,
            warmup_seconds=cfg.warmup_seconds,
            hold_seconds=cfg.hold_seconds,
            batch_size=batch_size,
            max_inflight=cfg.max_inflight,
            pacer_stalls=pacer_stalls,
            achieved_ingress_rate=achieved_ingress_rate,
            accepted=accepted,
            rejected=rejected,
            total_requests=total_requests,
            errors=errors,
            latency=_compute_latency_stats(latencies),
            client_cpu_fraction=client_cpu_fraction,
            depth_series=depth_series,
            depth_slope_per_s=depth_slope,
            missing_rows=None,
            post_run_flush_seconds=0.0,
            healthy=False,
            started_at=time.time() - total_seconds,
        ),
        run_id,
    )
