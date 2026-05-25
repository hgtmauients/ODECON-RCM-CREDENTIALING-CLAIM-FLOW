import copy

from core import scheduler as scheduler_module


def _zero_metrics(metrics: dict) -> None:
    for value in metrics.values():
        value["runs"] = 0
        value["successes"] = 0
        value["failures"] = 0
        value["skips_locked"] = 0
        value["last_run_at"] = None
        value["last_success_at"] = None
        value["last_failure_at"] = None
        value["last_error"] = None


def test_scheduler_status_captures_success_skip_and_failure():
    original = copy.deepcopy(scheduler_module._scheduler_metrics)
    try:
        _zero_metrics(scheduler_module._scheduler_metrics)

        scheduler_module._record_job_run("poll_835_files", outcome="skipped_locked")
        scheduler_module._record_job_run("poll_835_files", outcome="success")
        scheduler_module._record_job_run("poll_835_files", outcome="failure", error="boom")

        snapshot = scheduler_module.get_scheduler_status()
        metrics = snapshot["jobs"]["poll_835_files"]

        assert metrics["runs"] == 3
        assert metrics["skips_locked"] == 1
        assert metrics["successes"] == 1
        assert metrics["failures"] == 1
        assert metrics["last_error"] == "boom"
        assert snapshot["enabled"] == scheduler_module.SCHEDULER_ENABLED
    finally:
        scheduler_module._scheduler_metrics.clear()
        scheduler_module._scheduler_metrics.update(original)
