"""NetCDF reader and pollen layer. Fixtures are built inline, so no network."""

from __future__ import annotations

import struct
from datetime import date

import numpy as np
import pytest

from app.dwd import pollen
from app.dwd.netcdf import Dataset

# ------------------------------------------------------------- a tiny file


def _name(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack(">I", len(raw)) + raw + b"\x00" * (-len(raw) % 4)


def _pad(raw: bytes) -> bytes:
    return raw + b"\x00" * (-len(raw) % 4)


def _netcdf(
    records: int = 3,
    lats: tuple = (50.0, 50.5),
    lons: tuple = (7.0, 7.5, 8.0),
    variable: str = "POAC",
    fill: float = -32767.0,
    with_time: bool = True,
) -> bytes:
    """A NetCDF-3 64-bit-offset file shaped like the DWD pollen product.

    Written by hand rather than with a library for the same reason the reader is:
    the format is a fixed layout, and a fixture that needs netCDF4 installed to
    build would defeat the point of not depending on it.
    """
    dims = [("time", 0), ("latitude", len(lats)), ("longitude", len(lons))]
    cells = len(lats) * len(lons)

    #: (name, dim ids, nc_type, attributes, vsize)
    plan = []
    if with_time:
        plan.append(("time", [0], 4, {}, 4))
    plan.append(("latitude", [1], 5, {}, _pad(b"x" * len(lats) * 4).__len__()))
    plan.append(("longitude", [2], 5, {}, _pad(b"x" * len(lons) * 4).__len__()))
    plan.append((variable, [0, 1, 2], 5, {"_FillValue": fill}, cells * 4))

    def header(offsets: dict) -> bytes:
        out = b"CDF\x02" + struct.pack(">I", records)
        out += struct.pack(">II", 0x0A, len(dims))
        for name, size in dims:
            out += _name(name) + struct.pack(">I", size)
        out += struct.pack(">II", 0, 0)  # no global attributes
        out += struct.pack(">II", 0x0B, len(plan))
        for name, dim_ids, nc_type, attributes, vsize in plan:
            out += _name(name) + struct.pack(">I", len(dim_ids))
            out += b"".join(struct.pack(">I", d) for d in dim_ids)
            if attributes:
                out += struct.pack(">II", 0x0C, len(attributes))
                for key, value in attributes.items():
                    out += _name(key) + struct.pack(">II", 5, 1) + struct.pack(">f", value)
            else:
                out += struct.pack(">II", 0, 0)
            out += struct.pack(">II", nc_type, vsize)
            out += struct.pack(">Q", offsets.get(name, 0))
        return out

    # Two passes: `begin` sits inside the header but points past it, and it is a
    # fixed width, so measuring with zeroes gives the right size.
    at = len(header({}))
    offsets = {}
    for name, _dim_ids, _t, _a, vsize in plan:
        if name in ("latitude", "longitude"):
            offsets[name] = at
            at += vsize
    for name, dim_ids, _t, _a, _vsize in plan:
        if dim_ids and dim_ids[0] == 0:  # record variables share the record block
            offsets[name] = at
            at += _pad(b"x" * (4 if name == "time" else cells * 4)).__len__()

    body = header(offsets)
    body += struct.pack(f">{len(lats)}f", *lats)
    body += struct.pack(f">{len(lons)}f", *lons)
    for record in range(records):
        if with_time:
            body += struct.pack(">i", 1_000_000 + record * 24)
        # A recognisable ramp, plus one gap so the fill value gets exercised.
        values = [float(record * 100 + n) for n in range(cells)]
        values[0] = fill
        body += struct.pack(f">{cells}f", *values)
    return body


def test_reads_dimensions_variables_and_attributes():
    data = Dataset(_netcdf())

    assert data.record_count == 3
    assert data.dimensions == {"time": 3, "latitude": 2, "longitude": 3}
    assert set(data.variables) == {"time", "latitude", "longitude", "POAC"}
    assert data.variables["POAC"].shape == (3, 2, 3)
    assert data.variables["POAC"].attributes["_FillValue"] == [pytest.approx(-32767.0)]


def test_coordinate_variables_read_contiguously():
    data = Dataset(_netcdf())
    assert data.read("latitude").tolist() == [50.0, 50.5]
    assert data.read("longitude").tolist() == [7.0, 7.5, 8.0]


def test_record_variables_are_strided_not_contiguous():
    """The point of the reader.

    Record variables are interleaved -- one slice of every one of them, then the
    next -- so reading step 2 means skipping two whole record blocks, not two
    grids. Read as if it were contiguous, every step after the first is a
    plausible-looking mixture of the time stamp and the wrong hours' data.
    """
    data = Dataset(_netcdf(records=3))

    for record in range(3):
        grid = data.read("POAC", record)
        assert grid.shape == (2, 3)
        # The ramp identifies which record we actually landed on.
        assert grid[0, 1] == record * 100 + 1
        assert int(data.read("time", record)) == 1_000_000 + record * 24


def test_fill_values_become_nan():
    data = Dataset(_netcdf())
    grid = data.masked("POAC", 0)
    assert np.isnan(grid[0, 0])
    assert np.isfinite(grid[0, 1])


def test_a_single_record_variable_has_no_trailing_pad():
    """With one record variable its record carries no padding.

    An odd corner of the format, and getting it wrong shifts every step after
    the first -- so it is worth its own case rather than being assumed.
    """
    data = Dataset(_netcdf(records=2, lons=(7.0,), with_time=False))
    assert data.record_size == 2 * 1 * 4  # 2 lats x 1 lon x float32, unpadded
    # Cell 0 of every record is the fill value; cell 1 carries the ramp, and its
    # value is what says which record we landed on.
    assert np.isnan(data.masked("POAC", 1)[0, 0])
    assert data.read("POAC", 0)[1, 0] == 1.0
    assert data.read("POAC", 1)[1, 0] == 101.0


def test_a_record_beyond_the_end_is_refused():
    data = Dataset(_netcdf(records=2))
    with pytest.raises(IndexError):
        data.read("POAC", 5)


def test_netcdf4_is_rejected_rather_than_misread():
    with pytest.raises(ValueError, match="NetCDF-4"):
        Dataset(b"\x89HDF\r\n\x1a\n" + b"\x00" * 64)


# ------------------------------------------------------------------ pollen


def test_seasons_match_the_dataset_description():
    """DWD publishes a species only inside its own season, so the site has to
    know the seasons to tell "nothing published" from "nothing there"."""
    assert pollen.in_season("grasses", date(2026, 8, 2))
    assert pollen.in_season("ragweed", date(2026, 8, 2))
    # Tree pollen in August is not missing data, it is out of season.
    assert not pollen.in_season("birch", date(2026, 8, 2))
    assert not pollen.in_season("hazel", date(2026, 8, 2))
    assert pollen.in_season("hazel", date(2026, 2, 1))
    assert pollen.in_season("birch", date(2026, 3, 15))


def test_season_edges_are_inclusive():
    start, end = pollen.season_dates("ragweed", 2026)
    assert (start, end) == (date(2026, 8, 1), date(2026, 10, 7))
    assert pollen.in_season("ragweed", start)
    assert pollen.in_season("ragweed", end)
    assert not pollen.in_season("ragweed", date(2026, 7, 31))


def test_out_of_season_is_a_lookup_error_not_a_fetch(monkeypatch):
    """It must not reach the network to discover a 404 it could have predicted."""

    def boom(*args, **kwargs):
        raise AssertionError("should not have gone to DWD")

    monkeypatch.setattr(pollen, "latest_run", boom)
    with pytest.raises(LookupError, match="out of season"):
        pollen.fetch("birch", run=date(2026, 8, 2))


def test_thresholds_differ_by_species():
    """Ragweed provokes symptoms an order of magnitude lower than grass; one
    shared scale would either cry wolf about grass or say nothing about it."""
    assert pollen.thresholds("ragweed")[0] < pollen.thresholds("grasses")[0]
    assert pollen.level_name("ragweed", 25.0) == "high"
    assert pollen.level_name("grasses", 25.0) == "low"


def test_levels_climb_with_concentration():
    for key in pollen.SPECIES:
        low, high, very = pollen.thresholds(key)
        assert pollen.level_name(key, low - 0.01) == "low"
        assert pollen.level_name(key, low) == "moderate"
        assert pollen.level_name(key, high) == "high"
        assert pollen.level_name(key, very * 10) == "very_high"


def test_bands_are_contiguous_and_named():
    bands = pollen._bands("grasses")
    assert [b["label"] for b in bands] == ["low", "moderate", "high", "very_high"]
    assert bands[0]["from"] == 0.0
    for earlier, later in zip(bands, bands[1:]):
        assert earlier["to"] == later["from"]  # no gap the legend cannot explain
    assert bands[-1]["open"] is True


def test_map_bounds_clamp_to_the_published_domain():
    """The pollen grid is Germany only, narrower than the map the card draws.

    Hung on the window that was asked for rather than the one it covers, the
    field would be stretched sideways across the coastline.
    """
    wide = (40.0, 0.0, 60.0, 25.0)
    bounds = pollen.map_bounds(wide)
    assert bounds == (pollen.DOMAIN[0], pollen.DOMAIN[1], pollen.DOMAIN[2], pollen.DOMAIN[3])


def test_map_bounds_snap_to_grid_cells():
    """Reported bounds must be cell centres, because that is what render crops."""
    bounds = pollen.map_bounds((52.0, 9.0, 54.0, 11.0))
    for value, origin in ((bounds[0], pollen.DOMAIN[0]), (bounds[2], pollen.DOMAIN[0])):
        assert abs((value - origin) / pollen.GRID_STEP % 1.0) < 1e-6
    assert bounds[0] >= 52.0 and bounds[2] <= 54.0


def test_an_area_outside_germany_is_refused():
    with pytest.raises(ValueError, match="outside"):
        pollen.map_bounds((35.0, 20.0, 40.0, 24.0))


def test_describe_lists_every_species_with_its_season(monkeypatch):
    monkeypatch.setattr(pollen, "latest_run", lambda *a, **k: date(2026, 8, 2))
    described = pollen.describe((52.0, 9.0, 54.0, 11.0), when=date(2026, 8, 2))

    assert set(described["species"]) == set(pollen.SPECIES)
    assert described["step_hours"] == 24  # daily means, not hours
    assert described["max_step"] == pollen.MAX_STEP
    in_season = {k: v["in_season"] for k, v in described["species"].items()}
    assert in_season == {
        "hazel": False,
        "alder": False,
        "birch": False,
        "grasses": True,
        "ragweed": True,
    }
    # Out of season still carries its dates, so the card can say when to come back.
    assert described["species"]["birch"]["season"]["start"] == "2026-01-30"


def test_describe_survives_a_failing_run_probe(monkeypatch):
    """One dead probe should cost the run label, not the whole card."""

    def boom(*args, **kwargs):
        raise RuntimeError("opendata unreachable")

    monkeypatch.setattr(pollen, "latest_run", boom)
    described = pollen.describe((52.0, 9.0, 54.0, 11.0), when=date(2026, 8, 2))
    assert described["run"] is None
    assert described["species"]["grasses"]["bands"]
