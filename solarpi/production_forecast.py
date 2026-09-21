from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo
from typing import Any, Dict, List, Optional, Tuple

from .models import InverterSnapshot
from .store import SnapshotStore


LOCATION_KEY = "borriol"
METHOD_VERSION = "solarpi-production-forecast-v1"
CORRECTION_FACTOR_KEY = "production_correction_factor"
HISTORY_DAYS = 400
SEASONAL_WINDOW_DAYS = 21
MIN_SEASONAL_SAMPLES = 3
DAY_CLOSED_SOLAR_W_THRESHOLD = 80


def build_tomorrow_production_forecast(
    store: SnapshotStore,
    weather_payload: Dict[str, Any],
    now: datetime,
    tz: tzinfo,
    latest: Optional[InverterSnapshot],
    max_gap_seconds: float,
) -> Optional[Dict[str, Any]]:
    location = weather_payload.get("location")
    if not isinstance(location, dict):
        return None
    if str(location.get("id") or "").strip().lower() != LOCATION_KEY:
        return None

    forecast = weather_payload.get("tomorrow")
    if not isinstance(forecast, dict):
        return None

    target_date = _date_from_iso(forecast.get("date"))
    if target_date is None:
        return None

    local_now = now if now.tzinfo else now.replace(tzinfo=tz)
    local_today = local_now.astimezone(tz).date()
    _finalize_due_predictions(store, local_today, tz, max_gap_seconds)

    correction_factor = _bounded_correction(
        store.get_prediction_state(CORRECTION_FACTOR_KEY, 1.0)
    )
    weather_history = store.weather_radiation_history(LOCATION_KEY)
    history = store.daily_production_history(
        end_date=target_date,
        days=HISTORY_DAYS,
        tz=tz,
        max_gap_seconds=max_gap_seconds,
        latest=latest,
    )
    base = _estimate_base(history, target_date)
    closed_today_base = _closed_today_observed_base(
        store=store,
        weather_payload=weather_payload,
        local_today=local_today,
        tz=tz,
        latest=latest,
        max_gap_seconds=max_gap_seconds,
        weather_history=weather_history,
    )
    base = _prefer_closed_today_base(base, closed_today_base)
    radiation_reference = _radiation_reference(weather_history, target_date)
    weather_factor, weather_details = estimate_weather_factor(
        forecast,
        radiation_reference,
    )

    predicted_kwh: Optional[float] = None
    if base["base_kwh"] is not None:
        predicted_kwh = round(
            float(base["base_kwh"]) * weather_factor * correction_factor,
            2,
        )

    confidence = _confidence(base, radiation_reference)
    prediction = {
        "target_date": target_date.isoformat(),
        "location_key": LOCATION_KEY,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "base_kwh": base["base_kwh"],
        "base_source": base["base_source"],
        "base_sample_count": base["sample_count"],
        "weather_factor": round(weather_factor, 4),
        "correction_factor": round(correction_factor, 4),
        "predicted_kwh": predicted_kwh,
        "method_version": METHOD_VERSION,
        "details": {
            "confidence": confidence,
            "base": base,
            "closed_today_base": closed_today_base,
            "weather": weather_details,
            "radiation_reference": radiation_reference,
        },
    }
    store.upsert_solar_prediction(prediction)

    return {
        "target_date": prediction["target_date"],
        "location_key": LOCATION_KEY,
        "estimated_kwh": predicted_kwh,
        "base_kwh": prediction["base_kwh"],
        "base_source": prediction["base_source"],
        "base_sample_count": prediction["base_sample_count"],
        "weather_factor": prediction["weather_factor"],
        "correction_factor": prediction["correction_factor"],
        "confidence": confidence,
        "method_version": METHOD_VERSION,
        "details": prediction["details"],
    }


def estimate_weather_factor(
    forecast: Dict[str, Any],
    radiation_reference: Optional[Dict[str, Any]] = None,
) -> Tuple[float, Dict[str, Any]]:
    code = _optional_int(forecast.get("weather_code"))
    daylight_seconds = _optional_float(forecast.get("daylight_duration_seconds"))
    sunshine_seconds = _optional_float(forecast.get("sunshine_duration_seconds"))
    radiation = _optional_float(forecast.get("shortwave_radiation_sum_mj_m2"))
    sunshine_ratio = _ratio(sunshine_seconds, daylight_seconds)

    reference_value = None
    reference_samples = 0
    if radiation_reference:
        reference_value = _optional_float(radiation_reference.get("value"))
        reference_samples = int(radiation_reference.get("sample_count") or 0)

    if radiation is not None and reference_value and reference_value > 0:
        radiation_factor = _clamp(radiation / reference_value, 0.12, 1.08)
        radiation_source = "seasonal_radiation_history"
    elif sunshine_ratio is not None:
        radiation_factor = sunshine_ratio
        radiation_source = "sunshine_fallback"
    else:
        radiation_factor = _weather_code_default(code)
        radiation_source = "weather_code_fallback"

    sunshine_factor = (
        sunshine_ratio if sunshine_ratio is not None else _weather_code_default(code)
    )
    raw_factor = 0.75 * radiation_factor + 0.25 * sunshine_factor

    precipitation_probability = _optional_float(
        forecast.get("precipitation_probability_percent")
    )
    precipitation_sum = _optional_float(forecast.get("precipitation_sum_mm"))
    precipitation_penalty = 1.0
    if precipitation_probability is not None:
        precipitation_penalty *= 1.0 - min(0.2, max(0.0, precipitation_probability) / 500.0)
    if precipitation_sum is not None:
        precipitation_penalty *= 1.0 - min(0.15, max(0.0, precipitation_sum) / 80.0)

    code_penalty = _weather_code_penalty(code)
    factor = _clamp(raw_factor * precipitation_penalty * code_penalty, 0.12, 1.05)

    return round(factor, 4), {
        "weather_code": code,
        "radiation_mj_m2": radiation,
        "radiation_reference_mj_m2": reference_value,
        "radiation_reference_sample_count": reference_samples,
        "radiation_source": radiation_source,
        "radiation_factor": round(radiation_factor, 4),
        "sunshine_ratio": round(sunshine_ratio, 4) if sunshine_ratio is not None else None,
        "precipitation_penalty": round(precipitation_penalty, 4),
        "weather_code_penalty": round(code_penalty, 4),
    }


def _closed_today_observed_base(
    store: SnapshotStore,
    weather_payload: Dict[str, Any],
    local_today: date,
    tz: tzinfo,
    latest: Optional[InverterSnapshot],
    max_gap_seconds: float,
    weather_history: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    today_forecast = weather_payload.get("today")
    if not isinstance(today_forecast, dict):
        return None
    if _date_from_iso(today_forecast.get("date")) != local_today:
        return None
    if not _is_day_closed(weather_payload, latest):
        return None

    actual = store.daily_production_for_date(
        day=local_today,
        tz=tz,
        max_gap_seconds=max_gap_seconds,
        latest=latest,
    )
    actual_kwh = _optional_float(actual.get("production_kwh"))
    if actual_kwh is None or actual_kwh <= 0.1 or actual["sample_count"] <= 0:
        return None

    weather_factor, weather_details = estimate_weather_factor(
        today_forecast,
        _radiation_reference(weather_history, local_today),
    )
    if weather_factor <= 0:
        return None

    base_kwh = actual_kwh / weather_factor
    return {
        "base_kwh": round(base_kwh, 3),
        "base_source": "closed_today_weather_adjusted",
        "sample_count": 1,
        "history_sample_count": 1,
        "observed_date": local_today.isoformat(),
        "actual_production_kwh": round(actual_kwh, 3),
        "actual_sample_count": actual["sample_count"],
        "weather_factor": round(weather_factor, 4),
        "weather": weather_details,
    }


def _is_day_closed(
    weather_payload: Dict[str, Any],
    latest: Optional[InverterSnapshot],
) -> bool:
    if weather_payload.get("is_day") is not False:
        return False
    if latest is None:
        return True
    return abs(int(latest.solar_power_w)) <= DAY_CLOSED_SOLAR_W_THRESHOLD


def _prefer_closed_today_base(
    base: Dict[str, Any],
    closed_today_base: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not closed_today_base:
        return base
    if base.get("base_source") == "seasonal_history":
        return base
    return closed_today_base


def _finalize_due_predictions(
    store: SnapshotStore,
    local_today: date,
    tz: tzinfo,
    max_gap_seconds: float,
) -> None:
    correction_factor = _bounded_correction(
        store.get_prediction_state(CORRECTION_FACTOR_KEY, 1.0)
    )

    for prediction in store.pending_predictions(before_date=local_today):
        target_date = _date_from_iso(prediction.get("target_date"))
        predicted_kwh = _optional_float(prediction.get("predicted_kwh"))
        if target_date is None or predicted_kwh is None or predicted_kwh <= 0:
            continue

        actual = store.daily_production_for_date(
            day=target_date,
            tz=tz,
            max_gap_seconds=max_gap_seconds,
        )
        if actual["sample_count"] <= 0:
            continue

        actual_kwh = float(actual["production_kwh"])
        error_ratio = actual_kwh / predicted_kwh
        bounded_ratio = _clamp(error_ratio, 0.4, 1.6)
        correction_factor = _clamp(
            correction_factor * 0.7 + bounded_ratio * 0.3,
            0.6,
            1.4,
        )
        store.update_prediction_actual(target_date, actual_kwh, error_ratio)
        store.set_prediction_state(CORRECTION_FACTOR_KEY, round(correction_factor, 4))


def _estimate_base(history: List[Dict[str, Any]], target_date: date) -> Dict[str, Any]:
    values: List[float] = []
    seasonal_values: List[float] = []

    for item in history:
        production = _optional_float(item.get("production_kwh"))
        item_date = _date_from_iso(item.get("date"))
        if production is None or production <= 0.1 or item_date is None:
            continue
        values.append(production)
        if _circular_day_distance(item_date, target_date) <= SEASONAL_WINDOW_DAYS:
            seasonal_values.append(production)

    if len(seasonal_values) >= MIN_SEASONAL_SAMPLES:
        return {
            "base_kwh": round(_percentile(seasonal_values, 0.8), 3),
            "base_source": "seasonal_history",
            "sample_count": len(seasonal_values),
            "history_sample_count": len(values),
        }

    if values:
        return {
            "base_kwh": round(max(values), 3),
            "base_source": "max_available_history",
            "sample_count": len(values),
            "history_sample_count": len(values),
        }

    return {
        "base_kwh": None,
        "base_source": "insufficient_history",
        "sample_count": 0,
        "history_sample_count": 0,
    }


def _radiation_reference(
    history: List[Dict[str, Any]],
    target_date: date,
) -> Optional[Dict[str, Any]]:
    values: List[float] = []

    for item in history:
        forecast_date = _date_from_iso(item.get("forecast_date"))
        radiation = _optional_float(item.get("shortwave_radiation_sum_mj_m2"))
        if forecast_date is None or radiation is None or radiation <= 0:
            continue
        if forecast_date == target_date:
            continue
        if _circular_day_distance(forecast_date, target_date) <= SEASONAL_WINDOW_DAYS:
            values.append(radiation)

    if len(values) < MIN_SEASONAL_SAMPLES:
        return None

    return {
        "value": round(_percentile(values, 0.8), 3),
        "sample_count": len(values),
        "source": "seasonal_weather_history",
    }


def _confidence(
    base: Dict[str, Any],
    radiation_reference: Optional[Dict[str, Any]],
) -> str:
    sample_count = int(base.get("sample_count") or 0)
    if base.get("base_kwh") is None:
        return "insufficient_history"
    if sample_count >= 10 and radiation_reference:
        return "high"
    if sample_count >= MIN_SEASONAL_SAMPLES:
        return "medium"
    return "low"


def _weather_code_default(code: Optional[int]) -> float:
    if code in {0, 1}:
        return 0.95
    if code == 2:
        return 0.75
    if code == 3:
        return 0.55
    if code in {45, 48}:
        return 0.45
    if code in {51, 53, 55, 56, 57}:
        return 0.45
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return 0.35
    if code in {71, 73, 75, 77, 85, 86}:
        return 0.25
    if code in {95, 96, 99}:
        return 0.25
    return 0.6


def _weather_code_penalty(code: Optional[int]) -> float:
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return 0.9
    if code in {71, 73, 75, 77, 85, 86}:
        return 0.85
    if code in {95, 96, 99}:
        return 0.8
    return 1.0


def _circular_day_distance(first: date, second: date) -> int:
    first_day = int(first.strftime("%j"))
    second_day = int(second.strftime("%j"))
    distance = abs(first_day - second_day)
    return min(distance, 366 - distance)


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * _clamp(percentile, 0.0, 1.0)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = index - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def _date_from_iso(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return _clamp(numerator / denominator, 0.0, 1.0)


def _bounded_correction(value: Any) -> float:
    number = _optional_float(value)
    if number is None:
        return 1.0
    return _clamp(number, 0.6, 1.4)


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
