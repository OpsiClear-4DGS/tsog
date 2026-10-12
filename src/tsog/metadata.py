# SPDX-License-Identifier: Apache-2.0
"""TSOG version 1 semantics, with explicit legacy Xiaomi v4 compatibility."""
import math
import re

PROFILE = {"id": "org.opsiclear.tsog-playback", "version": 1}
MAX_FLOAT = 3.4028234663852886e38
MIME = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "aac": "audio/aac",
        "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg",
        "wav": "audio/wav", "flac": "audio/flac", "webm": "audio/webm"}


def number(value, label, minimum=None, maximum=None, integer=False):
    if type(value) not in (int, float) or type(value) is float and not math.isfinite(value):
        raise ValueError(f"{label}: expected a finite number")
    if integer and (int(value) != value or abs(value) > 9007199254740991):
        raise ValueError(f"{label}: expected a safe integer")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{label}: outside allowed range")
    return value


def entry_name(name):
    if not isinstance(name, str) or not name or re.search(r"[\\\x00-\x1f:?#]", name):
        raise ValueError("Invalid package-relative entry name")
    if any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("Invalid entry path segment")
    return name


def group(meta, key, files, ranges=None, book=False):
    g = meta.get(key)
    if not isinstance(g, dict):
        raise ValueError(f"{key}: missing attribute group")
    names = g.get("files")
    if not isinstance(names, list) or len(names) not in files:
        raise ValueError(f"{key}: incorrect image count")
    for name in names:
        if entry_name(name) == "meta.json":
            raise ValueError("An attribute cannot reference meta.json")
    if len(set(names)) != len(names):
        raise ValueError(f"{key}: duplicate image reference")
    if ranges is not None:
        for k in ("mins", "maxs"):
            values = g.get(k)
            if not isinstance(values, list) or len(values) != ranges:
                raise ValueError(f"{key}.{k}: incorrect shape")
            for value in values:
                number(value, f"{key}.{k}", -MAX_FLOAT, MAX_FLOAT)
        if any(a > b for a, b in zip(g["mins"], g["maxs"])):
            raise ValueError(f"{key}: reversed range")
    if book:
        values = g.get("codebook")
        if not isinstance(values, list) or not 1 <= len(values) <= 256:
            raise ValueError(f"{key}: codebook length must be 1..256")
        for value in values:
            number(value, f"{key}.codebook", -MAX_FLOAT, MAX_FLOAT)
    return g


def validate_metadata(meta, require_profile=False):
    if not isinstance(meta, dict) or type(meta.get("version")) not in (int, float) or meta["version"] not in (1, 4):
        raise ValueError("Only TSOG version 1 and legacy Xiaomi version 4 are supported")
    profile = meta.get("profile")
    if "profile" in meta:
        if not isinstance(profile, dict) or profile.get("id") != PROFILE["id"] or type(profile.get("version")) not in (int, float) or profile["version"] != 1:
            raise ValueError("Unsupported playback profile")
    elif require_profile or meta["version"] == 1:
        raise ValueError("An explicit playback profile is required")
    number(meta.get("count"), "count", 1, integer=True)
    group(meta, "means", (2,), ranges=3)
    group(meta, "scales", (1,), book=True)
    group(meta, "quats", (1,))
    group(meta, "sh0", (1,), book=True)
    if "shN" in meta:
        g = group(meta, "shN", (2,), book=True)
        number(g.get("bands"), "shN.bands", 1, 3, integer=True)
        number(g.get("count"), "shN.count", 1, 65536, integer=True)
    if "timeline" in meta:
        timeline = meta["timeline"]
        if not isinstance(timeline, dict) or type(timeline.get("type")) not in (int, float):
            raise ValueError("Invalid timeline")
        if timeline["type"] == 0:
            group(meta, "timeline", (2,))
            n = number(timeline.get("N"), "timeline.N", 1, 65536, integer=True)
            if number(timeline.get("delta"), "timeline.delta", integer=True) != 65536 // n:
                raise ValueError("Invalid discrete timeline delta")
        elif timeline["type"] == 1:
            group(meta, "timeline", (2,), ranges=2)
            if timeline["mins"][1] <= 7.006492321624085e-46:
                raise ValueError("Temporal sigma must remain positive in float32")
        else:
            raise ValueError("Unsupported timeline type")
    if "temporal" in meta:
        temporal = meta["temporal"]
        if "timeline" not in meta or not isinstance(temporal, dict) or set(temporal) != {"means"}:
            raise ValueError("Only first-order temporal.means with a timeline is supported")
        motion = group(temporal, "means", (1, 2))
        for k in ("mins", "maxs"):
            if not isinstance(motion.get(k), list) or len(motion[k]) != 1:
                raise ValueError("Motion ranges must have shape [1][3]")
        group({"motion": {"files": motion["files"], "mins": motion["mins"][0], "maxs": motion["maxs"][0]}}, "motion", (1, 2), ranges=3)
    if "fps" in meta:
        if number(meta["fps"], "fps") <= 0:
            raise ValueError("FPS must be positive")
    playback = meta.get("playback", {})
    if not isinstance(playback, dict):
        raise ValueError("playback must be an object")
    for key in ("duration", "fps"):
        if key in playback and number(playback[key], key) <= 0:
            raise ValueError(f"{key} must be positive")
    if "rate" in playback:
        number(playback["rate"], "playback.rate", .25, 4)
    if "loop" in playback and type(playback["loop"]) is not bool:
        raise ValueError("playback.loop must be boolean")
    timing(meta)
    if "audio" in meta:
        audio = meta["audio"]
        if not isinstance(audio, dict):
            raise ValueError("audio must be an object")
        name = entry_name(audio.get("file"))
        if name == "meta.json" or name in attribute_names(meta):
            raise ValueError("Audio cannot share an attribute or metadata entry")
        audio_mime(audio)
        if "volume" in audio:
            number(audio["volume"], "audio.volume", 0, 1)
        if "timeline" not in meta and "duration" not in playback:
            raise ValueError("Static scenes with audio require playback.duration")
    return meta


def attribute_names(meta):
    names = set()
    for key in ("means", "scales", "quats", "sh0", "shN", "timeline"):
        if key in meta:
            names.update(meta[key]["files"])
    if "temporal" in meta:
        names.update(meta["temporal"]["means"]["files"])
    return names


def audio_mime(audio):
    if "mimeType" in audio:
        mime = audio["mimeType"]
        if not isinstance(mime, str) or not re.fullmatch(r"audio/[a-z0-9.+-]+", mime, re.I):
            raise ValueError("Invalid audio MIME type")
        return mime
    try:
        return MIME[audio["file"].rsplit(".", 1)[-1].lower()]
    except KeyError:
        raise ValueError("Unknown audio extension requires mimeType") from None


def timing(meta):
    p = meta.get("playback", {})
    fps = p.get("fps", meta.get("fps", 30))
    duration = p.get("duration")
    t = meta.get("timeline")
    if t is None:
        frames = 1
    elif t["type"] == 0:
        frames = t["N"]
        if duration is not None:
            if "fps" in p and abs(duration * fps - frames) > 1e-6 * frames:
                raise ValueError("Discrete playback FPS/duration mismatch")
            fps = frames / duration
        else:
            duration = frames / fps
    else:
        if duration is not None:
            number(duration*fps, "derived duration*FPS", 0, 9007199254740990)
        frames = max(2, math.floor(duration * fps + .5) + 1) if duration is not None else 300
        if duration is None:
            duration = (frames - 1) / fps
    number(frames, "derived frame count", 1, integer=True)
    if duration is not None:
        if number(duration, "derived duration") <= 0:
            raise ValueError("Invalid derived duration")
    if number(fps, "effective FPS") <= 0:
        raise ValueError("Invalid effective FPS")
    return {"frames": frames, "fps": fps, "duration": duration,
            "rate": p.get("rate", 1), "loop": p.get("loop", True)}
