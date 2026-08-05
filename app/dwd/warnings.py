"""Official DWD warnings for the configured Warncells.

The WarnWetter feed is a JSONP document (``warnWetter.loadWarnings({...});``)
encoded in ISO-8859-1. It is keyed by Warncell id -- 102000000 is
"Hansestadt Hamburg". Two buckets exist: ``warnings`` (in force) and
``vorabInformation`` (advance notice of possible severe weather).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.dwd.client import cache, fetch_bytes
from app.i18n import t
from app.models import Warning

logger = logging.getLogger(__name__)

FEED_URL = "https://www.dwd.de/DWD/warnungen/warnapp/json/warnings.json"

#: DWD warning type code -> our coarse kind, used by the FSI caps and the icons.
TYPES = {
    0: "thunderstorm",
    1: "wind",
    2: "rain",
    3: "snow",
    4: "fog",
    5: "frost",
    6: "ice",
    7: "thaw",
    8: "heat",
    9: "uv",
    10: "ice_rain",
    11: "ground_frost",
    22: "ground_frost",
    24: "coast",
    40: "thunderstorm",
    41: "thunderstorm",
    44: "wind",
    45: "wind",
    46: "thunderstorm",
    48: "thunderstorm",
    54: "ice",
    55: "snow",
    56: "snow",
    57: "ice_rain",
    58: "rain",
    59: "fog",
    61: "rain",
    62: "rain",
    63: "wind",
    64: "wind",
    65: "wind",
    66: "wind",
}

#: DWD level -> (severity, colour). 1-5 is the standard weather scale;
#: 50/51 are the separate heat-health warnings.
LEVELS = {
    1: ("minor", "#ffeb3b"),  # Vorabinformation
    2: ("minor", "#ffeb3b"),  # Wetterwarnung (yellow)
    3: ("moderate", "#fb8c00"),  # Markantes Wetter (orange)
    4: ("severe", "#e53935"),  # Unwetterwarnung (red)
    5: ("extreme", "#8e24aa"),  # Extremes Unwetter (violet)
    10: ("minor", "#ffeb3b"),
    50: ("moderate", "#fb8c00"),  # Starke Waermebelastung
    51: ("severe", "#e53935"),  # Extreme Waermebelastung
}


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _kind_of(entry: Dict[str, Any]) -> str:
    """Map DWD's numeric type to our coarse kind.

    Type 0 is thunderstorm, so this must not use ``or`` for the default: zero is
    falsy, and treating it as "missing" filed every thunderstorm under "other" --
    which also stopped the thunderstorm cap in the index from ever firing.
    """
    raw = entry.get("type")
    if raw is None:
        return "other"
    try:
        return TYPES.get(int(raw), "other")
    except (TypeError, ValueError):
        return "other"


def _normalise(entry: Dict[str, Any], advance_notice: bool = False, lang: str = "en") -> Warning:
    raw_level = entry.get("level")
    level = int(raw_level) if raw_level is not None else 1
    severity, color = LEVELS.get(level, ("minor", "#ffeb3b"))
    kind = _kind_of(entry)

    kind_label = t(lang, f"kind.{kind}")
    label = (
        t(lang, "warning.advance", kind=kind_label)
        if advance_notice
        else t(lang, "warning.label", kind=kind_label, severity=t(lang, f"severity.{severity}"))
    )

    return Warning(
        event=(entry.get("event") or "").strip().title() or kind_label,
        event_en=label,
        headline=(entry.get("headline") or "").strip(),
        description=" ".join((entry.get("description") or "").split()),
        instruction=" ".join((entry.get("instruction") or "").split()),
        severity=severity,
        advance=advance_notice,
        level=level,
        kind=kind,
        region=(entry.get("regionName") or entry.get("state") or "").strip(),
        start=_parse_time(entry.get("start")),
        end=_parse_time(entry.get("end")),
        color=color,
    )


def _decode(payload: bytes) -> str:
    """The feed is UTF-8; older DWD deployments served ISO-8859-1."""
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("WarnWetter payload is not UTF-8, falling back to ISO-8859-1")
        return payload.decode("iso-8859-1")


def _parse_feed(payload: bytes, warncells: List[str], lang: str = "en") -> List[Warning]:
    text = _decode(payload)
    start, end = text.find("("), text.rfind(")")
    if start == -1 or end == -1:
        raise ValueError("Unexpected WarnWetter payload (no JSONP wrapper)")
    document = json.loads(text[start + 1 : end])

    collected: List[Warning] = []
    seen: set = set()
    for bucket, advance in (("warnings", False), ("vorabInformation", True)):
        cells = document.get(bucket) or {}
        for cell in warncells:
            for entry in cells.get(cell, []):
                warning = _normalise(entry, advance_notice=advance, lang=lang)
                # Watching several Warncells hands us the same warning once per
                # cell. Left in, every copy claimed a row of its own on the
                # charts and stacked the panel taller without saying anything new.
                key = (warning.event, warning.level, advance, warning.start, warning.end)
                if key in seen:
                    continue
                seen.add(key)
                collected.append(warning)

    order = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3}
    collected.sort(key=lambda w: (order.get(w.severity, 9), w.start or datetime.max.replace(tzinfo=timezone.utc)))

    logger.info("Warnings for %s: %d active", ",".join(warncells), len(collected))
    return collected


def fetch_warnings(warncells: Optional[List[str]] = None, lang: str = "en") -> List[Warning]:
    warncells = warncells or settings.dwd.warncells

    def _fetch() -> List[Warning]:
        return _parse_feed(fetch_bytes(FEED_URL), warncells, lang)

    # Cache per language: the payload is shared but the labels are not.
    return cache.get_or_fetch(
        f"warnings:{','.join(warncells)}:{lang}", settings.cache.warnings, _fetch
    )
