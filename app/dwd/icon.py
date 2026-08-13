"""ICON-D2 model fields (cloud + rain, 2 m temperature, 10 m wind) as map images.

DWD publishes ICON-D2 as GRIB2 every three hours. We take the
``regular-lat-lon`` variants, decode them with the small reader in
``grib2.py``, crop to the area around the venue and paint them so the frontend
can drape the result straight over a map.
"""

from __future__ import annotations

import bz2
import io
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import requests
from PIL import Image, ImageDraw

from app.config import settings
from app.dwd.client import cache, field_cache, get_session
from app.dwd.grib2 import GribField, decode

logger = logging.getLogger(__name__)

BASE_URL = "https://opendata.dwd.de/weather/nwp/icon-d2/grib"

#: ICON-D2 runs every three hours and reaches +48 h.
RUN_HOURS = (0, 3, 6, 9, 12, 15, 18, 21)
MAX_STEP = 48
FIELD_TTL = 6 * 3600  # a run is valid until the next one lands
RUN_TTL = 900

Stops = Sequence[Tuple[float, int, int, int]]

#: Colour ramps as (position 0-1, R, G, B), linear in the parameter's range.
RAMPS: Dict[str, Stops] = {
    "temperature": (
        (0.00, 68, 90, 204),
        (0.25, 74, 175, 214),
        (0.45, 96, 190, 130),
        (0.60, 233, 205, 92),
        (0.78, 226, 132, 61),
        (1.00, 196, 58, 58),
    ),
    "clouds": (
        (0.00, 150, 165, 190),
        (1.00, 255, 255, 255),
    ),
    "wind": (
        (0.00, 40, 90, 120),
        (0.35, 90, 190, 190),
        (0.70, 255, 214, 51),
        (1.00, 241, 60, 163),
    ),
    #: Rain intensity, drawn on top of the cloud field.
    "rain": (
        (0.00, 90, 170, 255),
        (0.35, 60, 225, 255),
        (0.70, 255, 214, 51),
        (1.00, 241, 60, 163),
    ),
}

#: Rain rate (mm/h) at the top of the rain ramp, and the floor below which
#: drizzle is not worth drawing.
RAIN_MAX = 10.0
RAIN_MIN = 0.08

#: Ticks on the rain scale. The ramp is square-rooted, because drizzle and
#: downpour differ by orders of magnitude, so the labels cannot be evenly spaced.
RAIN_TICKS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0)

#: The step each field is drawn and read in.
#:
#: A colour a reader cannot put a number to is decoration. Painting continuous
#: ramps meant the legend could only honestly label its two ends; in steps, the
#: same list drives the image and the key beside it, and every shade on the map
#: is one the legend names. Clouds go in eighths, the way sky cover is reported.
STEPS: Dict[str, float] = {
    "clouds": 12.5,  # one okta
    "temperature": 2.0,
    "wind": 5.0,
}


@dataclass(frozen=True)
class Parameter:
    key: str
    sources: Tuple[str, ...]
    unit: str
    vmin: float
    vmax: float


PARAMETERS: Dict[str, Parameter] = {
    # Cloud cover carries the rain rate on top so one map answers "is it
    # overcast, and is anything actually falling out of it".
    "clouds": Parameter("clouds", ("clct", "prr_gsp"), "%", 0.0, 100.0),
    # Absolute scale, bounded for northern Germany rather than the globe, and
    # ending on even numbers so the 2 °C bands do too.
    "temperature": Parameter("temperature", ("t_2m",), "°C", -6.0, 36.0),
    "wind": Parameter("wind", ("u_10m", "v_10m"), "km/h", 0.0, 60.0),
}


def _run_candidates(now: Optional[datetime] = None) -> List[datetime]:
    """Recent run times, newest first."""
    now = now or datetime.now(timezone.utc)
    candidates: List[datetime] = []
    probe = now.replace(minute=0, second=0, microsecond=0)
    while len(candidates) < 5:
        if probe.hour in RUN_HOURS:
            candidates.append(probe)
        probe -= timedelta(hours=1)
    return candidates


def _filename(param: str, run: datetime, step: int) -> str:
    stamp = run.strftime("%Y%m%d%H")
    return (
        f"icon-d2_germany_regular-lat-lon_single-level_"
        f"{stamp}_{step:03d}_2d_{param}.grib2.bz2"
    )


def _url(param: str, run: datetime, step: int) -> str:
    return f"{BASE_URL}/{run:%H}/{param}/{_filename(param, run, step)}"


def latest_run() -> datetime:
    """The newest run that has actually been published."""

    def _probe() -> datetime:
        session = get_session()
        for run in _run_candidates():
            try:
                response = session.head(
                    _url("t_2m", run, 0), timeout=settings.request_timeout, allow_redirects=True
                )
            except requests.RequestException:
                continue
            if response.status_code == 200:
                logger.info("ICON-D2 latest run: %s", run.isoformat())
                return run
        raise RuntimeError("No ICON-D2 run available on opendata.dwd.de")

    return cache.get_or_fetch("icon:run", RUN_TTL, _probe)


def _fetch_field(param: str, run: datetime, step: int) -> GribField:
    def _load() -> GribField:
        response = get_session().get(_url(param, run, step), timeout=60)
        response.raise_for_status()
        return decode(bz2.decompress(response.content))

    # Bounded: 49 steps of five fields is far more than fits in the container.
    return field_cache.get_or_fetch(f"icon:{param}:{run:%Y%m%d%H}:{step}", FIELD_TTL, _load)


# --------------------------------------------------------------- rendering


def ramp_lookup(stops: Stops) -> np.ndarray:
    """Expand a ramp into a 256-entry RGB lookup table.

    Public because the pollen maps paint the same way; see ``app/dwd/pollen.py``.
    """
    positions = np.array([s[0] for s in stops])
    colors = np.array([[s[1], s[2], s[3]] for s in stops], dtype=float)
    x = np.linspace(0.0, 1.0, 256)
    return np.stack([np.interp(x, positions, colors[:, c]) for c in range(3)], axis=1).astype(
        np.uint8
    )


def crop_grid(
    values: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    bbox: Tuple[float, float, float, float],
) -> np.ndarray:
    """Cut a lat/lon grid down to (min_lat, min_lon, max_lat, max_lon), north-up.

    Split out from ``_crop`` so the pollen fields, which arrive from NetCDF
    rather than GRIB but on the same kind of regular grid, can reuse it.
    """
    min_lat, min_lon, max_lat, max_lon = bbox

    rows = np.where((lats >= min_lat) & (lats <= max_lat))[0]
    cols = np.where((lons >= min_lon) & (lons <= max_lon))[0]
    if rows.size == 0 or cols.size == 0:
        raise ValueError("Requested area lies outside the model domain")

    window = values[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
    # Rows run south to north in both GRIB and these NetCDF grids; images are
    # drawn top-down.
    return np.flipud(window)


def _crop(field: GribField, bbox: Tuple[float, float, float, float]) -> np.ndarray:
    return crop_grid(field.values, field.lats, field.lons, bbox)


def _normalise(values: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    return np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0)


def _colorise(
    values: np.ndarray,
    stops: Stops,
    vmin: float,
    vmax: float,
    step: Optional[float] = None,
) -> np.ndarray:
    # Zero the gaps before the cast: NaN -> uint8 is undefined and noisy.
    scaled = _normalise(np.nan_to_num(values, nan=vmin), vmin, vmax)
    if step:
        # Snap to the middle of the band, so the shade on the map is exactly the
        # one the legend prints against that band's numbers.
        count = _band_count(vmin, vmax, step)
        scaled = (np.floor(scaled * count).clip(0, count - 1) + 0.5) / count
    return ramp_lookup(stops)[(scaled * 255).astype(np.uint8)]


def _band_count(vmin: float, vmax: float, step: float) -> int:
    return max(1, round((vmax - vmin) / step))


def resize_field(values: np.ndarray, width: int, height: int) -> np.ndarray:
    """Smoothly resample a float field, keeping NaN as NaN."""
    filled = np.nan_to_num(values, nan=0.0).astype(np.float32)
    resized = np.asarray(
        Image.fromarray(filled, mode="F").resize((width, height), Image.BICUBIC)
    )
    mask = np.asarray(
        Image.fromarray(np.isfinite(values).astype(np.float32), mode="F").resize(
            (width, height), Image.BILINEAR
        )
    )
    return np.where(mask > 0.5, resized, np.nan)


def _draw_arrows(
    image: Image.Image,
    u: np.ndarray,
    v: np.ndarray,
    spacing: int = 54,
    color: Tuple[int, int, int, int] = (255, 255, 255, 225),
) -> None:
    """Wind direction arrows on a coarse grid, pointing downwind."""
    width, height = image.size
    ny, nx = u.shape
    cols = max(2, width // spacing)
    rows = max(2, height // spacing)

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    for row in range(rows):
        for col in range(cols):
            px = (col + 0.5) * width / cols
            py = (row + 0.5) * height / rows
            i = min(nx - 1, int(px / width * nx))
            j = min(ny - 1, int(py / height * ny))

            ue, vn = u[j, i], v[j, i]
            if not (np.isfinite(ue) and np.isfinite(vn)):
                continue
            speed = math.hypot(ue, vn)
            if speed < 0.5:  # calm: an arrow would imply a direction that is noise
                continue

            # u is eastward, v northward; screen y grows downward.
            length = min(spacing * 0.44, 9.0 + speed * 1.5)
            dx = ue / speed * length
            dy = -vn / speed * length
            x0, y0 = px - dx / 2, py - dy / 2
            x1, y1 = px + dx / 2, py + dy / 2

            draw.line([(x0, y0), (x1, y1)], fill=color, width=2)
            angle = math.atan2(dy, dx)
            for offset in (2.5, -2.5):
                draw.line(
                    [
                        (x1, y1),
                        (x1 + math.cos(angle + offset) * 6.5, y1 + math.sin(angle + offset) * 6.5),
                    ],
                    fill=color,
                    width=2,
                )

    image.alpha_composite(layer)


def _oktas(cloud: np.ndarray) -> np.ndarray:
    """Cloud cover in eighths, 0 (clear) to 8 (overcast).

    Rounded up, so that any cloud at all is at least 1/8 and only a genuinely
    clear sky is 0 -- which is the one value the map does not draw.
    """
    return np.clip(np.ceil(np.nan_to_num(cloud, nan=0.0) / STEPS["clouds"]), 0, 8)


def _render_clouds(arrays: List[np.ndarray], width: int, height: int) -> Image.Image:
    """White cloud cover in eighths, with the rain rate painted over it."""
    cloud, rain_rate = arrays[0], arrays[1] * 3600.0  # kg/m2/s -> mm/h

    # Resampled as a percentage and only then cut into eighths, for the reason
    # in _banded: a smoothed image would show half-oktas the legend never names.
    oktas = _oktas(resize_field(cloud, width, height))
    rgb = ramp_lookup(RAMPS["clouds"])[(oktas / 8.0 * 255).astype(np.uint8)]
    # Clear sky must stay transparent or the map disappears under a grey sheet.
    alpha = (oktas / 8.0 * 175).astype(np.uint8)
    image = Image.fromarray(
        np.dstack([rgb, alpha[..., None]]).astype(np.uint8), mode="RGBA"
    )

    rain = resize_field(rain_rate, width, height)
    wet = np.isfinite(rain) & (rain >= RAIN_MIN)
    if wet.any():
        # Bicubic resampling can undershoot below zero around dry edges.
        positive = np.clip(np.nan_to_num(rain), 0.0, None)
        # Square root: drizzle and downpour differ by orders of magnitude, and a
        # linear ramp would show nothing until it is already pouring.
        rain_rgb = _colorise(np.sqrt(positive), RAMPS["rain"], 0.0, math.sqrt(RAIN_MAX))
        # Fade rain in from the drizzle threshold so light rain is not a hard edge.
        strength = np.clip((positive - RAIN_MIN) / 1.2, 0.25, 1.0)
        rain_alpha = np.where(wet, strength * 245, 0).astype(np.uint8)
        image.alpha_composite(
            Image.fromarray(np.dstack([rain_rgb, rain_alpha[..., None]]).astype(np.uint8), "RGBA")
        )

    return image


def _banded(
    values: np.ndarray, key: str, opacity: int, width: int, height: int
) -> Image.Image:
    """One field painted in its own steps.

    Resampled as numbers first and coloured afterwards, never the other way
    round: smoothing the finished image would blend neighbouring bands into
    shades that appear nowhere in the legend, and painting the coarse grid
    first would leave the model's 2 km cells as visible blocks. This way the
    band edges are smooth and every pixel is still exactly one step.
    """
    parameter = PARAMETERS[key]
    smooth = resize_field(values, width, height)
    rgb = _colorise(smooth, RAMPS[key], parameter.vmin, parameter.vmax, STEPS[key])
    alpha = np.where(np.isfinite(smooth), opacity, 0).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, alpha[..., None]]).astype(np.uint8), mode="RGBA")


def _render_temperature(arrays: List[np.ndarray], width: int, height: int) -> Image.Image:
    return _banded(arrays[0] - 273.15, "temperature", 235, width, height)


def _render_wind(arrays: List[np.ndarray], width: int, height: int) -> Image.Image:
    u, v = arrays[0], arrays[1]
    speed = np.hypot(u, v) * 3.6  # m/s -> km/h

    # Keep the fill muted so the arrows stay the readable part. The isolines
    # this map used to carry are gone: with the fill itself now in 5 km/h steps
    # they marked the same boundaries twice, in white, over the arrows.
    image = _banded(speed, "wind", 170, width, height)
    _draw_arrows(image, u, v)
    return image


RENDERERS = {
    "clouds": _render_clouds,
    "temperature": _render_temperature,
    "wind": _render_wind,
}


def render(
    param_key: str,
    step: int,
    bbox: Tuple[float, float, float, float],
    width: int = 900,
) -> Dict:
    """Return ``{"png": bytes, "run": datetime, "min": float, "max": float}``."""
    parameter = PARAMETERS[param_key]
    run = latest_run()

    arrays = [_crop(_fetch_field(source, run, step), bbox) for source in parameter.sources]
    height = max(1, round(width * arrays[0].shape[0] / arrays[0].shape[1]))

    image = RENDERERS[param_key](arrays, width, height)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)

    if param_key == "temperature":
        scale = arrays[0] - 273.15
    elif param_key == "wind":
        scale = np.hypot(arrays[0], arrays[1]) * 3.6
    else:
        scale = arrays[0]

    return {
        "png": buffer.getvalue(),
        "run": run,
        "min": float(np.nanmin(scale)) if np.isfinite(scale).any() else None,
        "max": float(np.nanmax(scale)) if np.isfinite(scale).any() else None,
    }


def _hex_ramp(name: str) -> List[List]:
    return [[s[0], f"#{s[1]:02x}{s[2]:02x}{s[3]:02x}"] for s in RAMPS[name]]


#: How opaque each field is drawn, matching the renderers above. The legend
#: swatches carry it too, so a colour in the key is the colour on the map.
OPACITY: Dict[str, float] = {"clouds": 175 / 255, "temperature": 235 / 255, "wind": 170 / 255}


def _rgba(name: str, position: float, alpha: float) -> str:
    r, g, b = ramp_lookup(RAMPS[name])[int(np.clip(position, 0.0, 1.0) * 255)]
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


def _bands(key: str) -> List[Dict]:
    """The steps the field is drawn in, as the legend should print them.

    Built from the same ramp and step the renderer uses, so the key cannot drift
    away from the image the way two hand-kept lists would.
    """
    if key == "clouds":
        # Eighths, the way sky cover is reported. 0/8 is missing on purpose:
        # a clear sky is drawn as nothing at all, so there is no swatch for it.
        # Thin cloud is drawn nearly transparent, which is right on the map and
        # invisible in a key, so the faintest steps are floored to stay legible.
        return [
            {
                "from": okta * STEPS["clouds"],
                "to": (okta + 1) * STEPS["clouds"],
                "color": _rgba(
                    "clouds", (okta + 1) / 8, max(0.16, (okta + 1) / 8 * OPACITY["clouds"])
                ),
                "label": f"{okta + 1}/8",
            }
            for okta in range(8)
        ]

    parameter = PARAMETERS[key]
    step = STEPS[key]
    count = _band_count(parameter.vmin, parameter.vmax, step)
    return [
        {
            "from": round(parameter.vmin + index * step, 3),
            "to": round(parameter.vmin + (index + 1) * step, 3),
            "color": _rgba(key, (index + 0.5) / count, OPACITY[key]),
        }
        for index in range(count)
    ]


def describe_parameters(bbox: Tuple[float, float, float, float]) -> Dict:
    """Metadata for the frontend: fields, ranges, overlays and the current run."""
    try:
        run = latest_run().isoformat()
    except Exception:  # noqa: BLE001 - the card degrades to "unavailable"
        run = None

    return {
        "run": run,
        "max_step": MAX_STEP,
        "bbox": {"min_lat": bbox[0], "min_lon": bbox[1], "max_lat": bbox[2], "max_lon": bbox[3]},
        "parameters": {
            "clouds": {
                "unit": "%",
                "min": 0.0,
                "max": 100.0,
                "step": STEPS["clouds"],
                "bands": _bands("clouds"),
                "ramp": _hex_ramp("clouds"),
                "overlay": {
                    "label": "Rain",
                    "unit": "mm/h",
                    "min": RAIN_MIN,
                    "max": RAIN_MAX,
                    "ramp": _hex_ramp("rain"),
                    # The ramp is square-rooted, so the ticks carry their own
                    # positions rather than being spaced evenly.
                    "ticks": [
                        {"value": value, "at": math.sqrt(value) / math.sqrt(RAIN_MAX)}
                        for value in RAIN_TICKS
                    ],
                },
            },
            "temperature": {
                "unit": "°C",
                "min": PARAMETERS["temperature"].vmin,
                "max": PARAMETERS["temperature"].vmax,
                "step": STEPS["temperature"],
                "bands": _bands("temperature"),
                "ramp": _hex_ramp("temperature"),
            },
            "wind": {
                "unit": "km/h",
                "min": PARAMETERS["wind"].vmin,
                "max": PARAMETERS["wind"].vmax,
                "step": STEPS["wind"],
                "bands": _bands("wind"),
                "ramp": _hex_ramp("wind"),
                "arrows": True,
            },
        },
        "model": "ICON-D2 (DWD), 2 km, regular lat-lon",
    }
