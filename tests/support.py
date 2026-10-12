# SPDX-License-Identifier: Apache-2.0
"""Independent deterministic synthetic vectors; no recorded upstream fixtures."""
from io import BytesIO
import json
import zipfile
import numpy as np
from PIL import Image
from tsog import Scene


def scene(kind="continuous", degree=0):
    count = 17
    i = np.arange(count, dtype=np.float64)
    result = Scene(np.column_stack((i/20-0.4, np.sin(i)/10, np.cos(i)/10)),
                   np.column_stack((.02+i/1000, .03+i/1000, .04+i/1000)),
                   np.column_stack((np.cos(i), np.sin(i), i*0, i*0)),
                   np.column_stack((i/20-.3, i*0+.25, -i/20)),
                   np.linspace(0, 1, count))
    if kind == "continuous":
        result.centers = np.linspace(-.1, 1.1, count)
        result.sigmas = np.linspace(.1, .3, count)
        result.velocities = np.column_stack((i/20, -i/20, i*0+.1))
    elif kind == "discrete":
        result.frame_ids = (i % 3).astype(np.uint16)
        result.metadata["timeline"] = {"N": 3}
    if degree:
        k = (degree+1)**2-1
        result.sh_palette = np.linspace(-.4, .4, 5*k*3).reshape(5, k, 3)
        result.sh_labels = (i % 5).astype(np.uint16)
    return result


def webp(pixels, width=None):
    pixels = np.asarray(pixels, np.uint8)
    pixels = pixels.reshape(1, -1, 4) if width is None else pixels.reshape(-1, width, 4)
    output = BytesIO()
    Image.fromarray(pixels).save(output, format="WEBP", lossless=True, exact=True)
    return output.getvalue()


def bundle(meta, entries):
    result = BytesIO()
    with zipfile.ZipFile(result, "w") as z:
        z.writestr("meta.json", json.dumps(meta))
        for name, value in entries.items():
            z.writestr(name, value)
    return result.getvalue()


def analytic():
    meta = {"version": 4, "count": 1,
            "means": {"mins": [-1, 0, 1], "maxs": [1, 0, 2], "files": ["lo.webp", "hi.webp"]},
            "scales": {"codebook": [float(np.log(.1)), float(np.log(.2))], "files": ["scale.webp"]},
            "quats": {"files": ["q.webp"]},
            "sh0": {"codebook": list(range(256)), "files": ["dc.webp"]},
            "timeline": {"type": 1, "mins": [.25, .1], "maxs": [.75, .2], "files": ["tl.webp", "th.webp"]},
            "temporal": {"means": {"mins": [[-1, -2, -3]], "maxs": [[1, 2, 3]], "files": ["motion.webp"]}}}
    pixels = {"lo.webp": [0, 0, 255, 255], "hi.webp": [0, 0, 255, 255],
              "scale.webp": [0, 1, 0, 255], "q.webp": [128, 128, 128, 255],
              "dc.webp": [23, 45, 67, 0], "tl.webp": [0, 255, 0, 255],
              "th.webp": [0, 255, 0, 255], "motion.webp": [255, 0, 128, 255]}
    return meta, {name: webp([pixel]) for name, pixel in pixels.items()}
