# SPDX-License-Identifier: Apache-2.0
"""Update playback/audio without recompressing any attribute image."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import zipfile

from .archive import Archive, webp_dimensions
from .metadata import PROFILE, attribute_names, validate_metadata, timing, audio_mime


def validate(source, *, full=False, require_profile=False):
    with Archive(source, require_profile) as archive:
        meta = archive.meta
        dimensions = None
        palette = meta.get("shN", {}).get("files", [None])[0]
        per_point = set()
        for key in ("means", "scales", "quats", "sh0", "timeline"):
            if key in meta:
                per_point.update(meta[key]["files"])
        if "shN" in meta:
            per_point.add(meta["shN"]["files"][1])
        if "temporal" in meta:
            per_point.update(meta["temporal"]["means"]["files"])
        for name in attribute_names(meta):
            width, height = webp_dimensions(archive.read(name))
            if name == palette:
                g = meta["shN"]
                expected = (64*((g["bands"]+1)**2-1), (g["count"]+63)//64)
                if (width, height) != expected:
                    raise ValueError("Invalid SH palette image dimensions")
            if name in per_point:
                if width*height < meta["count"] or dimensions is not None and dimensions != (width, height):
                    raise ValueError("Invalid per-Gaussian image dimensions")
                dimensions = (width, height)
        if "audio" in meta:
            archive.read(meta["audio"]["file"], 128*1048576)
        report = {"version": meta["version"], "profile": meta.get("profile"), "count": meta["count"],
                  "timeline": "static" if "timeline" not in meta else {0: "discrete", 1: "continuous"}[meta["timeline"]["type"]],
                  "sh_degree": meta.get("shN", {}).get("bands", 0), "audio": "audio" in meta,
                  "timing": timing(meta), "dimensions": dimensions,
                  "validation": "container, CRCs, metadata and lossless image headers"}
    if full:
        from . import decode
        scene = decode(source, include_audio=False)
        report["validation"] += ", all attribute values"
        report["attribute_bytes"] = scene.attribute_bytes
    return report


def repackage(source, destination, *, playback=None, audio=None, mime_type=None, remove_audio=False):
    destination = Path(destination)
    if destination.exists() or destination.suffix.lower() != ".tsog":
        raise ValueError("Destination must be a new .tsog file")
    if audio is not None and remove_audio:
        raise ValueError("Cannot add and remove audio together")
    with Archive(source) as original:
        meta = deepcopy(original.meta)
        meta["version"] = 1
        meta["profile"] = dict(PROFILE)
        if playback is not None:
            meta["playback"] = {**meta.get("playback", {}), **playback}
        old_audio = meta.get("audio", {}).get("file")
        track = None
        if remove_audio:
            meta.pop("audio", None)
        elif audio is not None:
            audio = Path(audio)
            if not 0 < audio.stat().st_size <= 128*1048576:
                raise ValueError("Audio must be 1 byte..128 MiB")
            track = audio.read_bytes()
            suffix = audio.suffix.lower().lstrip(".")
            if not suffix.isascii() or not suffix.isalnum():
                raise ValueError("Audio filename requires a portable extension")
            description = {"file": f"audio/track.{suffix}", "volume": meta.get("audio", {}).get("volume", 1)}
            if mime_type is not None:
                description["mimeType"] = mime_type
            description["mimeType"] = audio_mime(description)
            meta["audio"] = description
        elif mime_type is not None:
            raise ValueError("mime_type requires a new audio file")
        validate_metadata(meta, require_profile=True)
        temp = tempfile.NamedTemporaryFile(prefix=".tsog-", dir=destination.parent, delete=False)
        try:
            with temp, zipfile.ZipFile(temp, "w", allowZip64=False) as output:
                for entry in original.zip.infolist():
                    if entry.filename == "meta.json" or entry.filename == old_audio and (remove_audio or track is not None):
                        continue
                    if track is not None and entry.filename == meta["audio"]["file"]:
                        raise ValueError("New audio would replace a non-audio entry")
                    output.writestr(entry.filename, original.read(entry.filename), compress_type=zipfile.ZIP_STORED)
                if track is not None:
                    output.writestr(meta["audio"]["file"], track, compress_type=zipfile.ZIP_STORED)
                output.writestr("meta.json", json.dumps(meta, allow_nan=False, separators=(",", ":")).encode(), compress_type=zipfile.ZIP_DEFLATED)
            os.link(temp.name, destination)
        finally:
            Path(temp.name).unlink(missing_ok=True)
    return meta
