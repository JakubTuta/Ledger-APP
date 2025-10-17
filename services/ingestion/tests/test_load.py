import asyncio
import datetime
import time

import ingestion_service.proto.ingestion_pb2 as ingestion_pb2
import pytest

from .helpers import create_proto_log
from .test_base import BaseIngestionTest


@pytest.mark.asyncio
class TestLoadTesting(BaseIngestionTest):
    """Test ingestion service under high load."""

    async def test_rapid_single_ingestion(self):
        """Test rapid fire single log ingestion."""

        async def send_log(i):
            log_dict = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Rapid log {i}",
            }
            proto_log = create_proto_log(log_dict)
            request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)
            return await self.stub.IngestLog(request)

        start = time.time()

        tasks = [send_log(i) for i in range(100)]
        results = await asyncio.gather(*tasks)

        duration = time.time() - start

        assert all(r.success is True for r in results)
        print(
            f"✅ 100 rapid single ingestions completed in {duration:.3f}s ({100/duration:.1f} req/s)"
        )

    async def test_concurrent_batch_ingestion(self):
        """Test concurrent batch ingestion from multiple sources."""

        async def send_batch(batch_id, size):
            logs = [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Batch {batch_id} log {i}",
                }
                for i in range(size)
            ]
            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)
            return await self.stub.IngestLogBatch(request)

        start = time.time()

        tasks = [send_batch(i, 100) for i in range(20)]
        results = await asyncio.gather(*tasks)

        duration = time.time() - start

        assert all(r.success is True for r in results)
        total_logs = sum(r.queued for r in results)

        assert total_logs == 2000
        print(
            f"✅ 20 concurrent batches (2000 logs) completed in {duration:.3f}s ({total_logs/duration:.1f} logs/s)"
        )

    async def test_sustained_load_single(self):
        """Test sustained single log ingestion over time."""
        duration_seconds = 5
        logs_sent = 0
        start = time.time()

        while time.time() - start < duration_seconds:
            log_dict = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Sustained log {logs_sent}",
            }

            proto_log = create_proto_log(log_dict)
            request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)

            response = await self.stub.IngestLog(request)
            assert response.success is True
            logs_sent += 1

        actual_duration = time.time() - start
        rate = logs_sent / actual_duration

        print(
            f"✅ Sustained {logs_sent} single log ingestions over {actual_duration:.1f}s ({rate:.1f} logs/s)"
        )
        assert logs_sent > 100

    async def test_sustained_load_batch(self):
        """Test sustained batch ingestion over time."""
        duration_seconds = 5
        batches_sent = 0
        total_logs = 0
        start = time.time()

        while time.time() - start < duration_seconds:
            logs = [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Batch {batches_sent} log {i}",
                }
                for i in range(50)
            ]

            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

            response = await self.stub.IngestLogBatch(request)
            assert response.success is True
            total_logs += 50
            batches_sent += 1

        actual_duration = time.time() - start
        rate = total_logs / actual_duration

        print(
            f"✅ Sustained {batches_sent} batches ({total_logs} logs) over {actual_duration:.1f}s ({rate:.1f} logs/s)"
        )
        assert batches_sent > 20

    async def test_mixed_load_single_and_batch(self):
        """Test mixed single and batch ingestion concurrently."""

        async def send_single_logs(count):
            results = []
            for i in range(count):
                log_dict = {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "console",
                    "importance": "standard",
                    "message": f"Single log {i}",
                }
                proto_log = create_proto_log(log_dict)
                request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)
                results.append(await self.stub.IngestLog(request))
            return results

        async def send_batch_logs(count, batch_size):
            results = []
            for i in range(count):
                logs = [
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "level": "info",
                        "log_type": "logger",
                        "importance": "standard",
                        "message": f"Batch {i} log {j}",
                    }
                    for j in range(batch_size)
                ]
                proto_logs = [create_proto_log(log) for log in logs]
                request = ingestion_pb2.IngestLogBatchRequest(
                    project_id=1, logs=proto_logs
                )
                results.append(await self.stub.IngestLogBatch(request))
            return results

        start = time.time()

        single_task = send_single_logs(100)
        batch_task = send_batch_logs(10, 100)

        single_results, batch_results = await asyncio.gather(single_task, batch_task)

        duration = time.time() - start

        assert all(r.success is True for r in single_results)
        assert all(r.success is True for r in batch_results)

        total_logs = 100 + (10 * 100)
        print(
            f"✅ Mixed load (100 single + 10 batches = 1100 logs) completed in {duration:.3f}s"
        )

    async def test_high_concurrency_single(self):
        """Test very high concurrency for single log ingestion."""

        async def send_log(i):
            log_dict = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "console",
                "importance": "standard",
                "message": f"Concurrent log {i}",
            }
            proto_log = create_proto_log(log_dict)
            request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)
            return await self.stub.IngestLog(request)

        start = time.time()

        tasks = [send_log(i) for i in range(500)]
        results = await asyncio.gather(*tasks)

        duration = time.time() - start

        assert all(r.success is True for r in results)
        print(
            f"✅ 500 concurrent single logs completed in {duration:.3f}s ({500/duration:.1f} req/s)"
        )

    async def test_high_concurrency_batch(self):
        """Test very high concurrency for batch ingestion."""

        async def send_batch(batch_id):
            logs = [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Batch {batch_id} log {i}",
                }
                for i in range(50)
            ]
            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)
            return await self.stub.IngestLogBatch(request)

        start = time.time()

        tasks = [send_batch(i) for i in range(100)]
        results = await asyncio.gather(*tasks)

        duration = time.time() - start

        assert all(r.success is True for r in results)
        total_logs = sum(r.queued for r in results)

        print(
            f"✅ 100 concurrent batches ({total_logs} logs) completed in {duration:.3f}s ({total_logs/duration:.1f} logs/s)"
        )

    async def test_large_payload_stress(self):
        """Test ingestion with large payloads."""
        logs = [
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": "info",
                "log_type": "custom",
                "importance": "standard",
                "message": "x" * 5000,
                "attributes": {f"key_{j}": "x" * 100 for j in range(50)},
            }
            for i in range(100)
        ]

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        start = time.time()
        response = await self.stub.IngestLogBatch(request)
        duration = time.time() - start

        assert response.success is True
        print(
            f"✅ Large payload batch (100 logs with large attrs) ingested in {duration:.3f}s"
        )

    async def test_exception_heavy_load(self):
        """Test load with high percentage of exception logs."""
        logs = []

        for i in range(200):
            if i % 2 == 0:
                logs.append(
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "level": "error",
                        "log_type": "exception",
                        "importance": "high",
                        "message": f"Exception {i}",
                        "error_type": "TestError",
                        "error_message": f"Error {i}",
                        "stack_trace": f"Traceback for error {i}\n  File test.py line {i}",
                        "platform": "python",
                    }
                )
            else:
                logs.append(
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "level": "info",
                        "log_type": "console",
                        "importance": "standard",
                        "message": f"Info log {i}",
                    }
                )

        proto_logs = [create_proto_log(log) for log in logs]
        request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

        start = time.time()
        response = await self.stub.IngestLogBatch(request)
        duration = time.time() - start

        assert response.success is True
        print(
            f"✅ Exception-heavy batch (200 logs, 50% exceptions) ingested in {duration:.3f}s"
        )

    async def test_multi_project_concurrent_load(self):
        """Test concurrent ingestion for multiple projects."""

        async def send_project_batch(project_id, count):
            logs = [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Project {project_id} log {i}",
                }
                for i in range(count)
            ]
            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(
                project_id=project_id, logs=proto_logs
            )
            return await self.stub.IngestLogBatch(request)

        start = time.time()

        tasks = []
        for project_id in range(1, 11):
            for _ in range(10):
                tasks.append(send_project_batch(project_id, 50))

        results = await asyncio.gather(*tasks)

        duration = time.time() - start

        assert all(r.success is True for r in results)
        total_logs = sum(r.queued for r in results)

        print(
            f"✅ Multi-project load (10 projects, {total_logs} logs) completed in {duration:.3f}s ({total_logs/duration:.1f} logs/s)"
        )

    async def test_burst_traffic_pattern(self):
        """Test burst traffic pattern (sudden spike in requests)."""
        bursts = 5
        logs_per_burst = 100

        for burst_num in range(bursts):
            start = time.time()

            async def send_log(i):
                log_dict = {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "console",
                    "importance": "standard",
                    "message": f"Burst {burst_num} log {i}",
                }
                proto_log = create_proto_log(log_dict)
                request = ingestion_pb2.IngestLogRequest(project_id=1, log=proto_log)
                return await self.stub.IngestLog(request)

            tasks = [send_log(i) for i in range(logs_per_burst)]
            results = await asyncio.gather(*tasks)
            duration = time.time() - start

            assert all(r.success is True for r in results)
            print(
                f"  Burst {burst_num + 1}: {logs_per_burst} logs in {duration:.3f}s ({logs_per_burst/duration:.1f} logs/s)"
            )

            await asyncio.sleep(0.5)

        print(f"✅ Completed {bursts} bursts of {logs_per_burst} logs each")

    async def test_steady_state_throughput(self):
        """Test steady state throughput over extended period."""
        test_duration = 10
        batch_size = 100
        batches_sent = 0
        total_logs = 0

        start_time = time.time()
        last_clear_time = start_time

        while time.time() - start_time < test_duration:
            logs = [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Steady state log {total_logs + i}",
                }
                for i in range(batch_size)
            ]

            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)

            response = await self.stub.IngestLogBatch(request)
            assert response.success is True

            batches_sent += 1
            total_logs += batch_size

            current_time = time.time()
            if current_time - last_clear_time >= 1.0:
                queue_key = "queue:logs:1"
                await self.redis.delete(queue_key)
                last_clear_time = current_time

        actual_duration = time.time() - start_time
        throughput = total_logs / actual_duration

        print(
            f"✅ Steady state: {total_logs} logs over {actual_duration:.1f}s ({throughput:.1f} logs/s)"
        )
        assert total_logs > 1000

    async def test_varied_payload_sizes(self):
        """Test ingestion with varied payload sizes."""

        async def send_varied_batch(small, medium, large):
            logs = []

            for i in range(small):
                logs.append(
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "level": "info",
                        "log_type": "console",
                        "importance": "standard",
                        "message": "Small log",
                    }
                )

            for i in range(medium):
                logs.append(
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "level": "info",
                        "log_type": "custom",
                        "importance": "standard",
                        "message": "Medium log with some content",
                        "attributes": {f"key_{j}": f"value_{j}" for j in range(10)},
                    }
                )

            for i in range(large):
                logs.append(
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "level": "info",
                        "log_type": "custom",
                        "importance": "standard",
                        "message": "x" * 1000,
                        "attributes": {f"key_{j}": "x" * 100 for j in range(20)},
                    }
                )

            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)
            return await self.stub.IngestLogBatch(request)

        start = time.time()

        tasks = [send_varied_batch(30, 15, 5) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        duration = time.time() - start

        assert all(r.success is True for r in results)
        total_logs = sum(r.queued for r in results)

        print(f"✅ Varied payload sizes: {total_logs} logs in {duration:.3f}s")

    async def test_stress_test_maximum_throughput(self):
        """Stress test to find maximum throughput."""
        print("\n  Starting stress test...")

        batch_size = 100
        num_concurrent_batches = 50

        async def send_stress_batch(batch_id):
            logs = [
                {
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "level": "info",
                    "log_type": "logger",
                    "importance": "standard",
                    "message": f"Stress batch {batch_id} log {i}",
                }
                for i in range(batch_size)
            ]
            proto_logs = [create_proto_log(log) for log in logs]
            request = ingestion_pb2.IngestLogBatchRequest(project_id=1, logs=proto_logs)
            return await self.stub.IngestLogBatch(request)

        start = time.time()

        tasks = [send_stress_batch(i) for i in range(num_concurrent_batches)]
        results = await asyncio.gather(*tasks)

        duration = time.time() - start

        success_count = sum(1 for r in results if r.success is True)
        total_logs = sum(r.queued for r in results if r.success is True)

        throughput = total_logs / duration

        print(f"  Successful requests: {success_count}/{num_concurrent_batches}")
        print(f"  Total logs: {total_logs}")
        print(f"  Duration: {duration:.3f}s")
        print(f"  Throughput: {throughput:.1f} logs/s")

        assert success_count >= num_concurrent_batches * 0.95
        print("✅ Stress test completed")
