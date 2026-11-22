"""Settings for the real Django → React Playwright journey (local/CI only).

A throwaway SQLite file (E2E_DB_PATH) so the journey never touches a real
database; Celery runs eagerly; the notification outbox only queues.
"""

import os

from .development import *  # noqa: F401,F403
from .development import BASE_DIR

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("E2E_DB_PATH", str(BASE_DIR / "e2e.sqlite3")),
    }
}
CELERY_TASK_ALWAYS_EAGER = True
NOTIFICATION_OUTBOX_ENABLED = False
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": [], "DEFAULT_THROTTLE_RATES": {}}  # noqa: F405
