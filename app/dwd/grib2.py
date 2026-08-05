"""A small GRIB2 reader for the DWD ICON ``regular-lat-lon`` products.

Full GRIB2 is a large specification, but the files we need are a narrow slice
of it: one message, grid definition template 3.0 (regular latitude/longitude)
and data representation template 5.0 (simple packing). Supporting exactly that
keeps the container free of ``eccodes``, which would otherwise dominate the
image size for no benefit here.

If DWD ever switches these products to another packing the reader raises
``UnsupportedGrib`` rather than returning silently wrong numbers.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np


class UnsupportedGrib(ValueError):
    """The message uses a template this reader deliberately does not implement."""


@dataclass
class GribField:
    values: np.ndarray  # 2-D, shape (nj, ni), NaN where masked out
    lat_first: float
    lon_first: float
    lat_last: float
    lon_last: float
    ni: int
    nj: int

    @property
    def lats(self) -> np.ndarray:
        return np.linspace(self.lat_first, self.lat_last, self.nj)

    @property
    def lons(self) -> np.ndarray:
        return np.linspace(self.lon_first, self.lon_last, self.ni)


def _signed(raw: int, bits: int) -> int:
    """GRIB stores signed integers as sign-and-magnitude, not two's complement."""
    sign_bit = 1 << (bits - 1)
    return -(raw & (sign_bit - 1)) if raw & sign_bit else raw


def _normalise_longitude(value: float) -> float:
    """GRIB longitudes run 0..360; the rest of the app uses -180..180."""
    return value - 360.0 if value > 180.0 else value


def _unpack_bits(payload: bytes, count: int, bits: int) -> np.ndarray:
    """Read ``count`` unsigned big-endian integers of ``bits`` width."""
    if bits == 0:
        return np.zeros(count, dtype=np.int64)

    raw = np.frombuffer(payload, dtype=np.uint8)
    unpacked = np.unpackbits(raw)[: count * bits]
    if unpacked.size < count * bits:
        raise UnsupportedGrib("Data section is shorter than the grid it describes")

    grid = unpacked.reshape(count, bits).astype(np.int64)
    weights = (1 << np.arange(bits - 1, -1, -1)).astype(np.int64)
    return grid @ weights


def decode(data: bytes) -> GribField:
    """Decode the first message of a GRIB2 file."""
    if data[:4] != b"GRIB":
        raise UnsupportedGrib("Not a GRIB file")
    if data[7] != 2:
        raise UnsupportedGrib(f"GRIB edition {data[7]} is not supported")

    sections: Dict[int, bytes] = {}
    position = 16  # skip the indicator section
    while position < len(data) - 4:
        if data[position : position + 4] == b"7777":
            break
        length = struct.unpack(">I", data[position : position + 4])[0]
        if length <= 0:
            raise UnsupportedGrib("Malformed section length")
        sections[data[position + 4]] = data[position : position + length]
        position += length

    for required in (3, 5, 7):
        if required not in sections:
            raise UnsupportedGrib(f"Message has no section {required}")

    # --- Section 3: grid definition -------------------------------------
    grid = sections[3]
    grid_template = struct.unpack(">H", grid[12:14])[0]
    if grid_template != 0:
        raise UnsupportedGrib(f"Grid template 3.{grid_template} is not supported")

    ni = struct.unpack(">I", grid[30:34])[0]
    nj = struct.unpack(">I", grid[34:38])[0]
    lat_first = struct.unpack(">i", grid[46:50])[0] / 1e6
    lon_first = struct.unpack(">i", grid[50:54])[0] / 1e6
    lat_last = struct.unpack(">i", grid[55:59])[0] / 1e6
    lon_last = struct.unpack(">i", grid[59:63])[0] / 1e6

    # --- Section 5: how the values are packed ---------------------------
    drs = sections[5]
    point_count = struct.unpack(">I", drs[5:9])[0]
    drs_template = struct.unpack(">H", drs[9:11])[0]
    if drs_template != 0:
        raise UnsupportedGrib(f"Data template 5.{drs_template} is not supported")

    reference = struct.unpack(">f", drs[11:15])[0]
    binary_scale = _signed(struct.unpack(">H", drs[15:17])[0], 16)
    decimal_scale = _signed(struct.unpack(">H", drs[17:19])[0], 16)
    bit_count = drs[19]

    # --- Section 6: bitmap, marking points that carry no value ----------
    bitmap: Optional[np.ndarray] = None
    if 6 in sections and sections[6][5] == 0:
        bits = np.unpackbits(np.frombuffer(sections[6][6:], dtype=np.uint8))
        bitmap = bits[: ni * nj].astype(bool)

    # --- Section 7: the packed values -----------------------------------
    packed = _unpack_bits(sections[7][5:], point_count, bit_count)
    values = (reference + packed * (2.0**binary_scale)) / (10.0**decimal_scale)

    if bitmap is not None:
        full = np.full(ni * nj, np.nan, dtype=np.float64)
        if bitmap.sum() != values.size:
            raise UnsupportedGrib("Bitmap does not match the number of packed values")
        full[bitmap] = values
        values = full
    elif values.size != ni * nj:
        raise UnsupportedGrib("Value count does not match the grid size")

    return GribField(
        values=values.reshape(nj, ni),
        lat_first=lat_first,
        lon_first=_normalise_longitude(lon_first),
        lat_last=lat_last,
        lon_last=_normalise_longitude(lon_last),
        ni=ni,
        nj=nj,
    )
