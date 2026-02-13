"""
Gunicorn configuration file for rozert_pay project.

This file contains configuration for Gunicorn server, including
Prometheus multiprocess metrics cleanup.
"""

from prometheus_client import multiprocess


def child_exit(server, worker):  # type: ignore
    """
    Called just after a worker has been exited, in the master process.

    This is required for proper cleanup of Prometheus multiprocess metrics
    when a worker process dies. Without this, metrics from dead workers
    will continue to be counted, leading to incorrect metric values.
    """
    multiprocess.mark_process_dead(worker.pid)  # type: ignore[no-untyped-call]
