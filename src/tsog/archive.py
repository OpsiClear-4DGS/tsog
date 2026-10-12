# SPDX-License-Identifier: Apache-2.0
"""Bounded ZIP32 and raw lossless WebP readers; no filesystem extraction."""
from io import BytesIO
import json
from pathlib import Path
import struct
import zipfile
import zlib

from .metadata import entry_name, validate_metadata, attribute_names

MIB = 1048576


class Archive:
    def __init__(self, source, require_profile=False):
        self._file = BytesIO(source) if isinstance(source, (bytes, bytearray)) else open(source, "rb")
        self.zip = None
        try:
            self._file.seek(0, 2)
            length = self._file.tell()
            self._file.seek(max(0, length - 65557))
            tail = self._file.read()
            end = tail.rfind(b"PK\x05\x06")
            while end >= 0 and (end + 22 > len(tail) or end + 22 + struct.unpack_from("<H", tail, end + 20)[0] != len(tail)):
                end = tail.rfind(b"PK\x05\x06", 0, end)
            if end < 0:
                raise ValueError("Missing ZIP end record")
            disk, directory_disk, entries_disk, entries, size, offset = struct.unpack_from("<4H2I", tail, end + 4)
            if disk or directory_disk or entries_disk != entries or entries == 65535 or size == 0xffffffff or offset == 0xffffffff:
                raise ValueError("ZIP64 and multi-disk archives are unsupported")
            if not 1 <= entries <= 1024 or size > 4*MIB or offset + size != length-len(tail)+end:
                raise ValueError("Invalid or oversized ZIP directory")
            self._file.seek(0)
            self.zip = zipfile.ZipFile(self._file)
            infos = self.zip.infolist()
            if len(infos) != entries or len({i.filename for i in infos}) != entries:
                raise ValueError("Duplicate entries or directory count mismatch")
            intervals = []
            for info in infos:
                entry_name(info.orig_filename)
                if any(ord(c) > 127 for c in info.filename) and not info.flag_bits & 0x800:
                    raise ValueError("Non-ASCII ZIP names require the UTF-8 flag")
                if info.compress_type not in (0, 8) or info.flag_bits & (1 | 64 | 8192):
                    raise ValueError("Unsupported compression or encryption")
                if info.file_size > 512*MIB:
                    raise ValueError("Entry exceeds the profile limit")
                self._reject_zip64(info.extra)
                self._file.seek(info.header_offset)
                header = self._file.read(30)
                if len(header) != 30 or header[:4] != b"PK\x03\x04":
                    raise ValueError("Invalid local ZIP header")
                flags, method = struct.unpack_from("<2H", header, 6)
                crc, compressed, uncompressed = struct.unpack_from("<3I", header, 14)
                name_size, extra_size = struct.unpack_from("<2H", header, 26)
                raw_name = self._file.read(name_size)
                local_extra = self._file.read(extra_size)
                self._reject_zip64(local_extra)
                expected_name = info.filename.encode("utf-8" if flags & 0x800 else "cp437")
                if flags != info.flag_bits or method != info.compress_type or raw_name != expected_name:
                    raise ValueError("Conflicting local ZIP header")
                data_end = info.header_offset + 30 + name_size + extra_size + info.compress_size
                record_end = data_end
                expected = (info.CRC, info.compress_size, info.file_size)
                if flags & 8:
                    if (crc, compressed, uncompressed) != (0, 0, 0):
                        raise ValueError("Descriptor entries must have zero local sizes/CRC")
                    self._file.seek(data_end)
                    descriptor = self._file.read(16)
                    if len(descriptor) >= 16 and descriptor[:4] == b"PK\x07\x08" and struct.unpack_from("<3I", descriptor, 4) == expected:
                        record_end += 16
                    elif len(descriptor) >= 12 and struct.unpack_from("<3I", descriptor) == expected:
                        record_end += 12
                    else:
                        raise ValueError("Invalid data descriptor")
                elif (crc, compressed, uncompressed) != expected:
                    raise ValueError("Local CRC/size mismatch")
                if info.header_offset < 0 or record_end > offset:
                    raise ValueError("ZIP record extends into the directory")
                intervals.append((info.header_offset, record_end))
            intervals.sort()
            if any(b[0] < a[1] for a, b in zip(intervals, intervals[1:])):
                raise ValueError("Overlapping ZIP records")
            self.meta = validate_metadata(json.loads(self.read("meta.json", 4*MIB)), require_profile)
            missing = attribute_names(self.meta) - set(self.zip.namelist())
            if missing:
                raise ValueError(f"Missing attribute entries: {sorted(missing)}")
            if "audio" in self.meta:
                audio = self.meta["audio"]["file"]
                if audio not in self.zip.namelist() or not 0 < self.zip.getinfo(audio).file_size <= 128*MIB:
                    raise ValueError("Missing, empty or oversized audio entry")
        except (zipfile.BadZipFile, UnicodeDecodeError) as error:
            self.close()
            raise ValueError(f"Invalid ZIP/metadata: {error}") from error
        except Exception:
            self.close()
            raise

    @staticmethod
    def _reject_zip64(extra):
        pos = 0
        while pos < len(extra):
            if pos+4 > len(extra):
                raise ValueError("Truncated ZIP extra field")
            kind, size = struct.unpack_from("<2H", extra, pos)
            if kind == 1:
                raise ValueError("ZIP64 is unsupported")
            pos += 4+size
        if pos != len(extra):
            raise ValueError("Invalid ZIP extra field")

    def read(self, name, limit=512*MIB):
        if name not in self.zip.namelist() or self.zip.getinfo(name).file_size > limit:
            raise ValueError(f"Missing or oversized entry: {name}")
        try:
            return self.zip.read(name)  # zipfile verifies actual length and CRC.
        except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError) as error:
            raise ValueError(f"Invalid ZIP entry {name}: {error}") from error

    def close(self):
        if self.zip is not None:
            self.zip.close()
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def webp_dimensions(data):
    if len(data) < 25 or data[:4] != b"RIFF" or data[8:12] != b"WEBP" or struct.unpack_from("<I", data, 4)[0]+8 != len(data):
        raise ValueError("Invalid WebP container")
    pos, dimensions, extended = 12, None, None
    while pos < len(data):
        if pos+8 > len(data):
            raise ValueError("Truncated WebP chunk")
        kind, size = data[pos:pos+4], struct.unpack_from("<I", data, pos+4)[0]
        start = pos+8
        if start+size > len(data):
            raise ValueError("Truncated WebP data")
        if kind in (b"VP8 ", b"ALPH", b"ANIM", b"ANMF"):
            raise ValueError("Attribute images must be still lossless WebP")
        if kind == b"VP8L":
            if dimensions or size < 5 or data[start] != 0x2f:
                raise ValueError("Invalid lossless WebP header")
            bits = struct.unpack_from("<I", data, start+1)[0]
            if bits >> 29:
                raise ValueError("Unsupported lossless WebP version")
            dimensions = ((bits & 16383)+1, ((bits >> 14) & 16383)+1)
        if kind == b"VP8X":
            if extended or size != 10 or data[start] & 2:
                raise ValueError("Invalid extended WebP header")
            extended = (int.from_bytes(data[start+4:start+7], "little")+1, int.from_bytes(data[start+7:start+10], "little")+1)
        pos = start+size+(size & 1)
    if pos != len(data) or dimensions is None or extended is not None and extended != dimensions:
        raise ValueError("Missing lossless data or conflicting WebP dimensions")
    return dimensions
