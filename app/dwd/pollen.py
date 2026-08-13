"""ICON-ART pollen forecast for Germany, as map images.

DWD runs a +150 h pollen forecast once a day (~03:35 UTC) and publishes the
German part as daily mean concentrations in NetCDF, on a regular lat/lon grid:

    icon-art-pollen_germany_regular_lon_lat_<SPECIES>_<YYYYMMDD>00.nc

Six daily steps, 47.2-56.2 N / 5.6-15.1 E at ~6.5 km, values in grains per cubic
metre. Two things about this source shape everything below:

* **A species only exists during its own season.** Outside it DWD publishes no
  file at all, so a request for birch in August is a 404 rather than a field of
  zeroes. The seasons are published with the dataset, so the site can say "out
  of season until 30 January" instead of "unavailable".
* **DWD publishes concentrations, not severity.** The bands here are the site's
  own reading of common European aerobiological practice, they are configurable
  (``pollen.thresholds``), and DWD's own note is worth repeating: these
  forecasts are research output and are not suitable for clinical use.

Docs: https://opendata.dwd.de/climate_environment/health/forecasts/pollen/
"""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
from PIL import Image

from app.config import settings
from app.dwd.client import cache, field_cache, get_session
from app.dwd.icon import crop_grid, resize_field
from app.dwd.netcdf import Dataset

logger = logging.getLogger(__name__)

BASE_URL = "https://opendata.dwd.de/climate_environment/health/forecasts/pollen"

#: A run stays the newest one all day; the probe for which day is current is
#: cheap and rechecked far more often than that.
FILE_TTL = 6 * 3600
RUN_TTL = 900

#: Steps in a file: the forecast day plus five.
MAX_STEP = 5

#: NetCDF time is "hours since" this.
EPOCH = datetime(1900, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Species:
    key: str
    #: The NetCDF variable name, which is also the token in the file name.
    variable: str
    latin: str
    #: Season as day-of-year, inclusive, from the dataset description.
    season_start: int
    season_end: int


#: The five species DWD publishes, with the seasons from the dataset
#: description. The keys are this site's own; the variable names are DWD's.
SPECIES: Dict[str, Species] = {
    "hazel": Species("hazel", "CORY", "Corylus", 1, 146),  # 1 Jan - 26 May
    "alder": Species("alder", "ALNU", "Alnus", 1, 146),  # 1 Jan - 26 May
    "birch": Species("birch", "BETU", "Betula", 30, 161),  # 30 Jan - 10 Jun
    "grasses": Species("grasses", "POAC", "Poaceae", 60, 305),  # 1 Mar - 1 Nov
    "ragweed": Species("ragweed", "AMBR", "Ambrosia", 213, 280),  # 1 Aug - 7 Oct
}

#: Level names, lowest first. The colours are the Fursuiting Index bands, so one
#: visual language covers the whole site: green means go out, pink means do not.
LEVELS: Tuple[Tuple[str, str], ...] = (
    ("low", "#7cc243"),
    ("moderate", "#ffd633"),
    ("high", "#ff8a3d"),
    ("very_high", "#f13ca3"),
)

#: The published grid, from the dataset description: Germany only, at 0.0625
#: degrees (~6.5 km). It matters because it is *narrower than the map*. The
#: ICON-D2 domain comfortably contains the view around the venue, so those
#: fields can be cropped to whatever window is asked for; this one cannot, and a
#: field drawn over ground it does not cover would be stretched sideways across
#: the map. Hence ``map_bounds``.
DOMAIN = (47.2, 5.6, 56.2, 15.1)
GRID_STEP = 0.0625

#: Air below a tenth of the "moderate" threshold is drawn as nothing at all, the
#: way a clear sky is on the cloud map: painting it green would bury the
#: coastline under a sheet of colour on every quiet day, and "no pollen worth
#: naming" is not a reading. Proportional rather than absolute, because one
#: grain per cubic metre means something very different for ragweed than for
#: grass.
def draw_floor(key: str) -> float:
    return thresholds(key)[0] / 10.0


#: Lower bounds of moderate, high and very high, in grains/m3.
#:
#: Two different things set these, and conflating them is how the table goes
#: wrong:
#:
#: * **Where "moderate" starts** follows potency -- the concentration at which a
#:   sensitised person notices anything. Ragweed is by far the worst of the five
#:   and provokes symptoms in the single digits; the trees and grasses need
#:   something in the tens.
#: * **Where "very high" starts** follows how high that taxon's counts actually
#:   run. Birch peaks in the hundreds in a northern-German spring, so it needs
#:   headroom or the map sits pinned at the top colour for weeks; ragweed never
#:   gets near those numbers and must not be judged on them.
#:
#: Hence ragweed's whole scale sitting below every other species'. These are a
#: reading of common European aerobiological practice, not something DWD
#: publishes -- exact figures vary between national services, which is why they
#: are overridable in config.json.
#: The middle number of each row is DWD's own "hohe Belastung" edge, from the
#: Pollenflug-Gefahrenindex: hazel and alder >100, birch >50, grasses >30,
#: ragweed >10. Keeping that edge exactly where DWD puts it is what lets the
#: board raise a warning at "high" and mean the same thing the national service
#: means by it.
DEFAULT_THRESHOLDS: Dict[str, Tuple[float, float, float]] = {
    # These two bloom in their hundreds in a late-winter week, which is why
    # their scale sits so far above the others: DWD only calls hazel or alder
    # heavy past 100, and a lower edge would leave the map pinned at the top
    # colour for most of February.
    "hazel": (10.0, 100.0, 250.0),
    "alder": (10.0, 100.0, 250.0),
    # Potent, but the counts are in a league of their own: 200 to top out.
    "birch": (10.0, 50.0, 200.0),
    "grasses": (10.0, 30.0, 80.0),
    # Far lower, and deliberately so: ragweed is the most potent of the five,
    # and its "high" sits below where grass is still only moderate.
    "ragweed": (3.0, 10.0, 25.0),
}

#: The level at which pollen stops being a number on a map and becomes something
#: the board says out loud. Index 2 is "high", which is DWD's own threshold for
#: heavy exposure. Anything lower and the strip would be lit for most of a
#: northern-German summer, which is the fastest way to teach a shift to stop
#: reading it.
WARN_FROM_LEVEL = 2


def thresholds(key: str) -> Tuple[float, float, float]:
    """The three band edges for one species."""
    configured = settings.pollen.thresholds.get(key)
    if configured and len(configured) == 3:
        return tuple(sorted(float(v) for v in configured))  # type: ignore[return-value]
    return DEFAULT_THRESHOLDS[key]


def _doy(when: date) -> int:
    return when.timetuple().tm_yday


def in_season(key: str, when: Optional[date] = None) -> bool:
    """Whether DWD is publishing this species today.

    None of the five wrap across new year, so a plain range test is enough --
    but the test is written to survive one that does, rather than quietly
    reporting a winter species as permanently out of season.
    """
    species = SPECIES[key]
    day = _doy(when or datetime.now(timezone.utc).date())
    if species.season_start <= species.season_end:
        return species.season_start <= day <= species.season_end
    return day >= species.season_start or day <= species.season_end


def season_dates(key: str, year: Optional[int] = None) -> Tuple[date, date]:
    """The season as real dates in ``year``, for "out of season until ..."."""
    species = SPECIES[key]
    year = year or datetime.now(timezone.utc).year
    start = date(year, 1, 1) + timedelta(days=species.season_start - 1)
    end = date(year, 1, 1) + timedelta(days=species.season_end - 1)
    return start, end


def map_bounds(
    bbox: Tuple[float, float, float, float]
) -> Tuple[float, float, float, float]:
    """The ground a pollen map for ``bbox`` will actually cover.

    Snapped outward-in to the grid's own cell centres and clamped to the
    published domain, so the answer is exactly the window ``render`` crops. The
    frontend drapes the image on *this*, not on the window it asked for.
    """
    wanted = (max(bbox[0], DOMAIN[0]), max(bbox[1], DOMAIN[1]),
              min(bbox[2], DOMAIN[2]), min(bbox[3], DOMAIN[3]))
    if wanted[0] > wanted[2] or wanted[1] > wanted[3]:
        raise ValueError("Requested area lies outside the pollen domain")

    def low(value: float, origin: float) -> float:
        # First cell centre at or above the requested edge.
        return origin + math.ceil(round((value - origin) / GRID_STEP, 6)) * GRID_STEP

    def high(value: float, origin: float) -> float:
        return origin + math.floor(round((value - origin) / GRID_STEP, 6)) * GRID_STEP

    return (
        round(low(wanted[0], DOMAIN[0]), 6),
        round(low(wanted[1], DOMAIN[1]), 6),
        round(high(wanted[2], DOMAIN[0]), 6),
        round(high(wanted[3], DOMAIN[1]), 6),
    )


def _url(key: str, day: date) -> str:
    species = SPECIES[key]
    return (
        f"{BASE_URL}/icon-art-pollen_germany_regular_lon_lat_"
        f"{species.variable}_{day:%Y%m%d}00.nc"
    )


def latest_run(key: Optional[str] = None) -> date:
    """The forecast day currently on the server.

    All species are published in the same morning batch, so one probe answers
    for all of them -- but it has to be aimed at a species that is actually in
    season, or it would probe a file that is 404 by design and conclude the
    whole product is a day behind.
    """
    probe_key = key if key and in_season(key) else None
    if probe_key is None:
        probe_key = next((k for k in SPECIES if in_season(k)), None)
    if probe_key is None:
        raise RuntimeError("No pollen species is in season")

    def _probe() -> date:
        session = get_session()
        today = datetime.now(timezone.utc).date()
        # The run lands around 03:35 UTC, so before that the newest file is
        # yesterday's. Two days back covers a late or skipped publication; the
        # server itself only keeps about three days.
        for back in range(3):
            day = today - timedelta(days=back)
            try:
                response = session.head(
                    _url(probe_key, day),
                    timeout=settings.request_timeout,
                    allow_redirects=True,
                )
            except requests.RequestException:
                continue
            if response.status_code == 200:
                logger.info("ICON-ART pollen latest run: %s", day.isoformat())
                return day
        raise RuntimeError("No ICON-ART pollen run available on opendata.dwd.de")

    return cache.get_or_fetch(f"pollen:run:{probe_key}", RUN_TTL, _probe)


@dataclass
class Forecast:
    """One species' file: the grid, its axes and the days it covers."""

    key: str
    run: date
    times: List[datetime]
    lats: np.ndarray
    lons: np.ndarray
    dataset: Dataset

    def grid(self, step: int) -> np.ndarray:
        return self.dataset.masked(SPECIES[self.key].variable, step)


def fetch(key: str, run: Optional[date] = None) -> Forecast:
    """Download and parse one species' forecast file."""
    if key not in SPECIES:
        raise KeyError(f"Unknown pollen species {key!r}")
    if not in_season(key):
        start, end = season_dates(key)
        # LookupError, not a network error: nothing is broken, the species
        # simply has no season today, and the caller should say so.
        raise LookupError(
            f"{key} is out of season (DWD publishes it "
            f"{start:%d %b} to {end:%d %b})"
        )
    run = run or latest_run(key)

    def _load() -> Forecast:
        response = get_session().get(_url(key, run), timeout=60)
        response.raise_for_status()
        dataset = Dataset(response.content)

        variable = SPECIES[key].variable
        if variable not in dataset.variables:
            raise ValueError(f"{variable} missing from the pollen file for {key}")

        # `time` is scalar per record, so it reads back as a 0-d array.
        times = [
            EPOCH + timedelta(hours=int(dataset.read("time", step)))
            for step in range(dataset.record_count)
        ]
        logger.info(
            "ICON-ART pollen %s run %s: %d daily steps, %s to %s",
            variable,
            run.isoformat(),
            len(times),
            times[0].date().isoformat(),
            times[-1].date().isoformat(),
        )
        return Forecast(
            key=key,
            run=run,
            times=times,
            lats=dataset.read("latitude"),
            lons=dataset.read("longitude"),
            dataset=dataset,
        )

    return field_cache.get_or_fetch(f"pollen:{key}:{run:%Y%m%d}", FILE_TTL, _load)


# --------------------------------------------------------------- rendering


def level_index(key: str, value: float) -> int:
    """Which of the four levels a concentration falls in.

    Shared with the API so a number and its name can never disagree.
    """
    return int(np.searchsorted(np.asarray(thresholds(key)), value, side="right"))


def level_name(key: str, value: float) -> str:
    return LEVELS[min(level_index(key, value), len(LEVELS) - 1)][0]


def _colorise(values: np.ndarray, key: str) -> Tuple[np.ndarray, np.ndarray]:
    """Paint a field in its species' bands, returning (rgb, alpha).

    The bands are irregular -- 5, 20, 50 for ragweed against 30, 50, 150 for
    grass -- so this cuts the field at those edges instead of scaling it down a
    continuous ramp. Every pixel is then exactly one of the four colours the
    legend names, which is the same rule the ICON maps follow.
    """
    edges = np.asarray(thresholds(key))
    finite = np.isfinite(values)
    filled = np.nan_to_num(values, nan=0.0)

    index = np.searchsorted(edges, filled, side="right")
    palette = np.array(
        [[int(color[i : i + 2], 16) for i in (1, 3, 5)] for _, color in LEVELS],
        dtype=np.uint8,
    )
    rgb = palette[np.clip(index, 0, len(LEVELS) - 1)]

    # Clean air stays transparent, and the faintest band is drawn lighter than
    # the loud ones so a map of mostly-low values does not read as an alarm.
    opacity = np.array([150, 190, 215, 235], dtype=np.float32)
    alpha = np.where(finite & (filled >= draw_floor(key)), opacity[np.clip(index, 0, 3)], 0)
    return rgb, alpha.astype(np.uint8)


def render(
    key: str,
    step: int,
    bbox: Tuple[float, float, float, float],
    width: int = 720,
) -> Dict:
    """Return ``{"png", "run", "valid", "bounds", "min", "max"}``."""
    forecast = fetch(key)
    if not 0 <= step < len(forecast.times):
        raise IndexError(f"Step {step} outside 0..{len(forecast.times) - 1}")

    # Cropped to the same window ``map_bounds`` reports, so the image and the
    # rectangle the frontend hangs it on are the same ground by construction.
    bounds = map_bounds(bbox)
    values = crop_grid(forecast.grid(step), forecast.lats, forecast.lons, bounds)
    height = max(1, round(width * values.shape[0] / values.shape[1]))

    # Resampled as numbers and coloured afterwards, for the reason in
    # icon._banded: smoothing the picture would invent shades between bands.
    smooth = resize_field(values, width, height)
    rgb, alpha = _colorise(smooth, key)
    image = Image.fromarray(np.dstack([rgb, alpha[..., None]]).astype(np.uint8), mode="RGBA")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)

    return {
        "png": buffer.getvalue(),
        "run": forecast.run,
        "valid": forecast.times[step],
        "bounds": bounds,
        "min": float(np.nanmin(values)) if np.isfinite(values).any() else None,
        "max": float(np.nanmax(values)) if np.isfinite(values).any() else None,
    }


def at_point(
    lat: float, lon: float, step: int = 0, when: Optional[date] = None
) -> List[Dict]:
    """What is in the air over one spot, for every species in season.

    The maps answer "where is it bad"; this answers "is it bad here", which is
    the only form a warning can take. Nearest grid cell rather than an
    interpolation: the cells are ~6.5 km across and a pollen forecast is not
    precise enough for the difference between one and its neighbour to mean
    anything.

    Heaviest first, so a caller that only shows one shows the one that matters.
    One species failing does not lose the others -- a missing file for grasses
    should not hide a ragweed warning.
    """
    readings: List[Dict] = []
    for key in SPECIES:
        if not in_season(key, when):
            continue
        try:
            forecast = fetch(key)
            if not 0 <= step < len(forecast.times):
                continue
            row = int(np.argmin(np.abs(forecast.lats - lat)))
            column = int(np.argmin(np.abs(forecast.lons - lon)))
            value = float(forecast.grid(step)[row, column])
        except Exception as exc:  # noqa: BLE001 - one species, not the whole block
            logger.warning("Pollen reading for %s unavailable: %s", key, exc)
            continue
        if not math.isfinite(value):
            continue

        index = min(level_index(key, value), len(LEVELS) - 1)
        readings.append(
            {
                "key": key,
                "value": round(value, 1),
                "level": LEVELS[index][0],
                "level_index": index,
                "color": LEVELS[index][1],
                "warn": index >= WARN_FROM_LEVEL,
                "valid": forecast.times[step].date().isoformat(),
            }
        )

    readings.sort(key=lambda r: (-r["level_index"], -r["value"]))
    return readings


def _bands(key: str) -> List[Dict]:
    """The four levels as the legend should print them."""
    edges = thresholds(key)
    lows = (0.0, *edges)
    # The top band is open-ended; the legend needs a number to close it on, so
    # it gets one well clear of the last threshold rather than a bare infinity.
    highs = (*edges, edges[-1] * 4)
    return [
        {
            "from": round(low, 1),
            "to": round(high, 1),
            "color": name_color,
            "label": name,
            "open": index == len(LEVELS) - 1,
        }
        for index, ((name, name_color), low, high) in enumerate(zip(LEVELS, lows, highs))
    ]


def describe(
    bbox: Tuple[float, float, float, float], when: Optional[date] = None
) -> Dict:
    """Species metadata for the frontend: seasons, bands and the current run.

    Pure calendar arithmetic plus at most one HEAD request, so the model card
    can describe all five species without downloading any of them.
    """
    when = when or datetime.now(timezone.utc).date()
    available = [key for key in SPECIES if in_season(key, when)]

    run: Optional[date] = None
    if available:
        try:
            run = latest_run()
        except Exception as exc:  # noqa: BLE001 - the card degrades to "unavailable"
            logger.warning("Pollen run probe failed: %s", exc)

    species = {}
    for key, entry in SPECIES.items():
        start, end = season_dates(key, when.year)
        species[key] = {
            "variable": entry.variable,
            "latin": entry.latin,
            "in_season": key in available,
            "season": {"start": start.isoformat(), "end": end.isoformat()},
            "bands": _bands(key),
            "thresholds": list(thresholds(key)),
        }

    bounds = map_bounds(bbox)
    return {
        "unit": "1/m³",
        "run": run.isoformat() if run else None,
        # Germany only, so the pollen layer sits on its own rectangle rather
        # than the card's; see map_bounds.
        "bbox": {
            "min_lat": bounds[0],
            "min_lon": bounds[1],
            "max_lat": bounds[2],
            "max_lon": bounds[3],
        },
        "max_step": MAX_STEP,
        # Daily means, not hours: the frontend labels the steps as days and must
        # not silently reuse the ICON card's "+1 h".
        "step_hours": 24,
        "levels": [name for name, _ in LEVELS],
        "species": species,
        "model": "ICON-ART (DWD), daily mean, ~6.5 km",
    }
