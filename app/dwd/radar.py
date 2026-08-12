"""Where the rain radar is, and how big a piece of map to ask for.

The DWD GeoServer exposes the national radar composite as a WMS layer, and the
browser talks to it directly: it is a public service, it serves tiles far better
than one machine on a home uplink can, and proxying it here only put our own
bandwidth between the reader and a picture DWD was already happy to hand over.
So nothing in this module fetches an image any more -- it names the layer and
works out the box, and Leaflet does the rest.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

WMS_URL = "https://maps.dwd.de/geoserver/dwd/wms"

#: Radar imagery updates every 5 minutes; do not hammer DWD harder than that.
RADAR_TTL = 240


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
    """What the frontend needs to put the radar on its map.

    No `age_seconds` any more: it read the age of our own cached copy of the
    image, and there is no copy to be old now that the browser fetches straight
    from DWD. A number that could only ever be null is worse than no number.
    """
    bbox = bbox_around(settings.location.latitude, settings.location.longitude, span_deg)
    return {
        "layer": settings.dwd.radar_layer,
        "bbox": {"min_lat": bbox[0], "min_lon": bbox[1], "max_lat": bbox[2], "max_lon": bbox[3]},
        "attribution": "Deutscher Wetterdienst (DWD)",
        "refresh_seconds": RADAR_TTL,
    }
