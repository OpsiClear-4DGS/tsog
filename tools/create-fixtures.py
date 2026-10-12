# SPDX-License-Identifier: Apache-2.0
"""Generate independent small vectors, raw bytes and decoded expectations."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"))
from support import scene, analytic, bundle
from tsog import decode, encode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for name in ("static", "discrete", "continuous8", "continuous16", "degree1", "degree2", "degree3", "analytic"):
        path = args.destination/f"{name}.tsog"
        if path.exists():
            raise FileExistsError(path)
        if name == "analytic":
            path.write_bytes(bundle(*analytic()))
        else:
            kind = name if name in ("static", "discrete") else "continuous"
            degree = int(name[-1]) if name.startswith("degree") else 0
            encode(scene(kind, degree), path, width=8, motion_bits=8 if name.endswith("8") else 16)
        decoded = decode(path)
        import numpy as np
        expected = {key: value.tolist() for key, value in vars(decoded).items() if isinstance(value, np.ndarray)}
        path.with_suffix(".json").write_text(json.dumps(expected, separators=(",", ":"))+"\n")
    print(f"Wrote eight synthetic vectors to {args.destination}")


if __name__ == "__main__":
    main()
