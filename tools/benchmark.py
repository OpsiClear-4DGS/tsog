# SPDX-License-Identifier: Apache-2.0
"""Run isolated CPU decode/encode trials; store results outside the source tree."""
import argparse
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter

import numpy as np
import PIL
from tsog import Scene, decode, encode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", type=Path, default=Path(__file__).resolve().parents[1]/"examples/slop-example.tsog")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--encode-points", type=int, default=100000)
    p.add_argument("--output", type=Path)
    p.add_argument("--trial", choices=["decode", "encode"], help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.trial:
        if args.trial == "decode":
            start = perf_counter()
            model = decode(args.file)
            seconds = perf_counter()-start
            result = {"seconds": seconds, "points": model.count, "attribute_bytes": model.attribute_bytes,
                      "audio_bytes": len(model.audio or b"")}
        else:
            rng = np.random.default_rng(7)
            n = args.encode_points
            model = Scene(rng.normal(0, 1, (n, 3)), np.full((n, 3), .01), np.tile([1.,0,0,0], (n,1)),
                          rng.uniform(-1, 1, (n, 3)), np.full(n, .8),
                          centers=np.linspace(0, 1, n), sigmas=np.full(n, .1), velocities=rng.normal(0, .1, (n, 3)))
            with tempfile.TemporaryDirectory() as tmp:
                file = Path(tmp)/"encode.tsog"
                start = perf_counter()
                encode(model, file, playback={"duration": 5, "fps": 24}, workers=2, webp_method=4)
                seconds = perf_counter()-start
                result = {"seconds": seconds, "points": n, "bytes": file.stat().st_size}
        # Linux reports KiB; macOS reports bytes.
        result["peak_process_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform == "darwin" else 1024)
        print(json.dumps(result))
        return
    if args.runs < 1 or args.encode_points < 1:
        p.error("runs and point count must be positive")
    result = {"environment": {"platform": platform.platform(), "python": platform.python_version(), "numpy": np.__version__, "pillow": PIL.__version__,
                              "cpu": platform.processor(), "method": "fresh subprocesses; warm filesystem cache; no network, renderer or GPU upload"}}
    for mode in ("decode", "encode"):
        trials = []
        for _ in range(args.runs):
            command = [sys.executable, __file__, "--trial", mode, "--file", str(args.file), "--encode-points", str(args.encode_points)]
            trials.append(json.loads(subprocess.check_output(command, text=True)))
        result[mode] = {"median_seconds": statistics.median(t["seconds"] for t in trials), "runs": trials}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
