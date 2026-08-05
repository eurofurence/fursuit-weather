"""Parser tests. All fixtures are inline, so the suite never touches the network."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.dwd import mosmix
from app.dwd.observations import _parse_csv
from app.dwd.warnings import _parse_feed
from app.models import WeatherPoint

# --------------------------------------------------------------------- POI

POI_HEADER = (
    "surface observations;Parameter description;"
    "dry_bulb_temperature_at_2_meter_above_ground;relative_humidity;"
    "mean_wind_speed_during last_10_min_at_10_meters_above_ground;"
    "maximum_wind_speed_last_hour;precipitation_amount_last_hour;cloud_cover_total"
)
POI_UNITS = "10147;Unit;Grad C;%;km/h;km/h;mm;%"
POI_DESC = "Datum;Uhrzeit (UTC);Temperatur;Feuchte;Wind;Boen;Niederschlag;Wolken"


def _poi(rows: list[str]) -> str:
    return "\n".join([POI_HEADER, POI_UNITS, POI_DESC, *rows])


def _newest(csv: str) -> WeatherPoint:
    """The reading ``fetch_current`` would return."""
    return _parse_csv(csv)[-1]


def test_poi_uses_the_newest_row_which_comes_first():
    """DWD publishes POI rows newest-first; reading the last row is ~24 h stale."""
    csv = _poi(
        [
            "28.07.26;20:00;19,7;81;0,0;7,0;0,0;88",  # newest
            "28.07.26;19:00;21,1;70;3,6;9,0;0,0;75",
            "27.07.26;20:00;15,7;71;11,0;29,0;0,0;0",  # 24 h old
        ]
    )
    point = _newest(csv)

    assert point.temperature == 19.7
    assert point.humidity == 81.0
    assert point.time == datetime(2026, 7, 28, 20, 0, tzinfo=timezone.utc)


def test_poi_returns_every_row_in_time_order():
    """The older rows are the only measured record of the hours behind us, so
    the elapsed part of a chart can be rebuilt from them after a restart."""
    csv = _poi(
        [
            "28.07.26;20:00;19,7;81;0,0;7,0;0,0;88",
            "28.07.26;19:00;21,1;70;3,6;9,0;0,0;75",
            "27.07.26;20:00;15,7;71;11,0;29,0;0,0;0",
        ]
    )
    points = _parse_csv(csv)

    assert [p.time.hour for p in points] == [20, 19, 20]
    assert [p.time.day for p in points] == [27, 28, 28]
    assert [p.temperature for p in points] == [15.7, 21.1, 19.7]


def test_poi_skips_rows_without_a_temperature():
    csv = _poi(
        [
            "28.07.26;21:00;---;80;1,0;2,0;0,0;90",  # published but still empty
            "28.07.26;20:00;19,7;81;0,0;7,0;0,0;88",
        ]
    )
    assert [p.temperature for p in _parse_csv(csv)] == [19.7]


def test_poi_converts_german_decimals_and_kmh_to_ms():
    point = _newest(_poi(["28.07.26;20:00;19,7;81;36,0;72,0;1,5;50"]))
    assert point.wind_speed == pytest.approx(10.0, abs=0.01)  # 36 km/h
    assert point.wind_gust == pytest.approx(20.0, abs=0.01)
    assert point.precipitation == 1.5


def test_poi_derives_dewpoint_when_absent():
    point = _newest(_poi(["28.07.26;20:00;20,0;60;5,0;8,0;0,0;20"]))
    assert point.dewpoint == pytest.approx(12.0, abs=0.6)


def test_poi_without_usable_rows_raises():
    with pytest.raises(ValueError):
        _parse_csv(_poi(["28.07.26;20:00;---;---;---;---;---;---"]))


# ----------------------------------------------------------------- warnings


def _feed(entries: dict) -> bytes:
    document = {"time": 0, "warnings": entries, "vorabInformation": {}}
    return f"warnWetter.loadWarnings({json.dumps(document)});".encode("utf-8")


HEAT_ENTRY = {
    "state": "Hamburg",
    "type": 8,
    "level": 50,
    "start": 1785315600000,
    "end": 1785344400000,
    "regionName": "Hansestadt Hamburg",
    "event": "STARKE HITZE",
    "headline": "Amtliche WARNUNG vor HITZE",
    "description": "Am Mittwoch wird eine starke Wärmebelastung erwartet.",
    "instruction": "Vermeiden Sie die Hitze, trinken Sie ausreichend Wasser.",
}


def test_warnings_decode_utf8_umlauts():
    """Decoding this UTF-8 feed as latin-1 turns "ä" into "Ã¤" on the page."""
    warnings = _parse_feed(_feed({"102000000": [HEAT_ENTRY]}), ["102000000"])

    assert len(warnings) == 1
    assert "Wärmebelastung" in warnings[0].description
    assert "Ã" not in warnings[0].description


def test_warnings_map_heat_level_50():
    warning = _parse_feed(_feed({"102000000": [HEAT_ENTRY]}), ["102000000"])[0]
    assert warning.kind == "heat"
    assert warning.severity == "moderate"
    assert warning.event_en == "Heat warning (moderate)"
    assert warning.start == datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


def test_warnings_ignore_other_warncells():
    assert _parse_feed(_feed({"103401000": [HEAT_ENTRY]}), ["102000000"]) == []


def test_warnings_sort_most_severe_first():
    thunder = {**HEAT_ENTRY, "type": 0, "level": 4, "event": "SCHWERES GEWITTER"}
    warnings = _parse_feed(_feed({"102000000": [HEAT_ENTRY, thunder]}), ["102000000"])
    assert [w.severity for w in warnings] == ["severe", "moderate"]


def test_warnings_are_not_repeated_once_per_warncell():
    """Watching several cells hands us the same warning once per cell. Left in,
    every copy claimed a row of its own on the charts and stacked the panel
    taller without saying anything the first copy had not already said."""
    feed = _feed({"102000000": [HEAT_ENTRY], "103401000": [HEAT_ENTRY]})
    warnings = _parse_feed(feed, ["102000000", "103401000"])

    assert len(warnings) == 1


def test_warnings_keep_two_spells_of_the_same_event():
    """Deduplication is on the event *and* its hours, not the event alone."""
    tomorrow = {**HEAT_ENTRY, "start": HEAT_ENTRY["start"] + 86_400_000}
    warnings = _parse_feed(_feed({"102000000": [HEAT_ENTRY, tomorrow]}), ["102000000"])

    assert len(warnings) == 2


def test_warnings_reject_a_non_jsonp_body():
    with pytest.raises(ValueError):
        _parse_feed(b"upstream is down", ["102000000"])


# ------------------------------------------------------------------- MOSMIX

KML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<kml:kml xmlns:kml="http://www.opengis.net/kml/2.2"
         xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd">
  <kml:Document>
    <kml:ExtendedData>
      <dwd:ProductDefinition>
        <dwd:IssueTime>2026-07-28T15:00:00.000Z</dwd:IssueTime>
        <dwd:ForecastTimeSteps>{steps}</dwd:ForecastTimeSteps>
      </dwd:ProductDefinition>
    </kml:ExtendedData>
    <kml:Placemark>
      <kml:description>HAMBURG-FU.</kml:description>
      <kml:ExtendedData>
        <dwd:Forecast dwd:elementName="TTT"><dwd:value>{ttt}</dwd:value></dwd:Forecast>
        <dwd:Forecast dwd:elementName="Td"><dwd:value>{td}</dwd:value></dwd:Forecast>
        <dwd:Forecast dwd:elementName="FF"><dwd:value>{ff}</dwd:value></dwd:Forecast>
        <dwd:Forecast dwd:elementName="Rad1h"><dwd:value>{rad}</dwd:value></dwd:Forecast>
        <dwd:Forecast dwd:elementName="SunD1"><dwd:value>{sun}</dwd:value></dwd:Forecast>
        <dwd:Forecast dwd:elementName="PPPP"><dwd:value>{pppp}</dwd:value></dwd:Forecast>
        <dwd:Forecast dwd:elementName="TX"><dwd:value>{tx}</dwd:value></dwd:Forecast>
      </kml:ExtendedData>
    </kml:Placemark>
  </kml:Document>
</kml:kml>
"""


def _kml(base: datetime, count: int = 3) -> bytes:
    steps = "".join(
        f"<dwd:TimeStep>{(base.replace(microsecond=0)).isoformat().replace('+00:00', '.000Z')}</dwd:TimeStep>"
        if index == 0
        else f"<dwd:TimeStep>{(base.replace(microsecond=0) + __import__('datetime').timedelta(hours=index)).isoformat().replace('+00:00', '.000Z')}</dwd:TimeStep>"
        for index in range(count)
    )
    return KML_TEMPLATE.format(
        steps=steps,
        ttt=" ".join(["293.15"] * count),  # 20 degC
        td=" ".join(["283.15"] * count),  # 10 degC
        ff=" ".join(["3.60"] * count),
        rad=" ".join(["1800.00"] * count),  # kJ/m^2 -> 500 W/m^2
        sun=" ".join(["1800.00"] * count),  # s -> 30 min
        pppp=" ".join(["102010.00"] * count),  # Pa -> 1020.1 hPa
        tx=" ".join(["-"] * (count - 1) + ["298.35"]),
    ).encode("utf-8")


def _now_utc_hour() -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def test_mosmix_converts_units():
    parsed = mosmix._parse_kml(_kml(_now_utc_hour()), hours=48)
    point = parsed["points"][0]

    assert point.temperature == pytest.approx(20.0, abs=0.01)  # K -> degC
    assert point.dewpoint == pytest.approx(10.0, abs=0.01)
    assert point.pressure == pytest.approx(1020.1, abs=0.01)  # Pa -> hPa
    assert point.solar_radiation == pytest.approx(500.0, abs=0.5)  # kJ/m^2 -> W/m^2
    assert point.sunshine_minutes == pytest.approx(30.0, abs=0.01)  # s -> min
    assert point.humidity == pytest.approx(52.5, abs=1.0)  # derived from T and Td
    assert parsed["station_name"] == "HAMBURG-FU."


def test_mosmix_drops_steps_outside_the_horizon():
    parsed = mosmix._parse_kml(_kml(_now_utc_hour(), count=10), hours=3)
    assert len(parsed["points"]) == 4  # now plus three hours


def _local_midnight() -> datetime:
    return (
        _now_utc_hour()
        .astimezone(ZoneInfo(settings.location.timezone))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )


def test_mosmix_keeps_the_hours_of_today_that_have_gone_by():
    """They are drawn greyed out behind the "now" line, so a day card stays a
    whole day instead of shrinking to a stub by the evening."""
    start = _now_utc_hour() - timedelta(hours=3)
    parsed = mosmix._parse_kml(_kml(start, count=6), hours=6)

    steps = [start + timedelta(hours=offset) for offset in range(6)]
    assert [p.time for p in parsed["points"]] == [s for s in steps if s >= _local_midnight()]


def test_mosmix_still_drops_yesterday():
    """Only today's elapsed hours are context; the rest is history."""
    parsed = mosmix._parse_kml(_kml(_now_utc_hour() - timedelta(hours=30), count=36), hours=6)

    assert parsed["points"]
    assert all(p.time >= _local_midnight() for p in parsed["points"])


def _point(when: datetime, temperature: float) -> WeatherPoint:
    return WeatherPoint(time=when, source="mosmix", temperature=temperature)


def test_mosmix_restores_todays_elapsed_hours_from_earlier_runs():
    """A run begins at its own issue time, so the afternoon one knows nothing
    about this morning. Without the archive today's card would shrink from a
    whole day of bars to a stub every time a new run landed."""
    mosmix._history.clear()
    now, floor = _now_utc_hour(), _local_midnight()
    elapsed = [now - timedelta(hours=n) for n in (3, 2, 1)]

    mosmix._merge_history("10147", [_point(t, 20.0) for t in elapsed])
    merged = mosmix._merge_history(
        "10147", [_point(now, 21.0), _point(now + timedelta(hours=1), 22.0)]
    )

    assert [p.time for p in merged] == [t for t in elapsed if t >= floor] + [
        now,
        now + timedelta(hours=1),
    ]


def test_mosmix_history_keeps_the_hour_we_are_in():
    """The hour in progress is the one most likely to fall between two runs.

    A run issued at 15:00 UTC starts at 16:00, so if 15:00 were only archived
    once it had elapsed it would be gone from the run and never taken into the
    store -- a hole exactly under the now line, and so no now line at all."""
    mosmix._history.clear()
    now = _now_utc_hour()

    mosmix._merge_history("10147", [_point(now, 20.0)])
    merged = mosmix._merge_history("10147", [_point(now + timedelta(hours=1), 21.0)])

    assert [p.time for p in merged] == [now, now + timedelta(hours=1)]


def test_mosmix_history_defers_to_the_current_run():
    """The archive fills gaps; it never overrides an hour the run still carries."""
    mosmix._history.clear()
    past = _now_utc_hour() - timedelta(hours=1)

    mosmix._merge_history("10147", [_point(past, 20.0)])
    merged = mosmix._merge_history("10147", [_point(past, 25.0)])

    assert [p.temperature for p in merged] == [25.0]


def test_mosmix_history_is_retired_at_local_midnight():
    """Only the current day is context, and the store stays bounded by it."""
    mosmix._history.clear()
    stale = _now_utc_hour() - timedelta(hours=30)

    mosmix._merge_history("10147", [_point(stale, 20.0)])
    merged = mosmix._merge_history("10147", [_point(_now_utc_hour(), 21.0)])

    assert [p.time for p in merged] == [_now_utc_hour()]
    assert not mosmix._history["10147"].keys() - {_now_utc_hour()}


def test_mosmix_history_is_kept_per_station():
    mosmix._history.clear()
    past = _now_utc_hour() - timedelta(hours=1)

    mosmix._merge_history("10147", [_point(past, 20.0)])
    merged = mosmix._merge_history("01234", [_point(_now_utc_hour(), 21.0)])

    assert [p.time for p in merged] == [_now_utc_hour()]


def test_mosmix_collects_daily_extremes():
    parsed = mosmix._parse_kml(_kml(_now_utc_hour()), hours=48)
    assert any(day.get("temp_max") == pytest.approx(25.2, abs=0.1) for day in parsed["extremes"].values())


def test_mosmix_without_timesteps_raises():
    empty = KML_TEMPLATE.format(steps="", ttt="", td="", ff="", rad="", sun="", pppp="", tx="")
    with pytest.raises(ValueError):
        mosmix._parse_kml(empty.encode("utf-8"), hours=24)


def test_mosmix_reads_the_kml_inside_a_kmz():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("MOSMIX_L_LATEST.kml", _kml(_now_utc_hour()))

    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        names = [n for n in archive.namelist() if n.endswith(".kml")]
        parsed = mosmix._parse_kml(archive.read(names[0]), hours=24)

    assert parsed["points"]


def test_thunderstorm_type_zero_is_not_lost():
    """DWD type 0 is Gewitter. Reading it with `or` turned the falsy 0 into a
    missing value, filing every thunderstorm as "other" -- which also stopped
    the thunderstorm cap in the index from firing."""
    thunder = {**HEAT_ENTRY, "type": 0, "level": 2, "event": "GEWITTER"}
    warning = _parse_feed(_feed({"102000000": [thunder]}), ["102000000"])[0]
    assert warning.kind == "thunderstorm"


def test_unknown_and_missing_types_fall_back():
    for value in (None, 999, "nonsense"):
        entry = {**HEAT_ENTRY, "type": value}
        assert _parse_feed(_feed({"102000000": [entry]}), ["102000000"])[0].kind == "other"


def test_advance_notices_are_flagged_and_labelled():
    document = {
        "warnings": {"102000000": [{**HEAT_ENTRY, "type": 8, "level": 50}]},
        "vorabInformation": {
            "102000000": [{**HEAT_ENTRY, "type": 0, "level": 1, "event": "VORABINFORMATION"}]
        },
    }
    payload = f"warnWetter.loadWarnings({json.dumps(document)});".encode("utf-8")
    warnings = _parse_feed(payload, ["102000000"])

    by_advance = {w.advance: w for w in warnings}
    assert set(by_advance) == {True, False}
    assert by_advance[True].kind == "thunderstorm"
    assert "Advance notice" in by_advance[True].event_en
    assert by_advance[False].advance is False
