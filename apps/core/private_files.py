"""Authenticated delivery of private uploads (receipts, payment proofs, speaking audio).

These files must never be reachable through the public ``/media/`` mapping: they
belong to one person and are only meant for that person and the staff who review
them. Views authorise the caller and then hand the file to this helper, which

* never emits a public URL (callers expose the *API path* of the download view);
* sends ``Cache-Control: private, no-store`` so no shared cache keeps a copy;
* forces ``nosniff`` and a sandboxing CSP, and only renders a small allow-list of
  raster-image / audio types inline (everything else, SVG and HTML included, is
  an attachment);
* uses ``X-Accel-Redirect`` when ``PRIVATE_MEDIA_ACCEL_PREFIX`` is configured (nginx
  streams the bytes and handles Range requests) and streams through Django
  otherwise, so the feature works unchanged with today's deployment.
"""

from __future__ import annotations

import mimetypes
import os
import posixpath
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse

#: Storage prefixes that hold private files. Public media (avatars, topic images, exam
#: assets, logos) deliberately stays outside this list.
PRIVATE_MEDIA_PREFIXES = ("receipts/", "tuition/proofs/", "speaking/audio/")

_INLINE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "audio/mpeg",
        "audio/mp4",
        "audio/ogg",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "audio/aac",
        "video/webm",  # browsers record audio-only WebM as video/webm
    }
)


def is_private_media_name(name: str) -> bool:
    """True when a storage-relative file name lives under a private prefix."""
    normalized = posixpath.normpath(str(name or "").replace("\\", "/")).lstrip("/")
    return any(normalized.startswith(prefix) for prefix in PRIVATE_MEDIA_PREFIXES)


def _content_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def _harden(response: HttpResponse, *, filename: str, inline: bool) -> HttpResponse:
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Referrer-Policy"] = "no-referrer"
    disposition = "inline" if inline else "attachment"
    # RFC 6266: ASCII fallback plus UTF-8 name; no user-controlled bytes reach the header raw.
    ascii_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename) or "file"
    response["Content-Disposition"] = (
        f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    )
    return response


def private_file_response(field_file, *, download_name: str | None = None) -> HttpResponse:
    """Return the file behind a model ``FileField`` value; raise ``Http404`` if it is gone.

    Authorisation is the caller's job and must happen first.
    """
    if not field_file or not getattr(field_file, "name", ""):
        raise Http404("No file")
    name = field_file.name
    if not is_private_media_name(name):
        # A view must not become a way to read arbitrary storage paths.
        raise Http404("Not a private file")

    content_type = _content_type(name)
    inline = content_type in _INLINE_TYPES
    filename = download_name or os.path.basename(name)

    accel_prefix = getattr(settings, "PRIVATE_MEDIA_ACCEL_PREFIX", "") or ""
    if accel_prefix:
        safe_name = posixpath.normpath(name.replace("\\", "/")).lstrip("/")
        response = HttpResponse(content_type=content_type)
        # nginx replaces the body with the file from its internal location.
        response["X-Accel-Redirect"] = quote(f"{accel_prefix.rstrip('/')}/{safe_name}")
        return _harden(response, filename=filename, inline=inline)

    try:
        handle = field_file.storage.open(name, "rb")
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise Http404("File missing") from exc
    response = FileResponse(handle, content_type=content_type)
    return _harden(response, filename=filename, inline=inline)
