"""A small reader for NetCDF-3 classic files.

DWD publishes the ICON-ART pollen forecast as NetCDF ("CDF\\x02", the 64-bit
offset variant of the classic format). That format is a documented, fixed
big-endian layout, so reading it here costs about a hundred lines and keeps
``netCDF4``/``h5netcdf`` -- which drag in the HDF5 C library -- out of the
image, exactly as ``grib2.py`` does for GRIB.

Deliberately partial: enough to read a CF-style gridded forecast, and nothing
else. NetCDF-4 is an HDF5 container and is *not* handled -- it is rejected by
magic number rather than misread.

Spec: https://docs.unidata.ucar.edu/nug/current/file_format_specifications.html
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

#: Tags that introduce each list in the header.
NC_DIMENSION = 0x0A
NC_VARIABLE = 0x0B
NC_ATTRIBUTE = 0x0C

#: nc_type -> (numpy dtype, size in bytes). Everything is big-endian.
TYPES: Dict[int, Tuple[str, int]] = {
    1: ("i1", 1),  # NC_BYTE
    2: ("S1", 1),  # NC_CHAR
    3: (">i2", 2),  # NC_SHORT
    4: (">i4", 4),  # NC_INT
    5: (">f4", 4),  # NC_FLOAT
    6: (">f8", 8),  # NC_DOUBLE
}


def _padded(length: int) -> int:
    """Header fields are padded out to a four-byte boundary."""
    return length + (-length % 4)


@dataclass(frozen=True)
class Variable:
    name: str
    dimensions: Tuple[str, ...]
    shape: Tuple[int, ...]
    dtype: str
    itemsize: int
    attributes: Dict[str, object]
    #: Byte offset of the first record (or of the whole array, if not a record
    #: variable).
    begin: int
    #: Bytes one record of this variable occupies, padded. Only meaningful when
    #: ``is_record``.
    vsize: int
    is_record: bool


class _Reader:
    """Cursor over the header bytes."""

    def __init__(self, buffer: bytes) -> None:
        self.buffer = buffer
        self.at = 0

    def uint32(self) -> int:
        value = struct.unpack_from(">I", self.buffer, self.at)[0]
        self.at += 4
        return value

    def offset(self, version: int) -> int:
        """``begin`` is 32-bit in v1 and 64-bit in the 64-bit-offset v2."""
        if version == 1:
            return self.uint32()
        value = struct.unpack_from(">Q", self.buffer, self.at)[0]
        self.at += 8
        return value

    def name(self) -> str:
        count = self.uint32()
        text = self.buffer[self.at : self.at + count].decode("utf-8", "replace")
        self.at += _padded(count)
        return text

    def values(self, nc_type: int, count: int):
        dtype, size = TYPES[nc_type]
        raw = self.buffer[self.at : self.at + count * size]
        self.at += _padded(count * size)
        if nc_type == 2:  # NC_CHAR: attribute text, not an array
            return raw.decode("utf-8", "replace").rstrip("\x00")
        array = np.frombuffer(raw, dtype=dtype)
        return array.tolist()

    def attributes(self) -> Dict[str, object]:
        tag = self.uint32()
        count = self.uint32()
        if tag != NC_ATTRIBUTE:
            # ABSENT is two zero words; anything else means we have lost our
            # place, and reading on would produce plausible nonsense.
            if tag == 0 and count == 0:
                return {}
            raise ValueError(f"Expected an attribute list, found tag {tag:#x}")
        return {self.name(): self.values(self.uint32(), self.uint32()) for _ in range(count)}

    def tagged_list(self, expected: int) -> int:
        """Length of a dimension or variable list, or 0 when ABSENT."""
        tag = self.uint32()
        count = self.uint32()
        if tag == 0 and count == 0:
            return 0
        if tag != expected:
            raise ValueError(f"Expected list tag {expected:#x}, found {tag:#x}")
        return count


class Dataset:
    """A parsed NetCDF-3 file, held as bytes with an index over it.

    The arrays are read lazily out of the original buffer, so opening a file to
    look at one time step does not materialise the rest of it.
    """

    def __init__(self, buffer: bytes) -> None:
        if buffer[:3] != b"CDF":
            hint = " (this looks like NetCDF-4/HDF5)" if buffer[:4] == b"\x89HDF" else ""
            raise ValueError(f"Not a NetCDF-3 classic file{hint}")
        version = buffer[3]
        if version not in (1, 2):
            raise ValueError(f"Unsupported NetCDF format version {version}")

        self.buffer = buffer
        reader = _Reader(buffer)
        reader.at = 4
        self.record_count = reader.uint32()

        #: Name -> length. The unlimited dimension is written as length 0; its
        #: real length is ``record_count``.
        self.dimensions: Dict[str, int] = {}
        unlimited: Optional[str] = None
        order: List[str] = []
        for _ in range(reader.tagged_list(NC_DIMENSION)):
            name, length = reader.name(), reader.uint32()
            if length == 0:
                unlimited = name
            self.dimensions[name] = length or self.record_count
            order.append(name)

        self.attributes = reader.attributes()

        self.variables: Dict[str, Variable] = {}
        for _ in range(reader.tagged_list(NC_VARIABLE)):
            name = reader.name()
            dim_ids = [reader.uint32() for _ in range(reader.uint32())]
            names = tuple(order[i] for i in dim_ids)
            attributes = reader.attributes()
            nc_type = reader.uint32()
            vsize = reader.uint32()
            begin = reader.offset(version)
            self.variables[name] = Variable(
                name=name,
                dimensions=names,
                shape=tuple(self.dimensions[d] for d in names),
                dtype=TYPES[nc_type][0],
                itemsize=TYPES[nc_type][1],
                attributes=attributes,
                begin=begin,
                vsize=vsize,
                # Only the *first* dimension may be the unlimited one, and that
                # is what makes a variable interleaved rather than contiguous.
                is_record=bool(names) and names[0] == unlimited,
            )

        #: Records are stored interleaved -- one slice of every record variable,
        #: then the next -- so stepping through time means striding by the sum
        #: of their record sizes rather than reading one array end to end.
        records = [v for v in self.variables.values() if v.is_record]
        self.record_size = sum(v.vsize for v in records)
        # One lone record variable is stored without its trailing pad, which
        # would otherwise push every step after the first off by a few bytes.
        if len(records) == 1:
            only = records[0]
            self.record_size = (
                int(np.prod(only.shape[1:], dtype=np.int64)) * only.itemsize
            )

    def read(self, name: str, record: Optional[int] = None) -> np.ndarray:
        """One variable, or one time step of a record variable.

        ``record`` is required for record variables and ignored otherwise.
        """
        variable = self.variables[name]
        if not variable.is_record:
            count = int(np.prod(variable.shape, dtype=np.int64)) if variable.shape else 1
            values = np.frombuffer(
                self.buffer, dtype=variable.dtype, count=count, offset=variable.begin
            )
            return values.reshape(variable.shape)

        if record is None:
            raise ValueError(f"{name} varies with the record dimension; pass record=")
        if not 0 <= record < self.record_count:
            raise IndexError(f"Record {record} outside 0..{self.record_count - 1}")

        shape = variable.shape[1:]
        count = int(np.prod(shape, dtype=np.int64)) if shape else 1
        values = np.frombuffer(
            self.buffer,
            dtype=variable.dtype,
            count=count,
            offset=variable.begin + record * self.record_size,
        )
        return values.reshape(shape)

    def masked(self, name: str, record: Optional[int] = None) -> np.ndarray:
        """``read`` with the file's own fill value turned into NaN."""
        values = self.read(name, record).astype(np.float32)
        variable = self.variables[name]
        for key in ("_FillValue", "missing_value"):
            fill = variable.attributes.get(key)
            if isinstance(fill, list) and fill:
                values = np.where(values == np.float32(fill[0]), np.nan, values)
        return values
