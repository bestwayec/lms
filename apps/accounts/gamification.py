"""
Gamification & Streak Engine (apps/accounts/gamification.py).

Duolingo-style daily habit loops:
- Streak flame (🔥 5 kun, 10 kun)
- Streak freeze protection
- XP rewards per educational action
- Weekly E-Sport Leagues (Bronze, Silver, Gold, Diamond)
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Dict

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _invalidate_gamification_caches(user_id: int | None = None, league: str | None = None) -> None:
    from django.core.cache import cache

    try:
        if user_id:
            cache.delete(f"tma_prof_stats:{user_id}")
        if league:
            cache.delete(f"grandec:weekly_league_v1:{league}")
        try:
            cache.incr("grandec:platform_lb_ver")
        except Exception:
            cache.set("grandec:platform_lb_ver", 2, timeout=None)
    except Exception:
        pass


@transaction.atomic
def record_user_activity(
    user,
    xp_amount: int = 20,
    activity_type: str = "general",
) -> Dict[str, Any]:
    """Record learning activity, update streak counter (if enabled), and atomically award XP."""
    if not user or not user.is_authenticated:
        return {"ok": False, "reason": "unauthenticated"}
    if not getattr(user, "is_active", True):
        return {"ok": False, "reason": "inactive"}

    safe_xp = max(0, int(xp_amount or 0))
    from apps.accounts.models import Profile

    profile, _ = Profile.objects.select_for_update().get_or_create(user=user)
    today = timezone.localdate()
    last_date = profile.last_activity_date

    streak_incremented = False
    streak_freeze_used = False

    if getattr(profile, "streak_opt_in", True):
        if last_date == today:
            pass
        elif last_date == today - timedelta(days=1):
            profile.current_streak += 1
            if profile.current_streak > profile.longest_streak:
                profile.longest_streak = profile.current_streak
            profile.last_activity_date = today
            streak_incremented = True
        elif last_date is None:
            profile.current_streak = 1
            profile.longest_streak = max(profile.longest_streak, 1)
            profile.last_activity_date = today
            streak_incremented = True
        else:
            days_missed = (today - last_date).days
            if days_missed == 2 and profile.streak_freeze_count > 0:
                profile.streak_freeze_count -= 1
                streak_freeze_used = True
                profile.current_streak += 1
                if profile.current_streak > profile.longest_streak:
                    profile.longest_streak = profile.current_streak
                profile.last_activity_date = today
            else:
                profile.current_streak = 1
                profile.last_activity_date = today

    # Award XP atomically under Profile lock
    profile.xp_points += safe_xp
    profile.weekly_xp += safe_xp

    # Dynamic promotion check based on weekly threshold
    if (
        profile.weekly_xp >= 800
        and profile.weekly_league != Profile.LeagueChoice.DIAMOND
    ):
        profile.weekly_league = Profile.LeagueChoice.DIAMOND
    elif profile.weekly_xp >= 400 and profile.weekly_league in (
        Profile.LeagueChoice.BRONZE,
        Profile.LeagueChoice.SILVER,
    ):
        profile.weekly_league = Profile.LeagueChoice.GOLD
    elif (
        profile.weekly_xp >= 150
        and profile.weekly_league == Profile.LeagueChoice.BRONZE
    ):
        profile.weekly_league = Profile.LeagueChoice.SILVER

    profile.save(
        update_fields=[
            "current_streak",
            "longest_streak",
            "last_activity_date",
            "streak_freeze_count",
            "xp_points",
            "weekly_xp",
            "weekly_league",
        ]
    )
    try:
        from django.core.cache import cache

        cache.delete(f"grandec:weekly_league_v1:{profile.weekly_league}")
    except Exception:
        pass

    return {
        "ok": True,
        "current_streak": profile.current_streak,
        "longest_streak": profile.longest_streak,
        "streak_incremented": streak_incremented,
        "streak_freeze_used": streak_freeze_used,
        "xp_earned": safe_xp,
        "total_xp": profile.xp_points,
        "weekly_xp": profile.weekly_xp,
        "league": profile.weekly_league,
    }


def get_user_streak_info(user) -> Dict[str, Any]:
    """Return user's streak status, daily goal progress, and league info."""
    if not user or not user.is_authenticated:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "is_active_today": False,
            "streak_freeze_count": 0,
            "xp_points": 0,
            "weekly_xp": 0,
            "weekly_league": "bronze",
            "daily_goal_completed": False,
        }

    from apps.accounts.models import Profile

    profile, _ = Profile.objects.get_or_create(user=user)
    today = timezone.localdate()
    is_active_today = profile.last_activity_date == today

    # If user missed more than 1 day and has no freeze, preview 0
    effective_streak = profile.current_streak
    if profile.last_activity_date and (today - profile.last_activity_date).days > 1:
        if profile.streak_freeze_count == 0:
            effective_streak = 0

    week_days = []
    day_labels = ["Du", "Se", "Chor", "Pay", "Jum", "Shan", "Yak"]
    monday = today - timedelta(days=today.weekday())
    for idx, label in enumerate(day_labels):
        d = monday + timedelta(days=idx)
        is_day_active = False
        if is_active_today and (today - timedelta(days=max(0, effective_streak - 1))) <= d <= today:
            is_day_active = True
        elif not is_active_today and profile.last_activity_date and (profile.last_activity_date - timedelta(days=max(0, effective_streak - 1))) <= d <= profile.last_activity_date:
            is_day_active = True

        week_days.append({
            "day": label,
            "date": d.isoformat(),
            "is_today": d == today,
            "is_past": d < today,
            "is_active": is_day_active,
        })

    milestones = [
        {
            "target": 7,
            "title": "7 kunlik Olov",
            "reward": "PRO bonus & BMB Mock kuponi",
            "reached": effective_streak >= 7,
            "progress_percent": min(100, int((effective_streak / 7) * 100)),
        },
        {
            "target": 30,
            "title": "30 kunlik Afsona",
            "reward": "VIP Attestatsiya va Sertifikat to'plami",
            "reached": effective_streak >= 30,
            "progress_percent": min(100, int((effective_streak / 30) * 100)),
        },
    ]

    return {
        "current_streak": effective_streak,
        "longest_streak": profile.longest_streak,
        "is_active_today": is_active_today,
        "streak_freeze_count": profile.streak_freeze_count,
        "xp_points": profile.xp_points,
        "weekly_xp": profile.weekly_xp,
        "weekly_league": profile.weekly_league,
        "daily_goal_completed": is_active_today,
        "week_days": week_days,
        "milestones": milestones,
    }


def _public_display_name(profile) -> str:
    """User-selected pseudonym preferred; never exposes real names, initials, or emails."""
    pseudo = (getattr(profile, "leaderboard_pseudonym", "") or "").strip()
    if pseudo:
        return pseudo[:40]
    return f"Ishtirokchi #{profile.user_id % 10000:04d}"


def get_weekly_league_leaderboard(user) -> Dict[str, Any]:
    """Return the weekly league leaderboard for opted-in users only (cached via Redis)."""
    from django.core.cache import cache
    from apps.accounts.models import Profile

    profile, _ = (
        Profile.objects.get_or_create(user=user)
        if user and user.is_authenticated
        else (None, False)
    )
    target_league = profile.weekly_league if profile else Profile.LeagueChoice.BRONZE
    lb_ver = cache.get("grandec:platform_lb_ver", 1)

    def _fetch_top_participants() -> list[dict[str, Any]]:
        top_profiles = (
            Profile.objects.filter(
                user__is_active=True,
                weekly_league=target_league,
                leaderboard_opt_in=True,
            )
            .select_related("user")
            .order_by("-weekly_xp", "-xp_points")[:20]
        )
        rows = []
        for idx, p in enumerate(top_profiles, start=1):
            rows.append(
                {
                    "rank": idx,
                    "user_id": p.user_id,
                    "name": _public_display_name(p),
                    "avatar_url": None,
                    "weekly_xp": p.weekly_xp,
                    "tier_badge": "🥇"
                    if idx == 1
                    else "🥈"
                    if idx == 2
                    else "🥉"
                    if idx == 3
                    else f"#{idx}",
                }
            )
        return rows

    base_rows = cache.get_or_set(
        f"grandec:weekly_league_v2:{target_league}:{lb_ver}", _fetch_top_participants, timeout=60
    )

    participants = []
    user_rank = None
    for row in base_rows:
        is_me = bool(user and user.is_authenticated and row["user_id"] == user.id)
        if is_me:
            user_rank = row["rank"]
        participants.append({**row, "is_current_user": is_me})

    # Next Sunday 23:59 calculation
    now = timezone.now()
    days_until_sunday = (6 - now.weekday()) % 7
    sunday_end = (now + timedelta(days=days_until_sunday)).replace(
        hour=23, minute=59, second=59
    )

    return {
        "league": target_league,
        "league_title": dict(Profile.LeagueChoice.choices).get(
            target_league, target_league.title()
        ),
        "opted_in": bool(profile and getattr(profile, "leaderboard_opt_in", False)),
        "pseudonym": getattr(profile, "leaderboard_pseudonym", "") if profile else "",
        "user_rank": user_rank,
        "participants": participants,
        "resets_in_hours": max(1, int((sunday_end - now).total_seconds() // 3600)),
    }


@transaction.atomic
def award_educational_xp(
    user: Any,
    event_type: str,
    reference_id: str,
    xp_amount: int = 20,
    metadata: dict[str, Any] | None = None,
) -> tuple[Any, bool]:
    """
    Atomically and idempotently awards XP for verified educational events.
    Guarantees that repeated callbacks, retries, or refreshes will NEVER award duplicate XP,
    and an interrupted transaction rolls back both the event and XP increment together.
    Returns (event, is_created).
    """
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", True):
        return None, False

    safe_xp = int(xp_amount or 0)
    if safe_xp <= 0:
        return None, False

    from apps.accounts.models import EducationalXPEvent

    event, created = EducationalXPEvent.objects.get_or_create(
        user=user,
        event_type=event_type,
        reference_id=str(reference_id),
        defaults={
            "xp_amount": safe_xp,
            "metadata": metadata or {},
        },
    )

    if not created:
        return event, False

    # Atomic inside same transaction: if record_user_activity fails, EducationalXPEvent rolls back too!
    res = record_user_activity(user, xp_amount=safe_xp, activity_type=event_type)
    league = res.get("league") if isinstance(res, dict) else None
    transaction.on_commit(lambda: _invalidate_gamification_caches(user_id=user.id, league=league))
    return event, True


def get_platform_leaderboard(
    user: Any | None = None,
    period: str = "weekly",
    limit: int = 20,
) -> dict[str, Any]:
    """
    Privacy-preserving, opt-in pseudonymous platform leaderboard.
    Excludes non-participating users; uses user-selected pseudonyms or opaque IDs.
    Never exposes real names, initials, emails, phones, private groups, or grades.
    """
    from django.core.cache import cache
    from apps.accounts.models import Profile

    period = period if period in ("weekly", "all_time") else "weekly"
    lb_ver = cache.get("grandec:platform_lb_ver", 1)
    cache_key = f"grandec:platform_lb_v3:{period}:{limit}:{lb_ver}"

    def _fetch():
        order_col = "-weekly_xp" if period == "weekly" else "-xp_points"
        top_profiles = (
            Profile.objects.filter(
                user__is_active=True,
                leaderboard_opt_in=True,
            )
            .select_related("user")
            .order_by(order_col, "-current_streak", "user_id")[:limit]
        )
        rows = []
        for idx, p in enumerate(top_profiles, start=1):
            xp_val = p.weekly_xp if period == "weekly" else p.xp_points
            rows.append({
                "rank": idx,
                "user_id": p.user_id,
                "display_name": _public_display_name(p),
                "avatar_url": None,
                "xp": xp_val,
                "streak": p.current_streak if getattr(p, "streak_opt_in", True) else None,
                "league": p.weekly_league,
                "badge": "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx}",
            })
        return rows

    base_rows = cache.get_or_set(cache_key, _fetch, timeout=60)
    user_rank = None
    items = []
    for r in base_rows:
        is_me = bool(user and getattr(user, "is_authenticated", False) and r["user_id"] == user.id)
        if is_me:
            user_rank = r["rank"]
        items.append({**r, "is_current_user": is_me})

    profile = getattr(user, "profile", None) if (user and getattr(user, "is_authenticated", False)) else None
    return {
        "period": period,
        "items": items,
        "user_rank": user_rank,
        "opted_in": bool(profile and getattr(profile, "leaderboard_opt_in", False)),
        "pseudonym": getattr(profile, "leaderboard_pseudonym", "") if profile else "",
    }

