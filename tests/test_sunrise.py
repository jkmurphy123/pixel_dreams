"""Sunrise mode: solar position, season mapping, and a headless render smoke test."""

from __future__ import annotations

import datetime as dt
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                                              # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.cache import ResourceCache                                       # noqa: E402
from modes.sunrise_mode import (SunriseMode, season_for_month,            # noqa: E402
                                solar_altitude, sun_times)

pygame.init()
pygame.font.init()


def test_solar_altitude_equator_equinox():
    when = dt.datetime(2026, 3, 20, 12, 0, tzinfo=dt.timezone.utc)
    noon, _ = solar_altitude(0.0, 0.0, when)
    assert noon > 85.0

    dawn, rising = solar_altitude(0.0, 0.0, when.replace(hour=6))
    assert -6.0 < dawn < 3.0
    assert rising is True

    dusk, rising = solar_altitude(0.0, 0.0, when.replace(hour=18))
    assert -6.0 < dusk < 3.0
    assert rising is False


def test_sun_times_for_nyc_in_november():
    tz = dt.timezone(dt.timedelta(hours=-5))
    rise, setting = sun_times(40.7, -74.0, dt.date(2026, 11, 1), tz)
    assert rise is not None and setting is not None
    rise_minutes = rise.hour * 60 + rise.minute
    set_minutes = setting.hour * 60 + setting.minute
    assert abs(rise_minutes - (6 * 60 + 29)) <= 8
    assert abs(set_minutes - (16 * 60 + 49)) <= 8


def test_season_for_month_includes_southern_hemisphere():
    assert season_for_month(1, 40.0) == "winter"
    assert season_for_month(4, 40.0) == "spring"
    assert season_for_month(7, 40.0) == "summer"
    assert season_for_month(10, 40.0) == "autumn"
    assert season_for_month(1, -30.0) == "summer"
    assert season_for_month(7, -30.0) == "winter"


class _Manager:
    def __init__(self, size=(1280, 400)):
        self.screen = pygame.Surface(size)
        self.cache = ResourceCache()
        self.width, self.height = size


def test_mode_renders_headless_without_network():
    manager = _Manager()
    mode = SunriseMode({"season": "autumn", "speed": 10,
                        "weather_enabled": False, "refresh_sec": 10})
    try:
        mode.enter(manager)
        assert mode.season == "autumn"
        assert mode.scene is not None

        mode._sim = dt.datetime(2026, 10, 31, 6, 30,
                                tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        mode._render_scene()
        mode.render(manager.screen)

        assert manager.screen.get_size() == (1280, 400)
        assert mode._cached is not None
        assert mode._weather_line() == "WEATHER UNAVAILABLE"
    finally:
        mode.exit()


def test_mode_renders_portrait_headless():
    manager = _Manager((1080, 1920))
    mode = SunriseMode({"season": "autumn", "speed": 10, "orientation": "portrait",
                        "weather_enabled": False, "refresh_sec": 10})
    try:
        mode.enter(manager)
        assert mode._portrait is True
        assert mode._cached.get_size() == (1080, 1920)

        mode._sim = dt.datetime(2026, 10, 31, 7, 35,
                                tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        mode._render_scene()
        mode.render(manager.screen)
        assert manager.screen.get_size() == (1080, 1920)
        assert mode._cached.get_size() == (1080, 1920)
    finally:
        mode.exit()
