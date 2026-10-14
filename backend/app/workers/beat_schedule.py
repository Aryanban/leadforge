"""Celery beat schedule (Docker / distributed deployments only).

Mirrors the in-process background loop in ``app.main``. Only one of the two
is ever active: main.py skips its loop when USE_CELERY is true, so IMAP
sweeps never double-count.
"""

BEAT_SCHEDULE = {
    "poll-mailbox-replies-every-5-minutes": {
        "task": "app.workers.tasks.poll_replies_task",
        "schedule": 300.0,
    },
}
