# SPDX-License-Identifier: Apache-2.0
"""Usage: python examples/encode.py /tmp/demo.tsog"""
import argparse
import numpy as np
from tsog import Scene, encode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    args = parser.parse_args()
    rng = np.random.default_rng(7)
    count = 4096
    positions = rng.normal(0, .15, (count, 3))
    scene = Scene(
        positions=positions,
        scales=np.full((count, 3), .01),
        quaternions=np.tile([1., 0., 0., 0.], (count, 1)),
        dc=(rng.random((count, 3))-.5)/.28209479177387814,
        opacity=np.full(count, .8),
        centers=np.linspace(0, 1, count),
        sigmas=np.full(count, .2),
        velocities=np.column_stack((np.zeros(count), np.full(count, .3), np.zeros(count))),
    )
    encode(scene, args.destination, playback={"duration": 5, "fps": 24, "loop": True}, workers=2)
    print(f"Wrote {count} continuous Gaussians to {args.destination}")


if __name__ == "__main__":
    main()
