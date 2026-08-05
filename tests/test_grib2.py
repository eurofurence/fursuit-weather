"""Tests for the minimal GRIB2 reader.

Messages are built by hand so the suite stays offline; each one exercises the
exact template combination DWD uses for the ICON ``regular-lat-lon`` products.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from app.dwd.grib2 import UnsupportedGrib, decode


def _section(number: int, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 5) + bytes([number]) + body


def _grid_section(ni: int, nj: int, grid_template: int = 0) -> bytes:
    body = bytearray(67)
    struct.pack_into(">H", body, 7, grid_template)  # octet 13-14 -> idx 7
    struct.pack_into(">I", body, 25, ni)  # idx 30 in the full section
    struct.pack_into(">I", body, 29, nj)
    struct.pack_into(">i", body, 41, 50_000_000)  # la1 = 50.0
    struct.pack_into(">i", body, 45, 5_000_000)  # lo1 = 5.0
    struct.pack_into(">i", body, 50, 54_000_000)  # la2 = 54.0
    struct.pack_into(">i", body, 54, 10_000_000)  # lo2 = 10.0
    return _section(3, bytes(body))


def _sign_magnitude(value: int) -> int:
    """Encode as GRIB does: a sign bit plus magnitude, not two's complement."""
    return 0x8000 | abs(value) if value < 0 else value


def _drs_section(points: int, reference: float, binary: int, decimal: int, bits: int, template=0) -> bytes:
    body = bytearray(16)
    struct.pack_into(">I", body, 0, points)
    struct.pack_into(">H", body, 4, template)
    struct.pack_into(">f", body, 6, reference)
    struct.pack_into(">H", body, 10, _sign_magnitude(binary))
    struct.pack_into(">H", body, 12, _sign_magnitude(decimal))
    body[14] = bits
    return _section(5, bytes(body))


def _data_section(values: list[int], bits: int) -> bytes:
    stream = "".join(format(v, f"0{bits}b") for v in values)
    stream += "0" * (-len(stream) % 8)
    payload = bytes(int(stream[i : i + 8], 2) for i in range(0, len(stream), 8))
    return _section(7, payload)


def _message(sections: bytes) -> bytes:
    head = b"GRIB" + b"\x00\x00" + bytes([0]) + bytes([2])
    total = 16 + len(sections) + 4
    return head + struct.pack(">Q", total) + sections + b"7777"


def _simple_message(ni=3, nj=2, values=None, bits=8, reference=0.0, binary=0, decimal=0):
    values = values if values is not None else list(range(ni * nj))
    return _message(
        _grid_section(ni, nj)
        + _drs_section(len(values), reference, binary, decimal, bits)
        + _data_section(values, bits)
    )


def test_decodes_a_simple_packed_field():
    field = decode(_simple_message(values=[0, 1, 2, 3, 4, 5]))
    assert field.ni == 3 and field.nj == 2
    assert field.values.shape == (2, 3)
    np.testing.assert_allclose(field.values, [[0, 1, 2], [3, 4, 5]])


def test_applies_reference_and_scale_factors():
    """value = (R + X * 2^E) / 10^D."""
    field = decode(_simple_message(values=[0, 1, 2, 3, 4, 5], reference=10.0, binary=1, decimal=1))
    np.testing.assert_allclose(field.values.ravel(), [1.0, 1.2, 1.4, 1.6, 1.8, 2.0])


def test_handles_negative_scale_factors():
    """GRIB uses sign-and-magnitude, so 0x8001 is -1 rather than 32769."""
    field = decode(_simple_message(values=[4], ni=1, nj=1, binary=-1))
    np.testing.assert_allclose(field.values.ravel(), [2.0])


def test_reads_grid_geometry_and_wraps_longitude():
    field = decode(_simple_message())
    assert field.lat_first == 50.0
    assert field.lat_last == 54.0
    assert field.lons[0] == 5.0
    assert len(field.lats) == field.nj


def test_longitudes_above_180_become_negative():
    """DWD publishes 356.06 for what the rest of the app calls -3.94."""
    body = bytearray(67)
    struct.pack_into(">I", body, 25, 1)
    struct.pack_into(">I", body, 29, 1)
    struct.pack_into(">i", body, 45, 356_060_000)
    message = _message(
        _section(3, bytes(body)) + _drs_section(1, 0.0, 0, 0, 8) + _data_section([1], 8)
    )
    assert decode(message).lon_first == pytest.approx(-3.94)


def test_bitmap_marks_missing_points_as_nan():
    grid = _grid_section(2, 2)
    drs = _drs_section(2, 0.0, 0, 0, 8)
    bitmap = _section(6, bytes([0]) + bytes([0b10010000]))  # points 0 and 3 present
    message = _message(grid + drs + bitmap + _data_section([7, 9], 8))

    values = decode(message).values
    assert values[0][0] == 7
    assert values[1][1] == 9
    assert np.isnan(values[0][1]) and np.isnan(values[1][0])


def test_rejects_an_unsupported_grid_template():
    message = _message(
        _grid_section(2, 2, grid_template=30)
        + _drs_section(4, 0.0, 0, 0, 8)
        + _data_section([1, 2, 3, 4], 8)
    )
    with pytest.raises(UnsupportedGrib, match="Grid template"):
        decode(message)


def test_rejects_an_unsupported_packing_template():
    """Complex packing must fail loudly rather than produce wrong numbers."""
    message = _message(
        _grid_section(2, 2)
        + _drs_section(4, 0.0, 0, 0, 8, template=3)
        + _data_section([1, 2, 3, 4], 8)
    )
    with pytest.raises(UnsupportedGrib, match="Data template"):
        decode(message)


def test_rejects_a_non_grib_payload():
    with pytest.raises(UnsupportedGrib):
        decode(b"this is not a GRIB file at all")


def test_rejects_a_truncated_data_section():
    message = _message(
        _grid_section(4, 4) + _drs_section(16, 0.0, 0, 0, 8) + _data_section([1, 2], 8)
    )
    with pytest.raises(UnsupportedGrib):
        decode(message)


def test_mismatched_bitmap_is_rejected():
    grid = _grid_section(2, 2)
    drs = _drs_section(3, 0.0, 0, 0, 8)  # claims 3 values
    bitmap = _section(6, bytes([0]) + bytes([0b10000000]))  # but marks only 1
    message = _message(grid + drs + bitmap + _data_section([1, 2, 3], 8))
    with pytest.raises(UnsupportedGrib, match="Bitmap"):
        decode(message)
