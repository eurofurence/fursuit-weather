"""Current surface observations from the DWD POI (point of interest) reports.

The CSV is semicolon separated, uses German decimal commas and ``---`` for
missing values, and carries three header rows:

    row 0  parameter names ("cloud_cover_total", ...)
    row 1  station id + units
    row 2  German descriptions
    row 3+ one row per hour in REVERSE chronological order -- row 3 is the
           newest reading and the last line is ~24 h old

Columns 0 and 1 of the data rows are date (DD.MM.YY) and time (UTC).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.dwd.client import cache, fetch_bytes
from app.meteo import dewpoint as calc_dewpoint
from app.models import WeatherPoint

logger = logging.getLogger(__name__)

BASE_URL = "https://opendata.dwd.de/weather/weather_reports/poi"

#: POI parameter name -> (WeatherPoint field, converter)
FIELDS = {
    "dry_bulb_temperature_at_2_meter_above_ground": ("temperature", lambda v: v),
    "dew_point_temperature_at_2_meter_above_ground": ("dewpoint", lambda v: v),
    "relative_humidity": ("humidity", lambda v: v),
    "mean_wind_speed_during last_10_min_at_10_meters_above_ground": (
        "wind_speed",
        lambda v: v / 3.6,  # km/h -> m/s
    ),
    "maximum_wind_speed_last_hour": ("wind_gust", lambda v: v / 3.6),
    "mean_wind_direction_during_last_10 min_at_10_meters_above_ground": (
        "wind_direction",
        lambda v: v,
    ),
    "pressure_reduced_to_mean_sea_level": ("pressure", lambda v: v),
    "cloud_cover_total": ("cloud_cover", lambda v: v),
    "precipitation_amount_last_hour": ("precipitation", lambda v: v),
    "precipitation_amount_last_24_hours": ("precipitation_24h", lambda v: v),
    "global_radiation_last_hour": ("solar_radiation", lambda v: v),
    "total_time_of_sunshine_during_last_hour": ("sunshine_minutes", lambda v: v),
    "horizontal_visibility": ("visibility", lambda v: v * 1000.0),  # km -> m
    "present_weather": ("weather_code", lambda v: int(v)),
}


def _url(station_id: str) -> str:
    return f"{BASE_URL}/{station_id}-BEOB.csv"


def _to_float(token: str) -> Optional[float]:
    token = token.strip()
    if not token or token in {"---", "-"}:
        return None
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def _parse_timestamp(date_token: str, time_token: str) -> datetime:
    """POI timestamps are ``DD.MM.YY`` / ``HH:MM`` in UTC."""
    stamp = datetime.strptime(f"{date_token.strip()} {time_token.strip()}", "%d.%m.%y %H:%M")
    return stamp.replace(tzinfo=timezone.utc)


def _parse_csv(text: str) -> List[WeatherPoint]:
    """Every usable row of the report, oldest first.

    The whole file is parsed rather than just the newest row: those ~24 hourly
    rows are the only *measured* record of the hours that have already gone by,
    and ``service`` uses them to repair a forecast that no longer reaches back
    to this morning. See ``fetch_recent``.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        raise ValueError("POI report has no data rows")

    header = [h.strip() for h in lines[0].split(";")]

    points: List[WeatherPoint] = []
    for line in lines[3:]:
        cells = line.split(";")
        if len(cells) < len(header) - 2:
            continue

        values: Dict[str, Optional[float]] = {}
        for index, name in enumerate(header):
            if index < 2 or index >= len(cells):
                continue
            values[name] = _to_float(cells[index])

        # A row without a temperature is not an observation worth having -- the
        # newest one is occasionally published with the slower-reporting fields
        # still empty, and older rows can be short too.
        if values.get("dry_bulb_temperature_at_2_meter_above_ground") is None:
            continue

        point = WeatherPoint(time=_parse_timestamp(cells[0], cells[1]), source="poi")
        for name, (field, convert) in FIELDS.items():
            value = values.get(name)
            if value is not None:
                setattr(point, field, round(convert(value), 2))

        if point.dewpoint is None and point.temperature is not None and point.humidity:
            point.dewpoint = calc_dewpoint(point.temperature, point.humidity)

        points.append(point)

    if not points:
        raise ValueError("POI report contains no usable observation")

    # The file runs newest first; everything downstream reads forwards in time.
    points.sort(key=lambda p: p.time)
    return points


def _fetch_report(station_id: str) -> List[WeatherPoint]:
    """The parsed report, cached once for both readers of it."""

    def _fetch() -> List[WeatherPoint]:
        payload = fetch_bytes(_url(station_id))
        points = _parse_csv(payload.decode("utf-8", errors="replace"))
        newest = points[-1]
        logger.info(
            "POI %s: %d hourly rows, newest %s at %.1f degC, %s%% RH",
            station_id,
            len(points),
            newest.time.isoformat(),
            newest.temperature or float("nan"),
            newest.humidity,
        )
        return points

    return cache.get_or_fetch(f"poi:{station_id}", settings.cache.observations, _fetch)


def fetch_current(station_id: Optional[str] = None) -> WeatherPoint:
    """The most recent usable reading."""
    return _fetch_report(station_id or settings.dwd.station_id)[-1]


def fetch_recent(station_id: Optional[str] = None) -> List[WeatherPoint]:
    """The last ~24 h of hourly readings, oldest first.

    Same cache entry and same request as ``fetch_current``: asking for the
    history costs nothing extra once the report has been fetched.
    """
    return list(_fetch_report(station_id or settings.dwd.station_id))
