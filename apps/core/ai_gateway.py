"""Shared AI Gateway, Grounded Evidence Verification & Calibration Helpers.

Centralizes:
1. Bounded evidence quote extraction with character-offset grounding (EVIDENCE_V2).
2. Honest insufficiency checks (`RESULT_INSUFFICIENT_RESPONSE_EVIDENCE`).
3. Standardized AI usage & cost accounting (used by Admin AI Cost Control Dashboard).
4. Deterministic writing rubric calibration scoring against anchor benchmarks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache

from apps.core.ai_health import AIUnavailable, record_ai_failure, record_ai_success

__all__ = [
    "AIUnavailable",
    "EvidenceSpan",
    "compute_calibrated_stats",
    "find_grounded_offset",
    "get_ai_usage_summary",
    "is_insufficient_response",
    "record_ai_failure",
    "record_ai_success",
    "record_ai_usage",
    "verify_evidence_items",
]

AI_USAGE_CACHE_KEY = "grandec:ai_usage_metrics_v1"
MIN_WRITING_EVIDENCE_WORDS = 12


@dataclass(frozen=True)
class EvidenceSpan:
    quote: str
    start_offset: int
    end_offset: int
    verified: bool


def _normalize_ws(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        (text or "")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u00a0", " "),
    ).strip()


def _find_all_occurrences(src: str, q: str) -> list[tuple[int, int]]:
    """Return all (start, end) character index pairs for ``q`` inside ``src``."""
    matches: list[tuple[int, int]] = []
    start = 0
    while True:
        idx = src.find(q, start)
        if idx == -1:
            break
        matches.append((idx, idx + len(q)))
        start = idx + max(1, len(q))
    if matches:
        return matches

    lower_src = src.lower()
    lower_q = q.lower()
    start = 0
    while True:
        idx = lower_src.find(lower_q, start)
        if idx == -1:
            break
        matches.append((idx, idx + len(q)))
        start = idx + max(1, len(q))
    if matches:
        return matches

    # Whitespace & curly-quote tolerant search on raw string using flexible character classes
    tokens = [re.escape(tok) for tok in _normalize_ws(q).split(" ") if tok]
    if 1 <= len(tokens) <= 45:
        joined = r"[\s\u00a0]+".join(tokens)
        joined = joined.replace("'", r"['\u2018\u2019]").replace('"', r'["\u201c\u201d]')
        pattern = re.compile(joined, re.IGNORECASE)
        for m in pattern.finditer(src):
            matches.append((m.start(), m.end()))
    return matches


def find_grounded_offset(
    source_text: str,
    quote: str,
    *,
    occurrence: int = 0,
    context_hint: str = "",
    exclude_spans: set[tuple[int, int]] | None = None,
) -> EvidenceSpan:
    """Locate ``quote`` inside ``source_text`` with repeated-phrase & Unicode support."""
    src = source_text or ""
    q = (quote or "").strip().strip('"\'\u201c\u201d\u2018\u2019')
    if not q or len(q) < 4:
        return EvidenceSpan(quote=q, start_offset=-1, end_offset=-1, verified=False)

    candidates = _find_all_occurrences(src, q)
    if not candidates:
        return EvidenceSpan(quote=q, start_offset=-1, end_offset=-1, verified=False)

    pool = [c for c in candidates if not exclude_spans or c not in exclude_spans] or candidates
    chosen = pool[occurrence] if 0 <= occurrence < len(pool) else pool[0]

    hint = _normalize_ws(context_hint).lower()
    if hint and len(pool) > 1:
        hint_tokens = [tok for tok in re.findall(r"[a-z0-9']+", hint) if len(tok) >= 4]
        best_score = -1
        for s_idx, e_idx in pool:
            window = _normalize_ws(src[max(0, s_idx - 25) : min(len(src), e_idx + 45)]).lower()
            score = 100 if hint in window else sum(1 for tok in hint_tokens if tok in window)
            if score > best_score:
                best_score = score
                chosen = (s_idx, e_idx)

    s_idx, e_idx = chosen
    return EvidenceSpan(quote=src[s_idx:e_idx], start_offset=s_idx, end_offset=e_idx, verified=True)


def verify_evidence_items(items: list[dict[str, Any]], source_text: str) -> list[dict[str, Any]]:
    """Enrich criterion/feedback items with verified start_offset/end_offset spans."""
    enriched: list[dict[str, Any]] = []
    seen_counts: dict[str, int] = {}
    used_spans: set[tuple[int, int]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        copy_item = dict(item)
        raw_quote = str(item.get("quote") or item.get("evidence_quote") or "").strip()
        if raw_quote:
            key = _normalize_ws(raw_quote).lower()
            explicit_occ = str(item.get("occurrence", "")).isdigit()
            occ = int(item.get("occurrence")) if explicit_occ else seen_counts.get(key, 0)
            seen_counts[key] = occ + 1
            span = find_grounded_offset(
                source_text,
                raw_quote,
                occurrence=occ,
                context_hint=str(item.get("context") or item.get("reason") or ""),
                exclude_spans=None if explicit_occ else used_spans,
            )
            if span.verified:
                used_spans.add((span.start_offset, span.end_offset))
            copy_item["quote"] = span.quote
            copy_item["start_offset"] = span.start_offset
            copy_item["end_offset"] = span.end_offset
            copy_item["quote_verified"] = span.verified
        else:
            copy_item["start_offset"] = -1
            copy_item["end_offset"] = -1
            copy_item["quote_verified"] = False
        enriched.append(copy_item)
    return enriched


def is_insufficient_response(text: str, min_words: int = MIN_WRITING_EVIDENCE_WORDS) -> bool:
    """True when response lacks enough lexical content to assign an honest AI band."""
    words = [w for w in re.findall(r"[A-Za-z0-9']+", text or "") if any(c.isalpha() for c in w)]
    return len(words) < min_words


def record_ai_usage(
    *,
    feature: str,
    model: str = "deepseek/deepseek-r1-0528",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    latency_ms: float = 0.0,
    success: bool = True,
) -> None:
    """Accumulate lightweight per-feature AI telemetry cleanly for admin observability."""
    try:
        summary = dict(cache.get(AI_USAGE_CACHE_KEY) or {})
        by_feature = dict(summary.get("by_feature") or {})
        entry = dict(
            by_feature.get(feature)
            or {
                "calls": 0,
                "success": 0,
                "failures": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "avg_latency_ms": 0.0,
                "model": model,
            }
        )
        entry["calls"] = int(entry["calls"]) + 1
        entry["success" if success else "failures"] = int(entry["success" if success else "failures"]) + 1
        entry["tokens_in"] = int(entry["tokens_in"]) + max(0, int(tokens_in))
        entry["tokens_out"] = int(entry["tokens_out"]) + max(0, int(tokens_out))
        entry["cost_usd"] = round(float(entry["cost_usd"]) + max(0.0, float(cost_usd)), 6)
        n = entry["calls"]
        entry["avg_latency_ms"] = round(((float(entry["avg_latency_ms"]) * (n - 1)) + max(0.0, float(latency_ms))) / n, 1)
        entry["model"] = model
        by_feature[feature] = entry
        summary["by_feature"] = by_feature
        summary["total_calls"] = sum(int(v["calls"]) for v in by_feature.values())
        summary["total_cost_usd"] = round(sum(float(v["cost_usd"]) for v in by_feature.values()), 6)
        cache.set(AI_USAGE_CACHE_KEY, summary, timeout=86400 * 7)
    except Exception:
        pass


def get_ai_usage_summary() -> dict[str, Any]:
    return dict(cache.get(AI_USAGE_CACHE_KEY) or {"total_calls": 0, "total_cost_usd": 0.0, "by_feature": {}})


def get_ai_gateway_health() -> dict[str, Any]:
    """Combined AI cost summary + per-feature circuit breaker state for Admin Control."""
    usage = get_ai_usage_summary()
    features: dict[str, Any] = {}
    for feat in ("essay_ielts", "essay", "speaking", "vocab", "converter"):
        raw_fail = cache.get(f"ai_health:fail:{feat}") or 0
        tripped = bool(cache.get(f"ai_health:open:{feat}"))
        features[feat] = {
            "circuit_open": tripped,
            "recent_failures": int(raw_fail),
            "usage": (usage.get("by_feature") or {}).get(feat, {}),
        }
    return {
        "total_calls": usage.get("total_calls", 0),
        "total_cost_usd": usage.get("total_cost_usd", 0.0),
        "features": features,
    }


def compute_calibrated_stats(anchors: list[dict[str, float]]) -> dict[str, Any]:
    """Compute MAE and within-0.5-band accuracy over calibrated anchor essays."""
    if not anchors:
        return {"count": 0, "mae": None, "within_half_band_pct": None}
    diffs = [abs(float(a["predicted"]) - float(a["expected"])) for a in anchors]
    within_half = sum(1 for d in diffs if d <= 0.5)
    return {
        "count": len(anchors),
        "mae": round(sum(diffs) / len(diffs), 3),
        "within_half_band_pct": round(within_half * 100.0 / len(anchors), 1),
    }
