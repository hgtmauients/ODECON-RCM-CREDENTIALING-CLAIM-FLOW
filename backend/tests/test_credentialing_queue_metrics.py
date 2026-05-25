from jobs import credentialing_queue


def test_credentialing_queue_stats_shape():
    stats = credentialing_queue.get_credentialing_queue_stats()
    expected_keys = {
        "runs",
        "items_claimed",
        "items_failed",
        "stale_recovered",
        "last_run_at",
        "last_success_at",
        "last_failure_at",
        "last_error",
    }
    assert expected_keys.issubset(set(stats.keys()))
