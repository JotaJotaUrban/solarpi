from __future__ import annotations

import json
import mimetypes
import shutil
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone, tzinfo
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .computed_metrics import ComputedMetricsService
from .config import ROOT_DIR, Settings
from .deye import DeyeReader
from .database_backup import copy_database, validate_database
from .economics import (
    ECONOMICS_DEFAULT_START_DATE,
)
from .service import SolarPiService
from .store import SnapshotStore
from .system_health import SystemMonitor
from .weather import DEFAULT_LOCATION, WeatherClient
from .weather_alerts import WeatherAlerts


WEB_DIR = ROOT_DIR / "web"


def create_service(settings: Settings) -> SolarPiService:
    reader = DeyeReader(settings)
    store = SnapshotStore(settings.database_path)
    return SolarPiService(
        reader=reader,
        store=store,
        poll_interval_seconds=settings.poll_interval_seconds,
    )


class SolarPiHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.database_lock = threading.RLock()
        self.weather_alerts = WeatherAlerts()

    def restore_database(self, path: Path) -> None:
        # Called under database_lock: no HTTP request can retain old state.
        try:
            self.metrics.stop(wait=True)
            self.service.stop(wait=True)
            copy_database(path, self.settings.database_path)
        finally:
            # Fresh objects discard all caches and latest readings from the old DB.
            self.service = create_service(self.settings)
            self.weather = WeatherClient(
                cache_seconds=self.settings.weather_cache_seconds,
                timeout_seconds=self.settings.weather_timeout_seconds,
            )
            self.metrics = ComputedMetricsService(
                settings=self.settings, solar_service=self.service,
                store=self.service.store, weather=self.weather,
                system_monitor=self.system_monitor,
            )
            self.service.start()
            self.metrics.start()

    settings: Settings
    service: SolarPiService
    metrics: ComputedMetricsService
    system_monitor: SystemMonitor
    weather: WeatherClient


class SolarPiRequestHandler(BaseHTTPRequestHandler):
    server_version = "SolarPi/0.1"

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/api/weather-alerts":
            self._json(HTTPStatus.OK, self.server.weather_alerts.snapshot())
            return
        with self.server.database_lock:
            self._get()

    def _get(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path

        try:
            if path == "/api/backup":
                self._download_backup()
                return
            if path == "/":
                self._serve_file(WEB_DIR / "index.html")
                return

            if path.startswith("/static/"):
                self._serve_static(path)
                return

            if path == "/api/health":
                self._json(HTTPStatus.OK, self.server.service.get_health())
                return

            if path == "/api/system":
                self._system()
                return

            if path == "/api/now":
                self._latest(include_raw=False)
                return

            if path == "/api/raw":
                self._latest(include_raw=True)
                return

            if path == "/api/history":
                query = parse_qs(parsed.query)
                minutes = self._bounded_int(query, "minutes", default=60, minimum=1, maximum=60 * 24 * 30)
                limit = self._bounded_int(query, "limit", default=720, minimum=1, maximum=10000)
                self._json(
                    HTTPStatus.OK,
                    {
                        "minutes": minutes,
                        "limit": limit,
                        "points": self.server.service.store.history(minutes=minutes, limit=limit),
                    },
                )
                return

            if path == "/api/weather":
                query = parse_qs(parsed.query)
                self._weather(query)
                return

            if path == "/api/totals":
                self._totals()
                return

            if path == "/api/economics-balance":
                query = parse_qs(parsed.query)
                self._economics_balance(query)
                return

            if path == "/api/peaks":
                self._peaks()
                return

            if path == "/api/settings":
                settings = self.server.settings
                self._json(
                    HTTPStatus.OK,
                    {
                        "poll_interval_seconds": settings.poll_interval_seconds,
                        "snapshot_persist_interval_seconds": settings.poll_interval_seconds,
                        "database_path": str(settings.database_path),
                        "weather_cache_seconds": settings.weather_cache_seconds,
                        "weather_update_seconds": settings.weather_update_seconds,
                        "timezone": settings.timezone_name,
                        "totals_max_gap_seconds": settings.totals_max_gap_seconds,
                        "summary_update_seconds": settings.summary_update_seconds,
                        "system_update_seconds": settings.system_update_seconds,
                    },
                )
                return

            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
        except Exception as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _download_backup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="backup-", dir=self.server.settings.database_path.parent) as folder:
            path = Path(folder) / "solarpi.sqlite3"
            path.touch()
            copy_database(self.server.settings.database_path, path)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/vnd.sqlite3")
            self.send_header("Content-Disposition", f'attachment; filename="solarpi-{stamp}.sqlite3"')
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with path.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile, length=1024 * 1024)

    def do_POST(self) -> None:
        self.close_connection = True
        if urlsplit(self.path).path != "/api/restore":
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        if self.headers.get("X-SolarPi-Confirm") != "replace-database":
            self._json(HTTPStatus.BAD_REQUEST, {"detail": "Set X-SolarPi-Confirm: replace-database to replace ALL current data"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._json(HTTPStatus.BAD_REQUEST, {"detail": "Chunked uploads are not supported"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size <= 0 or size > 4 * 1024**3:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"detail": "Upload a SQLite file between 1 byte and 4 GiB"})
            return
        if self.headers.get_content_type() not in ("application/octet-stream", "application/vnd.sqlite3"):
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"detail": "Send the raw SQLite file, not multipart or SQL"})
            return
        with self.server.database_lock:
            try:
                self.connection.settimeout(60)
                with tempfile.TemporaryDirectory(prefix="restore-", dir=self.server.settings.database_path.parent) as folder:
                    path = Path(folder) / "uploaded.sqlite3"
                    remaining = size
                    with path.open("wb") as stream:
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("Incomplete upload; current database unchanged")
                            stream.write(chunk)
                            remaining -= len(chunk)
                    validate_database(path)
                    self.server.restore_database(path)
                self._json(HTTPStatus.OK, {"status": "ok", "detail": "Full database restored; collection resumed"})
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": str(exc)})

    def _latest(self, include_raw: bool) -> None:
        snapshot = self.server.service.get_latest()
        if snapshot is None:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "No inverter reading yet"})
            return
        self._json(HTTPStatus.OK, snapshot.to_dict(include_raw=include_raw))

    def _weather(self, query: Dict[str, Any]) -> None:
        location = str(query.get("location", [DEFAULT_LOCATION])[0]).strip().lower()
        try:
            if location == DEFAULT_LOCATION:
                payload = self.server.service.store.latest_weather_payload(DEFAULT_LOCATION)
                if payload is None:
                    self._json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"detail": "Weather not ready yet"},
                    )
                    return
                self._enrich_persisted_weather(payload)
            else:
                payload = self.server.weather.get(location)
            self._json(HTTPStatus.OK, payload)
        except ValueError:
            raise
        except Exception as exc:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": str(exc)})

    def _enrich_persisted_weather(self, payload: Dict[str, Any]) -> None:
        settings = self.server.settings
        tz = _timezone(settings.timezone_name)
        store = self.server.service.store
        today = datetime.now(tz).date()

        tomorrow = payload.get("tomorrow")
        tomorrow_date = today + timedelta(days=1)
        if isinstance(tomorrow, dict):
            tomorrow_date = _date_from_iso(tomorrow.get("date")) or tomorrow_date

        tomorrow_prediction = store.solar_prediction_for_date(tomorrow_date)
        if tomorrow_prediction:
            production_forecast = _public_prediction(tomorrow_prediction)
            payload["production_forecast"] = production_forecast
            tomorrow = payload.get("tomorrow")
            if isinstance(tomorrow, dict):
                tomorrow["production_estimate_kwh"] = production_forecast.get(
                    "estimated_kwh"
                )

        today_prediction = store.solar_prediction_for_date(today)
        totals = self.server.metrics.latest_energy_summaries() or {}
        day_totals = totals.get("day") if isinstance(totals.get("day"), dict) else {}
        expected_kwh = (
            _optional_float(today_prediction.get("predicted_kwh"))
            if today_prediction
            else None
        )
        payload["today_production"] = {
            "target_date": today.isoformat(),
            "actual_kwh": _optional_float(day_totals.get("production_kwh")),
            "expected_kwh": expected_kwh,
            "source": "day_ahead_prediction" if today_prediction else None,
        }

    def _totals(self) -> None:
        payload = self.server.metrics.latest_energy_summaries()
        if payload is None:
            payload = self.server.service.store.latest_energy_summaries()
        if payload is None:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"detail": "Energy summaries not ready yet"},
            )
            return
        self._json(HTTPStatus.OK, payload)

    def _energy_summaries_now(self, use_sampled_totals: bool = False) -> Dict[str, Any]:
        settings = self.server.settings
        tz = _timezone(settings.timezone_name)
        now = datetime.now(tz)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        year_start = day_start.replace(month=1, day=1)
        max_gap_seconds = settings.totals_max_gap_seconds
        latest = self.server.service.get_latest()
        totals_fn = (
            self.server.service.store.energy_totals_sampled
            if use_sampled_totals
            else self.server.service.store.energy_totals_fast
        )

        def totals(start: datetime) -> Dict[str, Any]:
            if use_sampled_totals:
                return totals_fn(
                    start=start,
                    end=now,
                    sample_seconds=settings.poll_interval_seconds,
                    max_gap_seconds=max_gap_seconds,
                )
            return totals_fn(
                start=start,
                end=now,
                latest=latest,
                max_gap_seconds=max_gap_seconds,
            )

        return {
            "timezone": settings.timezone_name,
            "generated_at": now.isoformat(),
            "provisional": use_sampled_totals,
            "day": totals(day_start),
            "month": totals(month_start),
            "year": totals(year_start),
        }

    def _economics_balance(self, query: Dict[str, Any]) -> None:
        settings = self.server.settings
        tz = _timezone(settings.timezone_name)
        now = datetime.now(tz)
        default_start = now.date().replace(day=1).isoformat()
        raw_start = str(query.get("start_date", [default_start])[0]).strip()
        start_day = _date_from_iso(raw_start)
        if start_day is None:
            raise ValueError("start_date must be YYYY-MM-DD")

        now = datetime.now(tz)
        start_at = datetime(
            start_day.year,
            start_day.month,
            start_day.day,
            tzinfo=tz,
        )
        if start_at > now:
            raise ValueError("start_date cannot be in the future")

        raw_end = str(query.get("end_date", [now.date().isoformat()])[0]).strip()
        end_day = _date_from_iso(raw_end)
        if end_day is None:
            raise ValueError("end_date must be YYYY-MM-DD")
        if start_day > end_day or end_day > now.date():
            raise ValueError("Expected start_date <= end_date <= today")
        self._json(HTTPStatus.OK, self.server.metrics.economics_balance(start_day, end_day))

    def _peaks(self) -> None:
        payload = self.server.metrics.latest_power_peak_summaries()
        if payload is None:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "Peaks not ready yet"})
            return
        self._json(HTTPStatus.OK, payload)

    def _system(self) -> None:
        payload = self.server.service.store.latest_system_health()
        if payload is None:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "System health not ready yet"})
            return
        self._json(HTTPStatus.OK, payload)

    def _json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        relative_path = path.removeprefix("/static/").lstrip("/")
        target = (WEB_DIR / relative_path).resolve()
        web_root = WEB_DIR.resolve()

        try:
            target.relative_to(web_root)
        except ValueError:
            self._json(HTTPStatus.FORBIDDEN, {"detail": "Forbidden"})
            return

        self._serve_file(target)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"detail": "File not found"})
            return

        body = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript"}:
            content_type = "%s; charset=utf-8" % content_type

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bounded_int(
        self,
        query: Dict[str, Any],
        key: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        values = query.get(key)
        if not values:
            return default

        value = int(values[0])
        if value < minimum or value > maximum:
            raise ValueError("%s must be between %s and %s" % (key, minimum, maximum))
        return value


def _timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo or timezone.utc


def _date_from_iso(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _public_prediction(prediction: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "target_date": prediction.get("target_date"),
        "location_key": prediction.get("location_key"),
        "estimated_kwh": prediction.get("predicted_kwh"),
        "base_kwh": prediction.get("base_kwh"),
        "base_source": prediction.get("base_source"),
        "base_sample_count": prediction.get("base_sample_count"),
        "weather_factor": prediction.get("weather_factor"),
        "correction_factor": prediction.get("correction_factor"),
        "confidence": (prediction.get("details") or {}).get("confidence"),
        "method_version": prediction.get("method_version"),
        "details": prediction.get("details") or {},
    }


def run_server(settings: Settings) -> None:
    service = create_service(settings)
    system_monitor = SystemMonitor(ROOT_DIR)
    weather = WeatherClient(
        cache_seconds=settings.weather_cache_seconds,
        timeout_seconds=settings.weather_timeout_seconds,
    )
    metrics = ComputedMetricsService(
        settings=settings,
        solar_service=service,
        store=service.store,
        weather=weather,
        system_monitor=system_monitor,
    )
    server = SolarPiHTTPServer((settings.api_host, settings.api_port), SolarPiRequestHandler)
    server.settings = settings
    server.service = service
    server.metrics = metrics
    server.system_monitor = system_monitor
    server.weather = weather

    service.start()
    metrics.start()
    server.weather_alerts.start()
    try:
        print("SolarPi listening on http://%s:%s" % (settings.api_host, settings.api_port))
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSolarPi stopped")
    finally:
        server.weather_alerts.stop()
        server.server_close()
        with server.database_lock:
            server.metrics.stop(wait=True)
            server.service.stop(wait=True)
