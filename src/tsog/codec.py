# SPDX-License-Identifier: Apache-2.0
"""Vectorized attribute decoding and a deterministic scalar-quantization writer.

Higher SH stays in a shared palette. The writer accepts a trained palette and
labels; it intentionally does not invent a clustering or training algorithm.
"""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import math
import os
from pathlib import Path
import tempfile
import json
import zipfile

import numpy as np
from PIL import Image

from .archive import Archive, webp_dimensions
from .metadata import PROFILE, MAX_FLOAT, validate_metadata, number, audio_mime
from .model import Scene


def _f32(values, label, positive=False):
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        result = np.asarray(values, dtype=np.float32)
    if not np.isfinite(result).all() or positive and (result <= 0).any():
        raise ValueError(f"{label}: non-finite or non-positive decoded value")
    return result


def _check_covariance(scales, quaternions):
    # Normal-sized scenes cannot overflow covariance. Check exceptional rows only.
    indices = np.any(scales > math.sqrt(MAX_FLOAT/4), axis=1)
    if not indices.any():
        return
    w, x, y, z = quaternions[indices].astype(np.float64).T
    rotation = ((1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)),
                (2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)),
                (2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)))
    variance = np.square(scales[indices].astype(np.float64)).T
    for row in range(3):
        for col in range(row, 3):
            component = sum(rotation[row][axis]*rotation[col][axis]*variance[axis] for axis in range(3))
            _f32(component, "covariance")


def _quaternions(pixels):
    if (pixels[:, 3] < 252).any():
        raise ValueError("Invalid smallest-three quaternion tag")
    kept = (2*pixels[:, :3].astype(np.float64)/255-1)/math.sqrt(2)
    omitted = pixels[:, 3]-252
    missing = np.sqrt(np.maximum(0, 1-np.square(kept).sum(axis=1)))
    values = np.empty((len(pixels), 4), np.float64)
    rows = np.arange(len(pixels))
    for component in range(4):
        is_missing = omitted == component
        values[is_missing, component] = missing[is_missing]
        others = ~is_missing
        values[others, component] = kept[rows[others], component-(omitted[others] < component)]
    values /= np.linalg.norm(values, axis=1)[:, None]
    return _f32(values, "quaternion")


def decode(source, *, include_audio=True, max_points=10_000_000, max_image_pixels=64_000_000):
    """Decode into float32 arrays, with uint16 SH labels and no SH expansion."""
    with Archive(source) as archive:
        meta = archive.meta
        count = int(meta["count"])
        if count > max_points:
            raise ValueError("Device/resource limit: point count exceeds max_points")
        shape = None

        def image(name, per_point=True):
            nonlocal shape
            data = archive.read(name)
            dimensions = webp_dimensions(data)
            w, h = dimensions
            if w*h > max_image_pixels:
                raise ValueError("Device/resource limit: decoded image is too large")
            if per_point:
                if w*h < count or shape is not None and shape != dimensions:
                    raise ValueError("Per-Gaussian image dimension mismatch")
                shape = dimensions
            with Image.open(BytesIO(data)) as im:
                if im.size != dimensions:
                    raise ValueError("Decoded WebP size mismatch")
                # libwebp/Pillow supplies unassociated RGBA, including zero-alpha RGB.
                pixels = np.asarray(im.convert("RGBA"), dtype=np.uint8).reshape(-1, 4).copy()
            return pixels[:count] if per_point else pixels

        def codes(group):
            low = image(group["files"][0]).astype(np.uint16)
            return low if len(group["files"]) == 1 else low + 256*image(group["files"][1]).astype(np.uint16)

        def indexed(pixels, book, label):
            if pixels.size and int(pixels.max()) >= len(book):
                raise ValueError(f"{label}: codebook index out of range")
            return np.asarray(book, dtype=np.float64)[pixels]

        encoded = codes(meta["means"])
        positions = np.empty((count, 3), np.float32)
        for axis in range(3):
            lo, hi = meta["means"]["mins"][axis], meta["means"]["maxs"][axis]
            domain = lo+(hi-lo)*(np.arange(65536, dtype=np.float64)/65535)
            with np.errstate(over="ignore", invalid="ignore"):
                table = np.sign(domain)*np.expm1(np.abs(domain))
            # Only used values must be representable; unused LUT extremes can overflow.
            positions[:, axis] = _f32(table[encoded[:, axis]], "position")
        del encoded
        with np.errstate(over="ignore", under="ignore"):
            scales = _f32(np.exp(indexed(image(meta["scales"]["files"][0])[:, :3], meta["scales"]["codebook"], "scale")), "scale", True)
        pixels = image(meta["quats"]["files"][0])
        quaternions = np.empty((count, 4), np.float32)
        for start in range(0, count, 65536):
            quaternions[start:start+65536] = _quaternions(pixels[start:start+65536])
        _check_covariance(scales, quaternions)
        del pixels
        sh0 = image(meta["sh0"]["files"][0])
        dc = _f32(indexed(sh0[:, :3], meta["sh0"]["codebook"], "DC"), "DC")
        opacity = sh0[:, 3].astype(np.float32)/255
        scene = Scene(positions, scales, quaternions, dc, opacity, metadata=meta)
        if "timeline" in meta:
            group = meta["timeline"]
            q = codes(group)
            if group["type"] == 0:
                scene.frame_ids = np.minimum(group["N"]-1, q[:, 0]//group["delta"]).astype(np.uint16)
            else:
                decoded = np.asarray(group["mins"])+(np.asarray(group["maxs"])-group["mins"])*(q[:, :2].astype(np.float64)/65535)
                scene.centers = _f32(decoded[:, 0], "center")
                scene.sigmas = _f32(decoded[:, 1], "sigma", True)
            del q
        if "temporal" in meta:
            group = meta["temporal"]["means"]
            q = codes(group)
            maximum = 255 if len(group["files"]) == 1 else 65535
            values = np.asarray(group["mins"][0])+(np.asarray(group["maxs"][0])-group["mins"][0])*(q[:, :3].astype(np.float64)/maximum)
            velocity = _f32(values, "velocity")
            if scene.centers is not None:
                scene.velocities = velocity
            del q, velocity
        if "shN" in meta:
            group = meta["shN"]
            k = (int(group["bands"])+1)**2-1
            palette_count = int(group["count"])
            data = archive.read(group["files"][0])
            if webp_dimensions(data) != (64*k, math.ceil(palette_count/64)):
                raise ValueError("SH centroid image dimension mismatch")
            palette = image(group["files"][0], False)[:palette_count*k, :3]
            scene.sh_palette = _f32(indexed(palette, group["codebook"], "SH palette"), "SH palette").reshape(palette_count, k, 3)
            label_pixels = image(group["files"][1]).astype(np.uint16)
            scene.sh_labels = label_pixels[:, 0]+256*label_pixels[:, 1]
            if (scene.sh_labels >= group["count"]).any():
                raise ValueError("SH palette label out of range")
        if "audio" in meta:
            # Consume and CRC-check audio even if the caller does not retain it.
            track = archive.read(meta["audio"]["file"], 128*1048576)
            scene.audio = track if include_audio else None
        return scene


def evaluate(scene, time):
    """Return positions and linear opacity at normalized time in [0,1]."""
    number(time, "time", 0, 1)
    positions, opacity = np.asarray(scene.positions), np.asarray(scene.opacity)
    if scene.frame_ids is not None:
        n = scene.metadata["timeline"]["N"]
        selected = min(n-1, math.floor(time*n))
        return positions, opacity*(np.asarray(scene.frame_ids) == selected)
    if scene.centers is None:
        return positions, opacity
    dt = time-np.asarray(scene.centers)
    positions = positions if scene.velocities is None else positions+np.asarray(scene.velocities)*dt[:, None]
    opacity = opacity*np.exp(-.5*np.square(dt/np.asarray(scene.sigmas)))
    return positions, opacity


def _array(value, shape, label):
    data = np.asarray(value, dtype=np.float64)
    if data.shape != shape or not np.isfinite(data).all():
        raise ValueError(f"{label}: expected finite array with shape {shape}")
    _f32(data, label)
    return data


def _range(values, bits):
    lo, hi = values.min(axis=0), values.max(axis=0)
    span = hi-lo
    normalized = np.divide(values-lo, span, out=np.zeros_like(values), where=span != 0)
    q = np.rint(np.clip(normalized, 0, 1)*((1 << bits)-1)).astype(np.uint16)
    return q, lo.tolist(), hi.tolist()


def _book(values, provided=None):
    if provided is None:
        lo, hi = float(values.min()), float(values.max())
        book = np.linspace(lo, hi, 256) if hi != lo else np.asarray([lo])
        indices = np.zeros(values.shape, np.uint8) if hi == lo else np.rint(np.clip((values-lo)/(hi-lo), 0, 1)*255).astype(np.uint8)
    else:
        book = np.asarray(provided, dtype=np.float64)
        if book.ndim != 1 or not 1 <= len(book) <= 256 or not np.isfinite(book).all():
            raise ValueError("Invalid supplied codebook")
        order = np.argsort(book, kind="stable")
        sorted_book = book[order]
        right = np.clip(np.searchsorted(sorted_book, values), 0, len(book)-1)
        left = np.maximum(0, right-1)
        chosen = np.where(np.abs(values-sorted_book[left]) <= np.abs(values-sorted_book[right]), left, right)
        indices = order[chosen].astype(np.uint8)
    _f32(book, "codebook")
    return indices, book.tolist()


def encode(scene, destination, *, playback=None, codebooks=None, motion_bits=16,
           width=2048, workers=2, webp_method=4):
    """Write a new archive atomically; never overwrite an existing file.

    Scalar books use uniform quantization unless supplied. SH palette clustering
    is the caller's responsibility. Quantization is lossy; WebP and ZIP are not.
    """
    count = scene.count
    if count < 1 or motion_bits not in (8, 16) or type(width) is not int or not 1 <= width <= 16384:
        raise ValueError("Invalid count, motion bit depth or image width")
    if type(workers) is not int or not 1 <= workers <= 4 or type(webp_method) is not int or not 0 <= webp_method <= 6:
        raise ValueError("workers must be 1..4 and webp_method 0..6")
    width = min(width, count)
    height = math.ceil(count/width)
    if height > 16384:
        raise ValueError("WebP image height exceeds 16384")
    destination = Path(destination)
    if destination.suffix.lower() != ".tsog" or destination.exists():
        raise ValueError("Destination must be a new .tsog file")
    positions = _array(scene.positions, (count, 3), "positions")
    scales = _array(scene.scales, (count, 3), "scales")
    if (scales <= 0).any():
        raise ValueError("Spatial scales must be positive")
    _f32(scales, "scale", True)
    rotations = _array(scene.quaternions, (count, 4), "quaternions").copy()
    lengths = np.linalg.norm(rotations, axis=1)
    if (lengths == 0).any():
        raise ValueError("Zero-length quaternion")
    rotations /= lengths[:, None]
    dc = _array(scene.dc, (count, 3), "DC")
    alpha = _array(scene.opacity, (count,), "opacity")
    if ((alpha < 0) | (alpha > 1)).any():
        raise ValueError("Opacity must be linear in [0,1]")
    codebooks = codebooks or {}
    meta = {"version": 1, "profile": dict(PROFILE), "count": count,
            "asset": {"generator": "opsiclear-tsog 1.0.0"}}
    if playback is not None or "playback" in scene.metadata:
        meta["playback"] = dict(playback if playback is not None else scene.metadata["playback"])
    if "fps" in scene.metadata:
        meta["fps"] = scene.metadata["fps"]
    temp = tempfile.NamedTemporaryFile(prefix=".tsog-", dir=destination.parent, delete=False)
    pending = []
    try:
        with temp, zipfile.ZipFile(temp, "w", allowZip64=False) as archive, ThreadPoolExecutor(max_workers=workers) as pool:
            def flush():
                name, future = pending.pop(0)
                archive.writestr(name, future.result(), compress_type=zipfile.ZIP_STORED)

            def webp(pixels):
                output = BytesIO()
                Image.fromarray(pixels).save(output, format="WEBP", lossless=True, exact=True, method=webp_method)
                return output.getvalue()

            def emit(name, channels, w=width, h=height):
                while len(pending) >= workers:
                    flush()
                image = np.zeros((w*h, 4), dtype=np.uint8)
                image[:, 3] = 255
                flat = np.asarray(channels, dtype=np.uint8).reshape(-1, channels.shape[-1])
                image[:len(flat), :flat.shape[1]] = flat
                pending.append((name, pool.submit(webp, image.reshape(h, w, 4))))

            def ranged(key, values, bits=16):
                q, lo, hi = _range(values, bits)
                files = [f"{key}_l.webp"]
                emit(files[0], (q & 255).astype(np.uint8))
                if bits == 16:
                    files.append(f"{key}_u.webp")
                    emit(files[1], (q >> 8).astype(np.uint8))
                return {"mins": lo, "maxs": hi, "files": files}

            meta["means"] = ranged("means", np.sign(positions)*np.log1p(np.abs(positions)))
            indices, book = _book(np.log(scales), codebooks.get("scales"))
            with np.errstate(over="ignore", under="ignore"):
                decoded_scales = _f32(np.exp(np.asarray(book)[indices]), "quantized scale", True)
            meta["scales"] = {"codebook": book, "files": ["scales.webp"]}
            emit("scales.webp", indices)
            omitted = np.argmax(np.abs(rotations), axis=1)
            rotations *= np.where(rotations[np.arange(count), omitted] < 0, -1, 1)[:, None]
            mask = np.arange(4)[None, :] != omitted[:, None]
            kept = rotations[mask].reshape(count, 3)
            pixels = np.empty((count, 4), np.uint8)
            pixels[:, :3] = np.rint(np.clip((kept*math.sqrt(2)+1)*127.5, 0, 255)).astype(np.uint8)
            pixels[:, 3] = 252+omitted
            if (decoded_scales > math.sqrt(MAX_FLOAT/4)).any():
                _check_covariance(decoded_scales, _quaternions(pixels))
            del decoded_scales
            meta["quats"] = {"files": ["quats.webp"]}
            emit("quats.webp", pixels)
            indices, book = _book(dc, codebooks.get("sh0"))
            pixels[:, :3] = indices
            pixels[:, 3] = np.rint(alpha*255).astype(np.uint8)
            meta["sh0"] = {"codebook": book, "files": ["sh0.webp"]}
            emit("sh0.webp", pixels)
            if scene.centers is not None or scene.sigmas is not None:
                if scene.frame_ids is not None:
                    raise ValueError("A scene cannot have both continuous and discrete timelines")
                center = _array(scene.centers, (count,), "centers")
                sigma = _array(scene.sigmas, (count,), "sigmas")
                _f32(sigma, "sigma", True)
                meta["timeline"] = {"type": 1, **ranged("timeline", np.column_stack((center, sigma)))}
            elif scene.frame_ids is not None:
                ids = _array(scene.frame_ids, (count,), "frame_ids")
                n = scene.metadata.get("timeline", {}).get("N", int(ids.max())+1)
                number(n, "timeline.N", 1, 65536, integer=True)
                if (ids < 0).any() or (ids >= n).any() or (ids != np.floor(ids)).any():
                    raise ValueError("Invalid discrete frame IDs")
                delta = 65536//n
                q = (ids*delta+delta//2).astype(np.uint16)[:, None]
                files = ["timeline_l.webp", "timeline_u.webp"]
                emit(files[0], (q & 255).astype(np.uint8))
                emit(files[1], (q >> 8).astype(np.uint8))
                meta["timeline"] = {"type": 0, "N": int(n), "delta": delta, "files": files}
            if scene.velocities is not None:
                if scene.centers is None:
                    raise ValueError("The writer accepts motion only for a continuous timeline")
                g = ranged("motion", _array(scene.velocities, (count, 3), "velocity"), motion_bits)
                g["mins"], g["maxs"] = [g["mins"]], [g["maxs"]]
                meta["temporal"] = {"means": g}
            if scene.sh_palette is not None or scene.sh_labels is not None:
                palette = np.asarray(scene.sh_palette, dtype=np.float64)
                if palette.ndim != 3 or palette.shape[2] != 3 or palette.shape[1] not in (3, 8, 15) or not 1 <= len(palette) <= 65536:
                    raise ValueError("Invalid SH palette shape")
                palette = _array(palette, palette.shape, "SH palette")
                labels = _array(scene.sh_labels, (count,), "SH labels")
                if (labels < 0).any() or (labels >= len(palette)).any() or (labels != np.floor(labels)).any():
                    raise ValueError("Invalid SH labels")
                k = palette.shape[1]
                indices, book = _book(palette, codebooks.get("shN"))
                emit("shN_centroids.webp", indices.reshape(-1, 3), 64*k, math.ceil(len(palette)/64))
                q = labels.astype(np.uint16)
                emit("shN_labels.webp", np.column_stack((q & 255, q >> 8)).astype(np.uint8))
                meta["shN"] = {"bands": {3: 1, 8: 2, 15: 3}[k], "count": len(palette), "codebook": book,
                               "files": ["shN_centroids.webp", "shN_labels.webp"]}
            if scene.audio is not None:
                if not isinstance(scene.audio, bytes) or not 0 < len(scene.audio) <= 128*1048576:
                    raise ValueError("Audio must be nonempty bytes of at most 128 MiB")
                original = scene.metadata.get("audio", {})
                if not original:
                    raise ValueError("Audio bytes require metadata.audio with a MIME type or known filename")
                meta["audio"] = {"file": "audio/track.bin", "mimeType": audio_mime(original),
                                 "volume": original.get("volume", 1)}
                archive.writestr(meta["audio"]["file"], scene.audio, compress_type=zipfile.ZIP_STORED)
            validate_metadata(meta, require_profile=True)
            while pending:
                flush()
            archive.writestr("meta.json", json.dumps(meta, allow_nan=False, separators=(",", ":")).encode(), compress_type=zipfile.ZIP_DEFLATED)
        os.link(temp.name, destination)  # exclusive, atomic publication on the same filesystem
    finally:
        Path(temp.name).unlink(missing_ok=True)
    return meta
