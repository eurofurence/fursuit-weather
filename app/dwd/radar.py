"""Rain radar imagery from the official DWD GeoServer (maps.dwd.de).

The GeoServer exposes the national radar composite as a WMS layer. Rather than
have the browser talk to DWD directly (which breaks behind restrictive
networks and gives us no caching), the backend proxies a single GetMap request
and serves the PNG.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

from app.config import settings
from app.dwd.client import cache, get_session

logger = logging.getLogger(__name__)

WMS_URL = "https://maps.dwd.de/geoserver/dwd/wms"

#: Radar imagery updates every 5 minutes; do not hammer DWD harder than that.
RADAR_TTL = 240


def build_getmap_url(
    layer: str,
    bbox: Tuple[float, float, float, float],
    width: int,
    height: int,
) -> str:
    """WMS 1.3.0 GetMap. Note EPSG:4326 takes bbox as min_lat,min_lon,max_lat,max_lon."""
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": layer,
        "styles": "",
        "crs": "EPSG:4326",
        "bbox": ",".join(str(v) for v in bbox),
        "width": str(width),
        "height": str(height),
        "format": "image/png",
        "transparent": "true",
    }
    return f"{WMS_URL}?{urlencode(params)}"


def fetch_layer_image(
    layer: str,
    bbox: Tuple[float, float, float, float],
    width: int = 900,
    height: int = 900,
) -> bytes:
    """Fetch one WMS layer as PNG bytes, cached for RADAR_TTL seconds."""
    key = f"wms:{layer}:{bbox}:{width}x{height}"

    def _fetch() -> bytes:
        url = build_getmap_url(layer, bbox, width, height)
        response = get_session().get(url, timeout=settings.request_timeout)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type:
            # GeoServer reports errors as XML with a 200 status.
            raise ValueError(f"WMS returned {content_type}: {response.text[:200]}")
        return response.content

    return cache.get_or_fetch(key, RADAR_TTL, _fetch)


def bbox_around(
    lat: float, lon: float, span_deg: float, aspect: float = 1.0
) -> Tuple[float, float, float, float]:
    """Bbox centred on a point, ``aspect`` wide for every unit tall.

    Longitude degrees are shorter than latitude degrees at Hamburg's latitude,
    so the longitude span is widened to keep the map from looking squashed.
    ``aspect`` then stretches it further to match a wide map container, so the
    image fills the frame instead of sitting in it with margins.
    """
    lon_span = span_deg / 0.6 * aspect  # cos(53.5 deg) is roughly 0.6
    return (
        round(lat - span_deg, 4),
        round(lon - lon_span, 4),
        round(lat + span_deg, 4),
        round(lon + lon_span, 4),
    )


def radar_info(span_deg: float = 1.6) -> Dict:
    """Metadata the frontend needs to place the radar image."""
    bbox = bbox_around(settings.location.latitude, settings.location.longitude, span_deg)
    age = cache.age(f"wms:{settings.dwd.radar_layer}:{bbox}:900x900")
    return {
        "layer": settings.dwd.radar_layer,
        "bbox": {"min_lat": bbox[0], "min_lon": bbox[1], "max_lat": bbox[2], "max_lon": bbox[3]},
        "attribution": "Deutscher Wetterdienst (DWD)",
        "refresh_seconds": RADAR_TTL,
        "age_seconds": None if age is None else int(age),
    }
