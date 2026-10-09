import datetime
import unittest.mock

import apscheduler.events as scheduler_events

import analytics_workers.main as main
import analytics_workers.services.self_monitoring as self_monitoring

_RUN_TIME = datetime.datetime(2026, 10, 9, 12, 0, tzinfo=datetime.timezone.utc)


def _counted(event) -> list:
    with unittest.mock.patch.object(self_monitoring, "increment") as increment:
        main._count_job_run(event)
    return increment.call_args_list


class TestJobRunCounter:
    def test_successful_run(self):
        event = scheduler_events.JobExecutionEvent(
            scheduler_events.EVENT_JOB_EXECUTED, "retention", "default", _RUN_TIME
        )
        assert _counted(event) == [
            unittest.mock.call(
                "ledger.analytics.job_runs", 1, {"job": "retention", "outcome": "ok"}
            )
        ]

    def test_failed_run(self):
        event = scheduler_events.JobExecutionEvent(
            scheduler_events.EVENT_JOB_ERROR,
            "alert_evaluator",
            "default",
            _RUN_TIME,
            exception=RuntimeError("boom"),
        )
        assert _counted(event)[0].args[2] == {"job": "alert_evaluator", "outcome": "error"}

    def test_missed_run(self):
        event = scheduler_events.JobExecutionEvent(
            scheduler_events.EVENT_JOB_MISSED, "log_metrics", "default", _RUN_TIME
        )
        assert _counted(event)[0].args[2] == {"job": "log_metrics", "outcome": "missed"}
