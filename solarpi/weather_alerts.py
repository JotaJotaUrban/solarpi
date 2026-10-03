"""Public MeteoAlarm Atom warnings for the province of Castellón."""
from __future__ import annotations

import threading
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.request import Request, urlopen

FEED_URL = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-spain"
SOURCE_URL = "https://www.aemet.es/es/eltiempo/prediccion/avisos"
ATOM = "{http://www.w3.org/2005/Atom}"
CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
LEVELS = {"Moderate": ("yellow", "Amarillo", 1), "Severe": ("orange", "Naranja", 2), "Extreme": ("red", "Rojo", 3)}
EVENTS = (
    ("thunder", "Tormentas"), ("rain", "Lluvias"),
    ("snow", "Nieve y hielo"), ("ice", "Nieve y hielo"),
    ("coastal", "Fenómenos costeros"), ("high-temperature", "Temperaturas máximas"),
    ("high temperature", "Temperaturas máximas"), ("low-temperature", "Temperaturas mínimas"),
    ("low temperature", "Temperaturas mínimas"), ("wind", "Viento"),
    ("fog", "Niebla"), ("flood", "Inundaciones"), ("fire", "Incendios forestales"),
    ("avalanche", "Aludes"),
)


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Warning date requires timezone")
    return result


def parse_alerts(body: bytes, now: datetime) -> list[dict]:
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Unsupported XML declaration")
    root = ET.fromstring(body)
    if root.tag != ATOM + "feed":
        raise ValueError("Expected a MeteoAlarm Atom feed")
    selected = {}
    withdrawn = set()
    for entry in root.findall(ATOM + "entry"):
        def cap(name):
            return (entry.findtext(CAP + name) or "").strip()
        if cap("status") != "Actual" or cap("scope") != "Public":
            continue
        message_type = cap("message_type") or cap("msgType")
        if message_type in {"Cancel", "Update"}:
            for reference in cap("references").split():
                parts = reference.split(',')
                if len(parts) >= 2:
                    withdrawn.add(parts[1])
        if message_type == "Cancel":
            withdrawn.add(cap("identifier"))
            continue
        area = cap("areaDesc")
        normalized = ''.join(c for c in unicodedata.normalize('NFKD', area.lower()) if not unicodedata.combining(c))
        if "castellon" not in normalized and "castello" not in normalized:
            continue
        onset = timestamp(cap("onset") or cap("effective"))
        expires = timestamp(cap("expires"))
        sent = timestamp(cap("sent"))
        if expires <= now or expires <= onset:
            continue
        event = cap("event")
        key = (cap("identifier"), area, onset, expires)
        level = LEVELS.get(cap("severity"))
        if level is None:
            continue
        name = next((label for needle, label in EVENTS if needle in event.lower()), event)
        alert = {
            "id": cap("identifier"), "area": area, "event": name,
            "level": level[0], "level_label": level[1], "rank": level[2],
            "onset": onset.isoformat(), "expires": expires.isoformat(),
            "sent": sent.isoformat(), "url": SOURCE_URL,
        }
        if key not in selected or sent > selected[key][0]:
            selected[key] = (sent, alert)
    alerts = [item for _, item in selected.values() if item['id'] not in withdrawn]
    # Distinct identifiers may have different thresholds for the same phenomenon.
    # Only explicit CAP references supersede another warning.
    return sorted(alerts, key=lambda item: (-item['rank'], item['onset'], item['area'], item['event']))


class WeatherAlerts:
    def __init__(self, interval: float = 300):
        self.interval = interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._alerts = []
        self._updated_at = None
        self._status = "loading"

    def start(self):
        self._thread = threading.Thread(target=self._run, name="weather-alerts", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=12)

    def refresh(self):
        try:
            request = Request(FEED_URL, headers={"User-Agent": "SolarPi/1.0", "Accept": "application/atom+xml"})
            with urlopen(request, timeout=10) as response:
                body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise ValueError("Warning feed exceeds size limit")
            now = datetime.now(timezone.utc)
            alerts = parse_alerts(body, now)
            with self._lock:
                self._alerts = alerts
                self._updated_at = now.isoformat()
                self._status = "ok"
        except Exception as exc:
            with self._lock:
                self._status = "unavailable"
            print("SolarPi weather alerts: %s" % exc)

    def snapshot(self):
        now = datetime.now(timezone.utc)
        with self._lock:
            return {
                "status": self._status, "updated_at": self._updated_at,
                "province": "Castellón", "source": "AEMET · MeteoAlarm",
                "alerts": [dict(alert, active=timestamp(alert['onset']) <= now)
                           for alert in self._alerts if timestamp(alert['expires']) > now],
            }

    def _run(self):
        while not self._stop.is_set():
            self.refresh()
            self._stop.wait(self.interval)
