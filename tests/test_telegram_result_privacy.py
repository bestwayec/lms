"""Individual reports must never be disclosed through legacy group jobs."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.notifications.tasks import (
    _send_group_result_and_vedomost,
    broadcast_essay_result_to_groups,
    broadcast_speaking_result_to_groups,
)


@pytest.mark.parametrize("job", [
    _send_group_result_and_vedomost,
    broadcast_essay_result_to_groups,
    broadcast_speaking_result_to_groups,
])
def test_legacy_group_jobs_neither_send_nor_generate_reports(job):
    # No DB access is allowed: queued jobs must fail closed even with stale data.
    with (
        patch("apps.notifications.services.telegram_service.TelegramService._send_message") as message,
        patch("apps.notifications.services.telegram_service.TelegramService._send_document") as document,
        patch("apps.results.pdf_generator.generate_student_vedomost_pdf") as test_pdf,
        patch("apps.results.pdf_generator.generate_essay_vedomost_pdf") as essay_pdf,
        patch("apps.results.pdf_generator.generate_speaking_vedomost_pdf") as speaking_pdf,
    ):
        job(SimpleNamespace(id=123))
        job(SimpleNamespace(id=123))  # A duplicate/redelivery must be equally safe.
    for mocked in (message, document, test_pdf, essay_pdf, speaking_pdf):
        mocked.assert_not_called()
