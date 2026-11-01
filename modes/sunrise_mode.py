"""Sunrise — a cartoon forest day/night cycle driven by the real sun.

Art and lighting live in the `sunrise/` package (extracted from the four-season
study in designs/sunrise_proto/).  This file is the mode wrapper: time, season,
speed, weather, and the HUD.

Config:
  orientation       "auto" | "landscape" | "portrait" (auto = tall screen)
  season            "auto" | "spring" | "summer" | "autumn" | "winter"
  speed             1.0 .. 10.0 (1 = wall clock, 10 = a 2.4 h day)
  latitude          degrees, north positive (default 40.7)
  longitude         degrees, east positive (default -74.0)
  show_clock        draw the clock / date / weather overlay
  clock_24h         true = 24-hour clock
  show_speed        show the "10x" speed badge
  weather_enabled   fetch current conditions from Open-Meteo (background thread)
  weather_units     "metric" | "imperial"
  weather_location  optional place label shown bottom-left
  weather_text      fallback line when the feed is unavailable
  refresh_sec       seconds between full scene re-renders at 10x (scaled down
                    for slower speeds; the overlay updates every frame)
"""

from __future__ import annotations

import datetime as dt
import math
import os
import sys
import time

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from sunrise.lighting import RampScene
from sunrise.portrait import PortraitScene
from sunrise.weather import WeatherFeed

TAU = math.tau


# --------------------------------------------------------------------------
# solar / calendar helpers (pure, so they are easy to test)
# --------------------------------------------------------------------------

def solar_altitude(latitude: float, longitude: float, when: dt.datetime):
    """(altitude in degrees, rising?) for a timezone-aware local datetime.

    NOAA's low-precision solar position: declination + equation of time, then
    the hour angle from local solar time.  Good to a fraction of a degree, which
    is far finer than the art can show.
    """
    if when.tzinfo is None:
        when = when.astimezone()
    n = when.timetuple().tm_yday
    decl = math.radians(23.44) * math.sin(TAU * (284 + n) / 365.0)
    b = TAU * (n - 81) / 364.0
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    offset = when.utcoffset()
    tz_hours = offset.total_seconds() / 3600.0 if offset else 0.0
    solar_time = (when.hour + when.minute / 60.0 + when.second / 3600.0
                  + (4.0 * (longitude - 15.0 * tz_hours) + eot) / 60.0)
    hour_angle = math.radians(15.0 * (solar_time - 12.0))
    lat = math.radians(latitude)
    sin_alt = (math.sin(lat) * math.sin(decl)
               + math.cos(lat) * math.cos(decl) * math.cos(hour_angle))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    return math.degrees(math.asin(sin_alt)), hour_angle < 0.0


def season_for_month(month: int, latitude: float) -> str:
    """Meteorological season for a month; flips for the southern hemisphere."""
    if latitude < 0:
        month = ((month - 1 + 6) % 12) + 1
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


# --------------------------------------------------------------------------
# mode
# --------------------------------------------------------------------------

class SunriseMode:
    def __init__(self, config: dict):
        self.season_pref = str(config.get("season", "auto")).strip().lower()
        self.speed = max(1.0, min(10.0, float(config.get("speed", 1.0))))
        self.latitude = max(-90.0, min(90.0, float(config.get("latitude", 40.7))))
        self.longitude = max(-180.0, min(180.0, float(config.get("longitude", -74.0))))

        self.orientation = str(config.get("orientation", "auto")).strip().lower()
        self.show_clock = bool(config.get("show_clock", True))
        self.clock_24h = bool(config.get("clock_24h", True))
        self.show_speed = bool(config.get("show_speed", True))

        self.weather_enabled = bool(config.get("weather_enabled", True))
        self.weather_units = ("imperial" if str(config.get("weather_units", "metric"))
                              .lower().startswith("imperial") else "metric")
        self.weather_location = str(config.get("weather_location", "")).strip()
        self.weather_text = str(config.get("weather_text", "")).strip()

        base_refresh = float(config.get("refresh_sec", 6.0))
        self.refresh_sec = max(2.0, min(30.0, base_refresh))
        # at 1x the sun moves ~0.004 deg/s, so a full re-render every few
        # seconds is pure waste; stretch the interval for slower speeds.
        self._scene_interval = max(2.0, min(90.0, self.refresh_sec * (10.0 / self.speed)))

        self.manager = None
        self.w = 0
        self.h = 0
        self.scene = None
        self.season = None
        self._portrait = False
        self._sim = dt.datetime.now().astimezone()
        self._cached = None
        self._next_scene = 0.0
        self._shade = None
        self._text_cache = {}
        self._weather_feed = None
        self._weather = None

    # ------------------------------------------------------------------
    def enter(self, manager):
        self.manager = manager
        self.w, self.h = manager.screen.get_size()
        self._build_shade()
        self.season = self._resolve_season()
        self._portrait = self._is_portrait()
        self.scene = (PortraitScene(self.season, self.w, self.h) if self._portrait
                      else RampScene(self.season))
        self._cached = None
        self._next_scene = 0.0
        self._render_scene()
        if self.weather_enabled and (abs(self.latitude) > 0.01 or abs(self.longitude) > 0.01):
            self._weather_feed = WeatherFeed(self.latitude, self.longitude,
                                             self.weather_units)
            self._weather_feed.start()

    def exit(self):
        if self._weather_feed is not None:
            self._weather_feed.stop()
            self._weather_feed = None
        self.scene = None
        self._cached = None
        self._shade = None
        self._text_cache.clear()
        self.manager = None

    def handle_event(self, event):
        pass

    # ------------------------------------------------------------------
    def update(self, dt_sec: float):
        if self.manager is None:
            return
        dt_sec = max(0.0, min(float(dt_sec), 1.0))

        if self.speed <= 1.0001:
            self._sim = dt.datetime.now().astimezone()
        else:
            self._sim += dt.timedelta(seconds=dt_sec * self.speed)

        size = self.manager.screen.get_size()
        if size != (self.w, self.h):
            self.w, self.h = size
            self._build_shade()
            want_portrait = self._is_portrait()
            needs_rebuild = (want_portrait != self._portrait
                             or (want_portrait and (self.scene.w, self.scene.h) != (self.w, self.h)))
            if needs_rebuild:
                self._portrait = want_portrait
                self.scene = (PortraitScene(self.season, self.w, self.h) if want_portrait
                              else RampScene(self.season))
            self._cached = None
            self._next_scene = 0.0

        now = time.monotonic()
        if self._cached is None or now >= self._next_scene:
            self._render_scene()
            self._next_scene = now + self._scene_interval

        if self._weather_feed is not None:
            snapshot = self._weather_feed.snapshot()
            if snapshot is not None:
                self._weather = snapshot

    def render(self, screen: pygame.Surface):
        if self._cached is None:
            return
        screen.blit(self._cached, (0, 0))
        if self.show_clock:
            self._draw_hud(screen)

    # ------------------------------------------------------------------
    def _is_portrait(self):
        if self.orientation == "portrait":
            return True
        if self.orientation == "landscape":
            return False
        return self.h > self.w * 1.20

    def _resolve_season(self):
        if self.season_pref in ("spring", "summer", "autumn", "winter"):
            return self.season_pref
        return season_for_month(self._sim.month, self.latitude)

    def _phase(self):
        alt_deg, rising = solar_altitude(self.latitude, self.longitude, self._sim)
        rad = math.radians(alt_deg)
        phase = (0.25 + rad / TAU) if rising else (0.75 - rad / TAU)
        return phase % 1.0

    def _render_scene(self):
        img, _mood = self.scene.render(self._phase())
        if img.get_size() != (self.w, self.h):
            src_w, src_h = img.get_size()
            scale = max(self.w / src_w, self.h / src_h)
            new_size = (max(1, int(src_w * scale + 0.5)), max(1, int(src_h * scale + 0.5)))
            scaled = pygame.transform.smoothscale(img, new_size)
            covered = pygame.Surface((self.w, self.h))
            covered.blit(scaled, ((self.w - new_size[0]) // 2,
                                  (self.h - new_size[1]) // 2))
            img = covered
        if self._shade is not None:
            img.blit(self._shade, (0, 0))
        self._cached = img

    def _build_shade(self):
        shade = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        top_h = max(44, int(self.h * 0.19))
        for y in range(top_h):
            a = int(46 * (1.0 - y / top_h))
            if a:
                pygame.draw.line(shade, (6, 8, 14, a), (0, y), (self.w, y))
        bot_h = max(34, int(self.h * 0.14))
        for i in range(bot_h):
            a = int(62 * (i / max(1, bot_h - 1)))
            y = self.h - bot_h + i
            if a:
                pygame.draw.line(shade, (6, 8, 14, a), (0, y), (self.w, y))
        self._shade = shade

    # ------------------------------------------------------------------
    def _draw_hud(self, screen):
        h = self.h
        w = self.w
        base = min(w, h)
        portrait = h > w * 1.15
        pad = max(12, int(base * 0.030))
        date_px = max(11, int(base * 0.040))
        clock_px = max(22, int(base * 0.112))
        small_px = max(11, int(base * 0.040))
        weather_px = max(12, int(base * 0.040))
        loc_px = max(10, int(base * 0.030))

        date_text = self._sim.strftime("%a %d %b").upper()
        if self.season:
            date_text = f"{self.season.upper()}  ·  {date_text}"
        if self.clock_24h:
            clock_text = self._sim.strftime("%H:%M")
        else:
            clock_text = self._sim.strftime("%I:%M %p").lstrip("0")

        if portrait:
            # tall frame: the clock/date stack is centred, because a left-aligned
            # date at portrait type size would collide with a centred clock.
            self._blit_text(screen, clock_text, w // 2, pad, clock_px,
                            (252, 249, 240), "midtop", bold=True)
            self._blit_text(screen, date_text, w // 2, pad + clock_px + 6, date_px,
                            (236, 232, 220), "midtop", bold=False)
            if self.show_speed:
                self._blit_text(screen, f"{self.speed:g}×", w - pad, pad,
                                small_px, (236, 232, 220), "topright", bold=False)
            weather_text = self._weather_line()
            if weather_text:
                self._blit_text(screen, weather_text, w // 2, h - pad,
                                weather_px, (242, 239, 230), "midbottom", bold=False)
            if self.weather_location:
                self._blit_text(screen, self.weather_location.upper(), pad,
                                h - pad - weather_px - 10,
                                loc_px, (226, 222, 210), "bottomleft", bold=False)
            return

        self._blit_text(screen, date_text, pad, pad, date_px,
                        (236, 232, 220), "topleft", bold=False)
        self._blit_text(screen, clock_text, w // 2, max(2, pad - 10), clock_px,
                        (252, 249, 240), "midtop", bold=True)
        if self.show_speed:
            self._blit_text(screen, f"{self.speed:g}×", w - pad, pad + 2,
                            small_px, (236, 232, 220), "topright", bold=False)

        weather_text = self._weather_line()
        if weather_text:
            self._blit_text(screen, weather_text, w // 2, h - pad, weather_px,
                            (242, 239, 230), "midbottom", bold=False)
        if self.weather_location:
            self._blit_text(screen, self.weather_location.upper(), pad, h - pad,
                            loc_px, (226, 222, 210), "bottomleft", bold=False)

    def _weather_line(self):
        data = self._weather
        if data:
            metric = data.get("units", "metric") == "metric"
            bits = [data.get("desc", "WEATHER")]
            temp = data.get("temp")
            if temp is not None:
                bits.append(f"{int(round(temp))}°{'C' if metric else 'F'}")
            wind = data.get("wind")
            if wind is not None:
                bits.append(f"WIND {int(round(wind))} {'KM/H' if metric else 'MPH'}")
            return "   ·   ".join(bits)
        return self.weather_text or "WEATHER UNAVAILABLE"

    def _blit_text(self, screen, text: str, x: int, y: int, px: int, color,
                   anchor: str = "topleft", bold: bool = False):
        key = (text, px, color, bold)
        pair = self._text_cache.get(key)
        if pair is None:
            font = self.manager.cache.get_font("dejavusans", px, bold=bold)
            surf = font.render(text, True, color)
            shadow = font.render(text, True, (8, 10, 16))
            if len(self._text_cache) > 300:
                self._text_cache.clear()
            pair = (surf, shadow)
            self._text_cache[key] = pair
        surf, shadow = pair
        rect = surf.get_rect(**{anchor: (x, y)})
        screen.blit(shadow, (rect.x + 2, rect.y + 2))
        screen.blit(surf, rect)
