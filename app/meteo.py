"""Meteorological helper formulas shared by the parsers and the FSI engine."""

from __future__ import annotations

import math
from typing import Optional


def saturation_vapor_pressure(temp_c: float) -> float:
    """Magnus/Tetens saturation vapour pressure in hPa."""
    return 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))


def relative_humidity(temp_c: float, dewpoint_c: float) -> float:
    """Relative humidity in % from temperature and dew point."""
    ratio = saturation_vapor_pressure(dewpoint_c) / saturation_vapor_pressure(temp_c)
    return round(max(0.0, min(100.0, ratio * 100.0)), 1)


def dewpoint(temp_c: float, humidity_percent: float) -> float:
    """Dew point in deg C from temperature and relative humidity (Magnus)."""
    humidity_percent = max(1.0, min(100.0, humidity_percent))
    a, b = 17.27, 237.7
    alpha = (a * temp_c) / (b + temp_c) + math.log(humidity_percent / 100.0)
    return round((b * alpha) / (a - alpha), 1)


def wetbulb(temp_c: float, humidity_percent: float) -> float:
    """Wet-bulb temperature in deg C via the Stull (2011) approximation.

    Valid for roughly -20..50 deg C and 5..99 % RH, which comfortably covers a
    Hamburg late-summer convention.
    """
    humidity_percent = max(1.0, min(100.0, humidity_percent))
    t, rh = temp_c, humidity_percent
    value = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh**1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return round(value, 1)


def apparent_solar_load(
    cloud_cover: Optional[float],
    solar_radiation: Optional[float],
    hour: int,
) -> float:
    """Extra perceived warmth (deg C) inside a fursuit from direct sun.

    Preference order: measured/forecast global radiation, then cloud cover
    scaled by time of day. A dark suit in full sun heats up far more than the
    shade temperature suggests, which is exactly what the index must capture.
    """
    if solar_radiation is not None and solar_radiation > 0:
        # ~800 W/m^2 is a clear summer noon in Hamburg; cap the bonus at 5 K.
        return round(min(5.0, 5.0 * (solar_radiation / 800.0)), 2)

    if 11 <= hour <= 13:
        base = 4.0
    elif 10 <= hour <= 14:
        base = 3.0
    elif 9 <= hour <= 15:
        base = 2.0
    else:
        return 0.0

    clear_fraction = 1.0 if cloud_cover is None else max(0.0, 1.0 - cloud_cover / 100.0)
    return round(base * clear_fraction, 2)


def beaufort(wind_speed_ms: Optional[float]) -> Optional[int]:
    """Beaufort force from wind speed in m/s."""
    if wind_speed_ms is None:
        return None
    limits = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
    for force, limit in enumerate(limits):
        if wind_speed_ms < limit:
            return force
    return 12


def wind_direction_name(degrees: Optional[float]) -> Optional[str]:
    if degrees is None:
        return None
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int((degrees % 360) / 45.0 + 0.5) % 8]
