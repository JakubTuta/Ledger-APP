import asyncio
import dataclasses
import random
import time

import httpx

import config as benchmark_config
import models
import payloads as payload_module


_RESERVOIR_MAX = 200_000


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
) -> models.PhaseResult:
    if duration_seconds is None and total_logs is None:
        raise ValueError("Provide duration_seconds or total_logs")

    stop_event = asyncio.Event()
    counter = _Counter(total_logs)
    started_at = time.time()
    start_mono = time.monotonic()

    base_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    limits = httpx.Limits(
        max_connections=concurrency + 4,
        max_keepalive_connections=concurrency,
    )

    async def worker(wid: int, client: httpx.AsyncClient) -> _WorkerStats:
        rng = random.Random(wid)
        stats = _WorkerStats()

        while not stop_event.is_set():
            batch_size = await counter.take(cfg.batch_size)
            if batch_size is None:
                break

            body = payload_module.build_batch_body(template_pool, batch_size, rng)
            compressed, extra_headers = payload_module.maybe_gzip(body, cfg.gzip)

            t0 = time.monotonic()
            try:
                resp = await client.post(
                    f"{cfg.base_url}/v1/logs",
                    content=compressed,
                    headers=extra_headers,
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
                data = resp.json()
                rejected = int(data.get("partialSuccess", {}).get("rejectedLogRecords", 0))
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
    )
