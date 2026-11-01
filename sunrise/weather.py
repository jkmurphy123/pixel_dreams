"""Open-Meteo current-conditions feed for the sunrise mode.

Runs on its own daemon thread; the render loop only reads `snapshot()`, never
the network.  No API key is required.  The mode falls back to its configured
text when the fetch fails or the coordinates are unset.
"""

from __future__ import annotations

import json
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# WMO weather interpretation codes used by Open-Meteo.
_WEATHER_TEXT = {
    0: "CLEAR",
    1: "MAINLY CLEAR",
    2: "PARTLY CLOUDY",
    3: "OVERCAST",
    45: "FOG",
    48: "RIME FOG",
    51: "LIGHT DRIZZLE",
    53: "DRIZZLE",
    55: "HEAVY DRIZZLE",
    56: "FREEZING DRIZZLE",
    57: "FREEZING DRIZZLE",
    61: "LIGHT RAIN",
    63: "RAIN",
    65: "HEAVY RAIN",
    66: "FREEZING RAIN",
    67: "FREEZING RAIN",
    71: "LIGHT SNOW",
    73: "SNOW",
    75: "HEAVY SNOW",
    77: "SNOW GRAINS",
    80: "LIGHT SHOWERS",
    81: "SHOWERS",
    82: "HEAVY SHOWERS",
    85: "SNOW SHOWERS",
    86: "HEAVY SNOW SHOWERS",
    95: "THUNDERSTORM",
    96: "THUNDERSTORM / HAIL",
    99: "THUNDERSTORM / HAIL",
}

_API = "https://api.open-meteo.com/v1/forecast"


class WeatherFeed:
    """A thread that keeps `current` conditions for one coordinate pair."""

    def __init__(self, latitude: float, longitude: float, units: str = "metric",
                 interval_sec: float = 900.0, timeout_sec: float = 8.0):
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.units = "imperial" if str(units).lower().startswith("imperial") else "metric"
        self.interval_sec = max(60.0, float(interval_sec))
        self.timeout_sec = max(2.0, float(timeout_sec))

        self._lock = threading.Lock()
        self._data = None          # last good snapshot
        self._error = ""
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------------
    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="sunrise-weather",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def snapshot(self):
        """Copy of the last good conditions, or None. Never blocks on the network."""
        with self._lock:
            return dict(self._data) if self._data else None

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    # ------------------------------------------------------------------
    def _run(self):
        while not self._stop.is_set():
            try:
                data = self._fetch()
            except Exception as exc:  # noqa: BLE001 - a feed failure must never kill the mode
                with self._lock:
                    self._error = f"{type(exc).__name__}: {exc}"
            else:
                with self._lock:
                    self._data = data
                    self._error = ""
            self._stop.wait(self.interval_sec)

    def _fetch(self):
        params = {
            "latitude": f"{self.latitude:.4f}",
            "longitude": f"{self.longitude:.4f}",
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
            "forecast_days": 1,
        }
        if self.units == "imperial":
            params["temperature_unit"] = "fahrenheit"
            params["wind_speed_unit"] = "mph"
        url = _API + "?" + urlencode(params)
        req = Request(url, headers={"User-Agent": "pixel_dreams-sunrise/1.0"})
        with urlopen(req, timeout=self.timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        cur = payload.get("current") or {}
        code = int(cur.get("weather_code") or 0)
        temp = cur.get("temperature_2m")
        wind = cur.get("wind_speed_10m")
        return {
            "desc": _WEATHER_TEXT.get(code, "WEATHER"),
            "code": code,
            "temp": float(temp) if temp is not None else None,
            "wind": float(wind) if wind is not None else None,
            "units": self.units,
        }
