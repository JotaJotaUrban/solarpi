from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .economics import (
    ECONOMICS_DEFAULT_START_DATE,
    build_economics_balance_payload,
)
from .models import InverterSnapshot
from .production_forecast import build_tomorrow_production_forecast
from .service import SolarPiService
from .store import SnapshotStore
from .system_health import SystemMonitor
from .weather import DEFAULT_LOCATION, WeatherClient


class ComputedMetricsService:
    def __init__(
        self,
        settings: Settings,
        solar_service: SolarPiService,
        store: SnapshotStore,
        weather: WeatherClient,
        system_monitor: SystemMonitor,
    ) -> None:
        self.settings = settings
        self.solar_service = solar_service
        self.store = store
        self.weather = weather
        self.system_monitor = system_monitor

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[str] = None
        self._summary_lock = threading.Lock()
        self._latest_energy_summaries: Optional[Dict[str, Any]] = None
        self._latest_power_peak_summaries: Optional[Dict[str, Any]] = None
        self._latest_economics_balances: Dict[str, Dict[str, Any]] = {}
        self._last_closed_daily_summary: Optional[date] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._load_cached_summaries()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="solarpi-computed-metrics",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def refresh_all(self) -> None:
        self.refresh_system_health()
        self.refresh_summaries()
        self.refresh_weather_and_forecast()

    def refresh_system_health(self) -> None:
        self.store.insert_system_health_snapshot(self.system_monitor.snapshot())

    def refresh_summaries(self) -> None:
        latest = self.solar_service.get_latest()
        self._ensure_closed_daily_summary()
        energy_payload = self._energy_summaries(latest)
        peak_payload = self._peak_summaries(latest)
        self.store.save_energy_summaries(energy_payload)
        with self._summary_lock:
            self._latest_energy_summaries = energy_payload
            self._latest_power_peak_summaries = peak_payload

        economics_payload = self._economics_balance(
            latest,
            ECONOMICS_DEFAULT_START_DATE,
        )
        self.store.save_economics_balance(economics_payload)
        with self._summary_lock:
            self._latest_economics_balances[
                ECONOMICS_DEFAULT_START_DATE.isoformat()
            ] = economics_payload

    def refresh_weather_and_forecast(self) -> None:
        payload = self.weather.get(DEFAULT_LOCATION)
        self.store.persist_weather_payload(payload, DEFAULT_LOCATION)
        build_tomorrow_production_forecast(
            store=self.store,
            weather_payload=payload,
            now=datetime.now(_timezone(self.settings.timezone_name)),
            tz=_timezone(self.settings.timezone_name),
            latest=self.solar_service.get_latest(),
            max_gap_seconds=self.settings.totals_max_gap_seconds,
        )

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def latest_energy_summaries(self) -> Optional[Dict[str, Any]]:
        with self._summary_lock:
            return _copy_payload(self._latest_energy_summaries)

    def latest_power_peak_summaries(self) -> Optional[Dict[str, Any]]:
        with self._summary_lock:
            return _copy_payload(self._latest_power_peak_summaries)

    def latest_economics_balance(self, start_day: date) -> Optional[Dict[str, Any]]:
        with self._summary_lock:
            return _copy_payload(
                self._latest_economics_balances.get(start_day.isoformat())
            )

    def economics_balance(self, start_day: date) -> Dict[str, Any]:
        payload = self._economics_balance(
            self.solar_service.get_latest(),
            start_day,
        )
        return payload

    def _load_cached_summaries(self) -> None:
        cached_energy = self.store.latest_energy_summaries()
        cached_economics = self.store.latest_economics_balance(
            ECONOMICS_DEFAULT_START_DATE
        )
        with self._summary_lock:
            if cached_energy is not None:
                self._latest_energy_summaries = cached_energy
            if cached_economics is not None:
                self._latest_economics_balances[
                    ECONOMICS_DEFAULT_START_DATE.isoformat()
                ] = cached_economics

    def _run(self) -> None:
        now = time.monotonic()
        latest_economics = self.latest_economics_balance(
            ECONOMICS_DEFAULT_START_DATE
        )
        summaries_are_cached = (
            self.latest_energy_summaries() is not None
            and latest_economics is not None
        )
        next_weather = 0.0
        next_summaries = (
            now + max(10.0, self.settings.summary_update_seconds)
            if summaries_are_cached
            else 0.0
        )
        next_system = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()

            if now >= next_system:
                self._safe("system", self.refresh_system_health)
                next_system = now + max(5.0, self.settings.system_update_seconds)

            if now >= next_summaries:
                self._safe("summaries", self.refresh_summaries)
                next_summaries = now + max(10.0, self.settings.summary_update_seconds)

            if now >= next_weather:
                self._safe("weather", self.refresh_weather_and_forecast)
                next_weather = now + max(60.0, self.settings.weather_update_seconds)

            wait_seconds = min(next_weather, next_summaries, next_system) - time.monotonic()
            self._stop_event.wait(max(0.2, min(5.0, wait_seconds)))

    def _safe(self, label: str, action: Any) -> None:
        try:
            action()
            self._last_error = None
        except Exception as exc:
            self._last_error = "%s: %s" % (label, exc)
            print("SolarPi computed metrics error: %s" % self._last_error)

    def _energy_summaries(
        self,
        latest: Optional[InverterSnapshot],
    ) -> Dict[str, Any]:
        settings = self.settings
        tz = _timezone(settings.timezone_name)
        now = datetime.now(tz)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        year_start = day_start.replace(month=1, day=1)
        max_gap_seconds = settings.totals_max_gap_seconds

        return {
            "timezone": settings.timezone_name,
            "generated_at": now.isoformat(),
            "day": self.store.energy_totals_fast(
                start=day_start,
                end=now,
                latest=latest,
                max_gap_seconds=max_gap_seconds,
            ),
            "month": self.store.energy_totals_daily_summarized(
                start=month_start,
                end=now,
                timezone_name=settings.timezone_name,
                tz=tz,
                latest=latest,
                max_gap_seconds=max_gap_seconds,
            ),
            "year": self.store.energy_totals_daily_summarized(
                start=year_start,
                end=now,
                timezone_name=settings.timezone_name,
                tz=tz,
                latest=latest,
                max_gap_seconds=max_gap_seconds,
            ),
        }

    def _peak_summaries(
        self,
        latest: Optional[InverterSnapshot],
    ) -> Dict[str, Any]:
        settings = self.settings
        tz = _timezone(settings.timezone_name)
        now = datetime.now(tz)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        year_start = day_start.replace(month=1, day=1)

        return {
            "timezone": settings.timezone_name,
            "generated_at": now.isoformat(),
            "day": self.store.power_peaks(
                start=day_start,
                end=now,
                latest=latest,
            ),
            "month": self.store.power_peaks(
                start=month_start,
                end=now,
                latest=latest,
            ),
            "year": self.store.power_peaks(
                start=year_start,
                end=now,
                latest=latest,
            ),
        }

    def _ensure_closed_daily_summary(self) -> None:
        tz = _timezone(self.settings.timezone_name)
        today = datetime.now(tz).date()
        target_day = today - timedelta(days=1)
        if target_day == self._last_closed_daily_summary:
            return
        self.store.ensure_daily_energy_summary(
            target_day=target_day,
            timezone_name=self.settings.timezone_name,
            tz=tz,
            max_gap_seconds=self.settings.totals_max_gap_seconds,
        )
        self._last_closed_daily_summary = target_day

    def _economics_balance(
        self,
        latest: Optional[InverterSnapshot],
        start_day: date,
    ) -> Dict[str, Any]:
        return build_economics_balance_payload(
            settings=self.settings,
            store=self.store,
            start_day=start_day,
            now=datetime.now(_timezone(self.settings.timezone_name)),
            latest=latest,
        )


def _timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo or timezone.utc


def _copy_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if payload is None:
        return None
    copied: Dict[str, Any] = {}
    for key, value in payload.items():
        copied[key] = dict(value) if isinstance(value, dict) else value
    return copied
