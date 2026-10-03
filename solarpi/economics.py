from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from .config import Settings
from .models import InverterSnapshot
from .store import SnapshotStore


ECONOMICS_DEFAULT_START_DATE = date(2026, 8, 21)
ECONOMICS_EXPORT_PRICE_EUR_KWH = 0.06
ECONOMICS_RECOVERY_PRICE_EUR_KWH = 0.1599 * 0.85
ECONOMICS_BALANCE_EPSILON_EUR = 0.005


def build_economics_balance_payload(
    settings: Settings,
    store: SnapshotStore,
    start_day: date,
    now: datetime,
    latest: Optional[InverterSnapshot],
    use_sampled_totals: bool = False,
    end_day: Optional[date] = None,
) -> Dict[str, Any]:
    tz = now.tzinfo
    end_day = end_day or now.date()
    if start_day > end_day or end_day > now.date():
        raise ValueError("Expected start_date <= end_date <= today")
    next_day = end_day + timedelta(days=1)
    end_at = min(now, datetime(next_day.year, next_day.month, next_day.day, tzinfo=tz))
    if end_day < now.date():
        latest = None
    start_at = datetime(
        start_day.year,
        start_day.month,
        start_day.day,
        tzinfo=tz,
    )
    if use_sampled_totals:
        totals = store.energy_totals_sampled(
            start=start_at,
            end=end_at,
            sample_seconds=settings.poll_interval_seconds,
            max_gap_seconds=settings.totals_max_gap_seconds,
        )
    else:
        totals = store.energy_totals_daily_summarized(
            start=start_at,
            end=end_at,
            timezone_name=settings.timezone_name,
            tz=tz,
            latest=latest,
            max_gap_seconds=settings.totals_max_gap_seconds,
        )
    exported_kwh = _optional_float(totals.get("grid_export_kwh")) or 0.0
    imported_kwh = _optional_float(totals.get("grid_import_kwh")) or 0.0
    export_credit_eur = exported_kwh * ECONOMICS_EXPORT_PRICE_EUR_KWH
    recovery_cost_eur = imported_kwh * ECONOMICS_RECOVERY_PRICE_EUR_KWH
    balance_eur = export_credit_eur - recovery_cost_eur
    recoverable_kwh = max(0.0, balance_eur) / ECONOMICS_RECOVERY_PRICE_EUR_KWH
    balance_state = _balance_state(balance_eur)

    return {
        "timezone": settings.timezone_name,
        "generated_at": now.isoformat(),
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "end_at": end_at.isoformat(),
        "start_at": start_at.isoformat(),
        "period_label": "Del %s al %s" % (start_day.strftime("%d/%m/%Y"), end_day.strftime("%d/%m/%Y")),
        "exported_kwh": exported_kwh,
        "imported_kwh": imported_kwh,
        "recovered_kwh": imported_kwh,
        "export_credit_eur": round(export_credit_eur, 4),
        "recovery_cost_eur": round(recovery_cost_eur, 4),
        "balance_eur": round(balance_eur, 4),
        "recoverable_kwh": round(recoverable_kwh, 3),
        "balance_state": balance_state,
        "balance_label": _balance_label(balance_state),
        "rates": {
            "export_price_eur_kwh": ECONOMICS_EXPORT_PRICE_EUR_KWH,
            "recovery_price_eur_kwh": ECONOMICS_RECOVERY_PRICE_EUR_KWH,
        },
        "totals": totals,
    }


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _balance_state(balance_eur: float) -> str:
    if balance_eur > ECONOMICS_BALANCE_EPSILON_EUR:
        return "positive"
    if balance_eur < -ECONOMICS_BALANCE_EPSILON_EUR:
        return "negative"
    return "even"


def _balance_label(balance_state: str) -> str:
    return {
        "positive": "Saldo a favor",
        "negative": "Saldo pendiente",
        "even": "Equilibrado",
    }.get(balance_state, "Equilibrado")
