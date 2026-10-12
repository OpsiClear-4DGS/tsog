# Attribution and licensing

The new specification, codecs, tests, examples of code and tooling in this
repository are Apache-2.0. The complete license and attribution are in
[LICENSE](../LICENSE) and [NOTICE](../NOTICE).

The file format was introduced by **Shady Gmira, Evangelos Alexiou, Emmanouil
Potetsianakis and Emmanuel Thomas** at **Xiaomi Research** in
[TSOG: A Format For Temporally And Spatially Ordered Gaussians](https://arxiv.org/abs/2607.28049),
ICIP 2026. Its reference implementation is
[xiaomi-research/tsog](https://github.com/xiaomi-research/tsog), with
[BSD-3-Clause-Clear licensing](https://github.com/xiaomi-research/tsog/blob/a58102d0489a68c4f7e18e5e1ddaf613256417dd/LICENSE).
Our compatibility target is commit `a58102d0489a68c4f7e18e5e1ddaf613256417dd`.

Spatial attribute conventions come from
[PlayCanvas SOG](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/).
[PlayCanvas splat-transform](https://github.com/playcanvas/splat-transform)
is [MIT-licensed](https://github.com/playcanvas/splat-transform/blob/main/LICENSE).

These are credited format sources. Their implementation code, engine and build
dependencies are not redistributed here. This independent profile is not
endorsed by Xiaomi, the authors or PlayCanvas. The separate
[FTGS Player](https://github.com/OpsiClear-4DGS/ftgs-player) is AGPL-3.0-only;
linking to its hosted demo does not put its source into this toolkit.

## Installed dependencies

| Dependency | Purpose | License source |
| --- | --- | --- |
| NumPy | Vectorized quantization and attribute arrays | [BSD-3-Clause and bundled notices](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| Pillow | Native libwebp lossless RGBA I/O | [Pillow license and vendored library notices](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| jsonschema, optional | Draft 2020-12 conformance tests | [MIT](https://github.com/python-jsonschema/jsonschema/blob/main/COPYING) |

The dependency wheels carry their own notices, including native libraries.
They are installed by package management, not copied into this repository.
Browser examples use native ZIP inflation and WebP/WebGL2; no third-party JS,
font or UI code is included.

## Recorded media

The example model is a preserved reconstruction from generated multiview media,
with its original audio. No ownership or commercial clearance of that media is
asserted. Its filename/display label does not change its source provenance.
Its bytes and manifest are outside the Apache code license; see
[example provenance](../examples/README.md). The published Python wheel and sdist
exclude the model and soundtrack.
