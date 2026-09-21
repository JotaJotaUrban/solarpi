from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import load_settings
from .economics import (
    ECONOMICS_DEFAULT_START_DATE,
    build_economics_balance_payload,
)
from .store import SnapshotStore


def main() -> None:
    settings = load_settings()
    store = SnapshotStore(settings.database_path)
    store.init_db()

    tz = _timezone(settings.timezone_name)
    now = datetime.now(tz)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    year_start = day_start.replace(month=1, day=1)
    cached_days = 0
    rebuilt_days = 0
    target_day = ECONOMICS_DEFAULT_START_DATE
    while target_day < now.date():
        _, rebuilt = store.ensure_daily_energy_summary(
            target_day=target_day,
            timezone_name=settings.timezone_name,
            tz=tz,
            max_gap_seconds=settings.totals_max_gap_seconds,
        )
        cached_days += 1
        if rebuilt:
            rebuilt_days += 1
        target_day += timedelta(days=1)

    energy_payload = {
        "timezone": settings.timezone_name,
        "generated_at": now.isoformat(),
        "provisional": False,
        "day": store.energy_totals_fast(
            start=day_start,
            end=now,
            max_gap_seconds=settings.totals_max_gap_seconds,
        ),
        "month": store.energy_totals_daily_summarized(
            start=month_start,
            end=now,
            timezone_name=settings.timezone_name,
            tz=tz,
            max_gap_seconds=settings.totals_max_gap_seconds,
        ),
        "year": store.energy_totals_daily_summarized(
            start=year_start,
            end=now,
            timezone_name=settings.timezone_name,
            tz=tz,
            max_gap_seconds=settings.totals_max_gap_seconds,
        ),
    }
    store.save_energy_summaries(energy_payload)

    economics_payload = build_economics_balance_payload(
        settings=settings,
        store=store,
        start_day=ECONOMICS_DEFAULT_START_DATE,
        now=now,
        latest=None,
    )
    store.save_economics_balance(economics_payload)

    print(
        "OK cached totals=%s economics=%s"
        % (
            energy_payload["generated_at"],
            "%s daily_days=%s rebuilt_days=%s"
            % (economics_payload["generated_at"], cached_days, rebuilt_days),
        )
    )


def _timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo or timezone.utc


if __name__ == "__main__":
    main()
