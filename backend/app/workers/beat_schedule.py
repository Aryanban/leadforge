"""Celery beat schedule (Docker / distributed deployments only).

Mirrors the in-process background loops in ``app.main``. Only one of the two
is ever active: main.py skips its loops when USE_CELERY is true, so IMAP
sweeps and campaign ticks never double-count.

The campaign-schedule entry is the important one. Without a scheduler, a
multi-step sequence only advanced when a human manually re-clicked "Launch"
- the step-delay arithmetic existed but nothing ever drove it, so the
product's headline feature was manual-only.
"""

BEAT_SCHEDULE = {
    "poll-mailbox-replies-every-5-minutes": {
        "task": "app.workers.tasks.poll_replies_task",
        "schedule": 300.0,
    },
    "run-campaign-schedules-every-5-minutes": {
        "task": "app.workers.tasks.run_campaign_schedules_task",
        "schedule": 300.0,
    },
    "reset-mailbox-daily-counters-midnight-utc": {
        "task": "app.workers.tasks.reset_daily_send_counters_task",
        # 00:00 UTC = 05:30 IST - the start of the operator's day.
        "schedule": {"crontab": "0 0 * * *"},
    },
}
