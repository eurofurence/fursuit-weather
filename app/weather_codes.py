"""WMO ``ww`` significant-weather codes -> plain text and an icon.

MOSMIX and the POI reports both use the WMO code table. Only the codes DWD
actually emits for Germany are listed; anything else falls back by decade.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.i18n import normalise

# code -> (english, german, day icon, night icon)
CODES: Dict[int, Tuple[str, str, str, str]] = {
    # The new-moon and waning-crescent glyphs render as near-black discs, which
    # read as a rendering fault rather than "clear night" -- use a crescent.
    0: ("Clear sky", "Klarer Himmel", "☀️", "\U0001f319"),
    1: ("Mainly clear", "Überwiegend klar", "\U0001f324️", "\U0001f319"),
    2: ("Partly cloudy", "Teilweise bewölkt", "⛅", "☁️"),
    3: ("Overcast", "Bedeckt", "☁️", "☁️"),
    45: ("Fog", "Nebel", "\U0001f32b️", "\U0001f32b️"),
    48: ("Freezing fog", "Gefrierender Nebel", "\U0001f32b️", "\U0001f32b️"),
    51: ("Light drizzle", "Leichter Nieselregen", "\U0001f327️", "\U0001f327️"),
    53: ("Drizzle", "Nieselregen", "\U0001f327️", "\U0001f327️"),
    55: ("Heavy drizzle", "Starker Nieselregen", "\U0001f327️", "\U0001f327️"),
    56: ("Freezing drizzle", "Gefrierender Nieselregen", "\U0001f9ca", "\U0001f9ca"),
    57: ("Heavy freezing drizzle", "Starker gefrierender Nieselregen", "\U0001f9ca", "\U0001f9ca"),
    61: ("Light rain", "Leichter Regen", "\U0001f326️", "\U0001f327️"),
    63: ("Rain", "Regen", "\U0001f327️", "\U0001f327️"),
    65: ("Heavy rain", "Starkregen", "\U0001f327️", "\U0001f327️"),
    66: ("Freezing rain", "Gefrierender Regen", "\U0001f9ca", "\U0001f9ca"),
    67: ("Heavy freezing rain", "Starker gefrierender Regen", "\U0001f9ca", "\U0001f9ca"),
    71: ("Light snow", "Leichter Schneefall", "\U0001f328️", "\U0001f328️"),
    73: ("Snow", "Schneefall", "\U0001f328️", "\U0001f328️"),
    75: ("Heavy snow", "Starker Schneefall", "❄️", "❄️"),
    77: ("Snow grains", "Schneegriesel", "❄️", "❄️"),
    80: ("Light rain showers", "Leichte Regenschauer", "\U0001f326️", "\U0001f327️"),
    81: ("Rain showers", "Regenschauer", "\U0001f327️", "\U0001f327️"),
    82: ("Heavy rain showers", "Starke Regenschauer", "\U0001f327️", "\U0001f327️"),
    85: ("Snow showers", "Schneeschauer", "\U0001f328️", "\U0001f328️"),
    86: ("Heavy snow showers", "Starke Schneeschauer", "❄️", "❄️"),
    95: ("Thunderstorm", "Gewitter", "⛈️", "⛈️"),
    96: ("Thunderstorm with hail", "Gewitter mit Hagel", "⛈️", "⛈️"),
    99: ("Severe thunderstorm with hail", "Schweres Gewitter mit Hagel", "⛈️", "⛈️"),
}

_FALLBACK_BY_DECADE = {
    4: ("Fog", "Nebel", "\U0001f32b️"),
    5: ("Drizzle", "Nieselregen", "\U0001f327️"),
    6: ("Rain", "Regen", "\U0001f327️"),
    7: ("Snow", "Schneefall", "\U0001f328️"),
    8: ("Showers", "Schauer", "\U0001f327️"),
    9: ("Thunderstorm", "Gewitter", "⛈️"),
}


def describe(code: Optional[int], is_day: bool = True, lang: str = "en") -> Dict[str, Optional[str]]:
    """Return ``{"code", "text", "icon"}`` for a ww code."""
    if code is None:
        return {"code": None, "text": None, "icon": None}

    code = int(code)
    german = normalise(lang) == "de"

    if code in CODES:
        english, deutsch, day_icon, night_icon = CODES[code]
        return {
            "code": code,
            "text": deutsch if german else english,
            "icon": day_icon if is_day else night_icon,
        }

    english, deutsch, icon = _FALLBACK_BY_DECADE.get(code // 10, ("Cloudy", "Bewölkt", "☁️"))
    return {"code": code, "text": deutsch if german else english, "icon": icon}


def is_thunderstorm(code: Optional[int]) -> bool:
    return code is not None and 95 <= int(code) <= 99
