from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_LOCATION = "borriol"


@dataclass(frozen=True)
class WeatherLocation:
    key: str
    name: str
    latitude: float
    longitude: float


LOCATIONS: Dict[str, WeatherLocation] = {
    "borriol": WeatherLocation(
        key="borriol",
        name="Borriol",
        latitude=40.029565,
        longitude=-0.141962,
    ),
    "merida": WeatherLocation(
        key="merida",
        name="Mérida",
        latitude=38.936399,
        longitude=-6.303819,
    ),
}


def describe_weather(code: int, is_day: bool) -> Tuple[str, str]:
    daytime = "day" if is_day else "night"
    if code == 0:
        return "Despejado", "clear-%s" % daytime
    if code == 1:
        return "Mayormente despejado", "clear-%s" % daytime
    if code == 2:
        return "Parcialmente nuboso", "partly-cloudy-%s" % daytime
    if code == 3:
        return "Cubierto", "cloudy"
    if code in {45, 48}:
        return "Niebla", "fog"
    if code in {51, 53, 55, 56, 57}:
        return "Llovizna", "rain"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "Lluvia", "rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "Nieve", "snow"
    if code in {95, 96, 99}:
        return "Tormenta", "thunder"
    return "Variable", "cloudy"


def daily_value(daily: Dict[str, Any], field: str, index: int) -> Any:
    values = daily.get(field)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def summarize_daily_forecast(daily: Dict[str, Any], index: int) -> Dict[str, Any]:
    code = int(daily_value(daily, "weather_code", index) or -1)
    label, condition = describe_weather(code, True)

    return {
        "date": daily_value(daily, "time", index),
        "weather_code": code,
        "weather_label": label,
        "condition": condition,
        "temperature_min_c": daily_value(daily, "temperature_2m_min", index),
        "temperature_max_c": daily_value(daily, "temperature_2m_max", index),
        "precipitation_probability_percent": daily_value(
            daily,
            "precipitation_probability_max",
            index,
        ),
        "precipitation_sum_mm": daily_value(daily, "precipitation_sum", index),
        "rain_sum_mm": daily_value(daily, "rain_sum", index),
        "snowfall_sum_cm": daily_value(daily, "snowfall_sum", index),
        "wind_speed_max_kmh": daily_value(daily, "wind_speed_10m_max", index),
        "shortwave_radiation_sum_mj_m2": daily_value(
            daily,
            "shortwave_radiation_sum",
            index,
        ),
        "sunshine_duration_seconds": daily_value(daily, "sunshine_duration", index),
        "daylight_duration_seconds": daily_value(daily, "daylight_duration", index),
    }


class WeatherClient:
    def __init__(self, cache_seconds: float, timeout_seconds: float) -> None:
        self.cache_seconds = max(0.0, cache_seconds)
        self.timeout_seconds = max(1.0, timeout_seconds)
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, location_key: str = DEFAULT_LOCATION) -> Dict[str, Any]:
        location = self._location(location_key)
        now = time.monotonic()

        with self._lock:
            cached = self._cache.get(location.key)
            if cached and now - cached[0] <= self.cache_seconds:
                payload = dict(cached[1])
                payload["cached"] = True
                return payload

        payload = self._fetch(location)
        with self._lock:
            self._cache[location.key] = (time.monotonic(), payload)
        return dict(payload)

    def _location(self, location_key: str) -> WeatherLocation:
        key = (location_key or DEFAULT_LOCATION).strip().lower()
        if key not in LOCATIONS:
            raise ValueError("Unknown weather location: %s" % location_key)
        return LOCATIONS[key]

    def _fetch(self, location: WeatherLocation) -> Dict[str, Any]:
        query = urlencode(
            {
                "latitude": "%.6f" % location.latitude,
                "longitude": "%.6f" % location.longitude,
                "current": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "weather_code",
                        "is_day",
                        "wind_speed_10m",
                        "precipitation",
                        "rain",
                        "snowfall",
                        "cloud_cover",
                    ]
                ),
                "daily": ",".join(
                    [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                        "precipitation_sum",
                        "rain_sum",
                        "snowfall_sum",
                        "wind_speed_10m_max",
                        "shortwave_radiation_sum",
                        "sunshine_duration",
                        "daylight_duration",
                    ]
                ),
                "forecast_days": 2,
                "timezone": "Europe/Madrid",
                "wind_speed_unit": "kmh",
            }
        )
        request = Request(
            "%s?%s" % (OPEN_METEO_URL, query),
            headers={"User-Agent": "SolarPi/0.1"},
        )

        with urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))

        current = data.get("current")
        if not isinstance(current, dict):
            raise RuntimeError("Open-Meteo response did not include current weather")
        daily = data.get("daily")
        if not isinstance(daily, dict):
            raise RuntimeError("Open-Meteo response did not include daily weather")

        code = int(current.get("weather_code", -1))
        is_day = int(current.get("is_day", 0) or 0) == 1
        label, condition = describe_weather(code, is_day)

        return {
            "location": {
                "id": location.key,
                "name": location.name,
                "latitude": location.latitude,
                "longitude": location.longitude,
            },
            "timestamp": current.get("time"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "timezone": data.get("timezone"),
            "temperature_c": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "weather_code": code,
            "weather_label": label,
            "condition": condition,
            "is_day": is_day,
            "cloud_cover_percent": current.get("cloud_cover"),
            "precipitation_mm": current.get("precipitation"),
            "rain_mm": current.get("rain"),
            "snowfall_cm": current.get("snowfall"),
            "today": summarize_daily_forecast(daily, 0),
            "tomorrow": summarize_daily_forecast(daily, 1),
            "cached": False,
        }
