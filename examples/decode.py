# SPDX-License-Identifier: Apache-2.0
"""Usage: python examples/decode.py examples/slop-example.tsog"""
import argparse
from time import perf_counter
import numpy as np
from tsog import decode, evaluate, timing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    args = parser.parse_args()
    started = perf_counter()
    scene = decode(args.source)
    elapsed = perf_counter()-started
    _, opacity = evaluate(scene, .5)
    print(f"{scene.count:,} points in {elapsed:.3f}s; {scene.attribute_bytes/1e6:.1f} MB of compact arrays")
    print(f"Media timing: {timing(scene.metadata)}")
    print(f"Visible at t=0.5 above 1/255: {np.count_nonzero(opacity >= 1/255):,}")
    if scene.sh_palette is not None:
        print(f"Shared SH palette: {scene.sh_palette.shape}; labels: {scene.sh_labels.dtype}")
    if scene.audio is not None:
        print(f"Embedded audio: {len(scene.audio):,} bytes")


if __name__ == "__main__":
    main()
