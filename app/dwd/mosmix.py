"""MOSMIX_L point forecast for a single DWD station.

DWD publishes MOSMIX_L four times a day as a KMZ (a zipped KML) holding ~247
hourly steps, i.e. roughly ten days. Each meteorological element is one long
whitespace separated list of values aligned with the ``ForecastTimeSteps``.

Docs: https://opendata.dwd.de/weather/lib/MetElementDefinition.xml
"""

from __future__ import annotations

import io
import logging
import threading
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from app.config import settings
from app.dwd.client import cache, fetch_bytes
from app.models import WeatherPoint
from app.meteo import relative_humidity

logger = logging.getLogger(__name__)

BASE_URL = "https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations"

NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "dwd": "https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd",
}

#: MOSMIX element -> (field on WeatherPoint, converter to our unit)
ELEMENTS = {
    "TTT": ("temperature", lambda v: v - 273.15),  # K -> deg C
    "Td": ("dewpoint", lambda v: v - 273.15),  # K -> deg C
    "FF": ("wind_speed", lambda v: v),  # m/s
    "FX1": ("wind_gust", lambda v: v),  # m/s
    "DD": ("wind_direction", lambda v: v),  # deg
    "PPPP": ("pressure", lambda v: v / 100.0),  # Pa -> hPa
    "Neff": ("cloud_cover", lambda v: v),  # % (effective cloud cover)
    "RR1c": ("precipitation", lambda v: v),  # mm/h
    "R101": ("precipitation_prob", lambda v: v),  # %
    "Rad1h": ("solar_radiation", lambda v: v / 3.6),  # kJ/m^2 per h -> W/m^2
    "SunD1": ("sunshine_minutes", lambda v: v / 60.0),  # s -> min
    "VV": ("visibility", lambda v: v),  # m
    "ww": ("weather_code", lambda v: int(v)),  # WMO ww
}

#: Sparse daily extremes, reported only on the step they belong to.
EXTREMES = {"TX": "temp_max", "TN": "temp_min"}

#: Elapsed hours of the current local day, kept per station across runs.
#: See ``_merge_history``.
_history: Dict[str, Dict[datetime, WeatherPoint]] = {}
_history_lock = threading.Lock()


def _url(station_id: str) -> str:
    return f"{BASE_URL}/{station_id}/kml/MOSMIX_L_LATEST_{station_id}.kmz"


def day_floor(moment: datetime) -> datetime:
    """Local midnight of the day ``moment`` falls in.

    Public because ``app.service`` repairs the same day window and the two have
    to agree on where it starts.
    """
    return moment.astimezone(ZoneInfo(settings.location.timezone)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _merge_history(station_id: str, points: List[WeatherPoint]) -> List[WeatherPoint]:
    """Put back the hours of today that the newest run no longer covers.

    MOSMIX_L begins at its own issue time, so the 15 UTC run knows nothing about
    this morning: the moment it lands, today's card would shrink from a full day
    of bars to a stub, and the strip would look different every six hours for no
    reason the reader can see. Every elapsed hour we have ever served is held
    here until local midnight retires it, so the day stays a whole day.

    Memory is bounded by construction -- one local day per station.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    floor = day_floor(now)

    with _history_lock:
        store = _history.setdefault(station_id, {})
        # ``<=``, not ``<``: the hour we are in is the one most likely to be
        # dropped next. A run issued at 15:00 UTC starts at 16:00, so if 15:00
        # were only remembered once it had elapsed it would fall between the two
        # -- gone from the run and never taken into the store -- leaving a hole
        # exactly under the "now" line, and with it no now line at all.
        for point in points:
            if point.time <= now:
                store[point.time] = point
        for stamp in [s for s in store if s < floor]:
            del store[stamp]

        known = {p.time for p in points}
        recovered = [point for stamp, point in store.items() if stamp not in known]

    if not recovered:
        return points

    logger.info(
        "MOSMIX %s: restored %d elapsed hour(s) of today from earlier runs",
        station_id,
        len(recovered),
    )
    return sorted(points + recovered, key=lambda p: p.time)


def _parse_values(root: ET.Element) -> Dict[str, List[str]]:
    """Pull every ``<dwd:Forecast elementName=...>`` into a list of raw tokens."""
    out: Dict[str, List[str]] = {}
    for forecast in root.iter(f"{{{NS['dwd']}}}Forecast"):
        name = forecast.get(f"{{{NS['dwd']}}}elementName")
        value_node = forecast.find("dwd:value", NS)
        if name and value_node is not None and value_node.text:
            out[name] = value_node.text.split()
    return out


def _to_float(token: str) -> Optional[float]:
    if not token or token == "-":
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _parse_kml(content: bytes, hours: int) -> Dict:
    root = ET.fromstring(content)

    steps = [
        datetime.fromisoformat(node.text.replace("Z", "+00:00"))
        for node in root.iter(f"{{{NS['dwd']}}}TimeStep")
        if node.text
    ]
    if not steps:
        raise ValueError("MOSMIX document contains no forecast time steps")

    raw = _parse_values(root)
    issued_node = next(root.iter(f"{{{NS['dwd']}}}IssueTime"), None)
    issued = (
        datetime.fromisoformat(issued_node.text.replace("Z", "+00:00"))
        if issued_node is not None and issued_node.text
        else None
    )
    description = next(
        (n.text for n in root.iter(f"{{{NS['kml']}}}description") if n.text), None
    )

    # Keep the hours of today that have already gone by: the charts draw them
    # greyed out behind a "now" marker, so a day card stays a whole day instead
    # of shrinking to a stub by the evening. What this run itself covers depends
    # on when it was issued; ``_merge_history`` fills in the rest. The horizon
    # ahead still counts from now, not from midnight.
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    floor = day_floor(now)
    horizon = now + timedelta(hours=hours)

    points: List[WeatherPoint] = []
    extremes: Dict[str, Dict[str, float]] = {}

    for index, step in enumerate(steps):
        if step < floor or step > horizon:
            continue

        point = WeatherPoint(time=step, source="mosmix")
        for element, (field, convert) in ELEMENTS.items():
            values = raw.get(element)
            if not values or index >= len(values):
                continue
            value = _to_float(values[index])
            if value is not None:
                setattr(point, field, round(convert(value), 2))

        if point.temperature is not None and point.dewpoint is not None:
            point.humidity = relative_humidity(point.temperature, point.dewpoint)

        points.append(point)

        # TX/TN carry the day's max/min but only appear on a single step.
        day = step.date().isoformat()
        for element, key in EXTREMES.items():
            values = raw.get(element)
            if not values or index >= len(values):
                continue
            value = _to_float(values[index])
            if value is not None:
                extremes.setdefault(day, {})[key] = round(value - 273.15, 1)

    elapsed = sum(1 for p in points if p.time < now)
    logger.info(
        "MOSMIX %s: %d steps within +%dh, %d of them already elapsed (issued %s)",
        settings.dwd.station_id,
        len(points),
        hours,
        elapsed,
        issued,
    )
    return {
        "points": points,
        "issued": issued,
        "station_name": (description or "").strip() or None,
        "extremes": extremes,
    }


def fetch_forecast(station_id: Optional[str] = None, hours: Optional[int] = None) -> Dict:
    """Return ``{"points": [WeatherPoint], "issued": dt, "extremes": {...}}``."""
    station_id = station_id or settings.dwd.station_id
    hours = hours or settings.forecast_hours

    def _fetch() -> Dict:
        payload = fetch_bytes(_url(station_id), timeout=45)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n.endswith(".kml")]
            if not names:
                raise ValueError("MOSMIX KMZ contains no KML file")
            content = archive.read(names[0])
        parsed = _parse_kml(content, hours)
        parsed["points"] = _merge_history(station_id, parsed["points"])
        return parsed

    return cache.get_or_fetch(f"mosmix:{station_id}:{hours}", settings.cache.forecast, _fetch)
