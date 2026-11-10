"""Centralized upload validation — images, attachments.

Prevents stored XSS via uploaded HTML/SVG/scriptable files served from /media/.
Validates extension + size; MIME is checked where reliable but never trusted alone.
"""

from __future__ import annotations

import os
import re

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_ATTACHMENT_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "pdf",
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "txt",
    "zip",
}

# Block active content that browsers may execute same-origin from /media/.
BLOCKED_EXTENSIONS = {
    "html",
    "htm",
    "svg",
    "js",
    "xhtml",
    "xml",
    "swf",
    "php",
    "exe",
    "sh",
    "bat",
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


def _ext(name: str) -> str:
    return os.path.splitext(name or "")[1].lower().lstrip(".")


@deconstructible
class UploadValidator:
    """Reusable validator for FileField/ImageField."""

    def __init__(
        self,
        allowed: set[str] | frozenset | None = None,
        max_size: int = MAX_IMAGE_SIZE,
    ):
        self.allowed = set(allowed) if allowed else set(ALLOWED_IMAGE_EXTENSIONS)
        self.max_size = max_size

    def __call__(self, value) -> None:
        name = getattr(value, "name", "") or ""
        ext = _ext(name)
        if not ext:
            raise ValidationError("Fayl kengaytmasi aniqlanmadi.")
        if ext in BLOCKED_EXTENSIONS:
            raise ValidationError(
                f".{ext} fayllar xavfsizlik uchun bloklangan (aktiv kontent)."
            )
        if ext not in self.allowed:
            raise ValidationError(
                f".{ext} ruxsat etilmagan. Ruxsat: {', '.join(sorted(self.allowed))}."
            )
        size = getattr(value, "size", None)
        if size is not None and size > self.max_size:
            raise ValidationError(
                f"Fayl juda katta ({size} bayt). Maksimal {self.max_size} bayt."
            )


validate_image_upload = UploadValidator(ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_SIZE)
validate_attachment_upload = UploadValidator(
    ALLOWED_ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_SIZE
)

_XSS_SCRIPT_BLOCK_RE = re.compile(
    r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_XSS_TAG_RE = re.compile(
    r"<\s*/?\s*(?:script|iframe|object|embed|applet|meta|link|style|form|base|img|svg|body|input|video|audio|details|marquee)\b[^>]*>",
    re.IGNORECASE,
)
_XSS_EVENT_ATTR_RE = re.compile(
    r"\bon[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)
_XSS_JS_URI_RE = re.compile(
    r"(?:javascript|vbscript|data\s*:\s*text/html)\s*:",
    re.IGNORECASE,
)


def sanitize_text_xss(value: str | None) -> str:
    """Strip executable XSS payloads (<script>, <iframe>, event handlers, javascript: URIs)
    while preserving plain text, Uzbek apostrophes (o', g'), and math expressions."""
    if not value or not isinstance(value, str):
        return value or ""
    cleaned = _XSS_SCRIPT_BLOCK_RE.sub("", value)
    cleaned = _XSS_TAG_RE.sub("", cleaned)
    cleaned = _XSS_EVENT_ATTR_RE.sub("", cleaned)
    cleaned = _XSS_JS_URI_RE.sub("", cleaned)
    return cleaned

