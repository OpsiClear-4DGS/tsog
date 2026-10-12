# OpsiClear TSOG

An independent **Apache-2.0** specification and reference toolkit for packaged
temporal Gaussian splats. A `.tsog` file carries compressed 3D/4D Gaussian
attributes, a timeline, playback defaults and an optional synchronized soundtrack.

Inspired by **Xiaomi Research's [TSOG](https://github.com/xiaomi-research/tsog)**,
by **Shady Gmira, Evangelos Alexiou, Emmanouil Potetsianakis and Emmanuel Thomas**,
and **[PlayCanvas SOG](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/)**.
The base attribute encoding follows Xiaomi's v4 output. OpsiClear's playback
profile adds explicit interoperability rules, media timing, audio, validation
and implementation guidance. This is not an official Xiaomi or PlayCanvas release.

**[File format](spec/FORMAT.md)** · **[JSON Schema](spec/profile.schema.json)** ·
**[Encode / decode](docs/IMPLEMENTATION.md)** · **[Slop Example](examples/README.md)** ·
**[Play the example](https://opsiclear-4dgs.github.io/ftgs-player/examples/jensen-2m.html)**

| Supported content | Encoding |
| --- | --- |
| Static splats | Positions, anisotropic scales, wxyz rotations, opacity |
| Continuous 4DGS | Gaussian temporal opacity and optional linear translation |
| Frame sequences | Discrete per-Gaussian frame IDs |
| View-dependent color | SH degrees 0–3; shared higher-SH palette |
| Playback | Duration, FPS hint, 0.25–4× speed, loop default |
| Embedded audio | One track, synchronized to the scene's media clock |
| Compatibility | Legacy v4 imports and explicit playback profile 1 |

The codec uses NumPy arrays and native lossless WebP. Position decoding uses
per-axis 16-bit lookup tables; SH stays in a shared palette instead of allocating
45 coefficients for every point. Encoding uses vectorized quantization and a
bounded WebP worker pool. Updating audio/defaults preserves every attribute
image byte. [Measured costs and limits](docs/PERFORMANCE.md).

## Start

Python 3.10+; install from this checkout:

```bash
python -m pip install -e '.[test]'
tsog validate examples/slop-example.tsog --full --require-profile
python examples/encode.py /tmp/demo.tsog
python examples/decode.py examples/slop-example.tsog
python -m unittest discover -s tests -v
```

```python
from tsog import decode, evaluate

scene = decode("scene.tsog")
positions, opacity = evaluate(scene, 0.5)
print(scene.count, scene.attribute_bytes)
# Higher SH for point i: scene.sh_palette[scene.sh_labels[i]].
# Expand individual coefficients only where the consumer needs them.
```

Add a soundtrack without decoding/re-encoding the splats:

```bash
tsog package scene.tsog scene-with-audio.tsog \
  --audio track.m4a --duration 5 --fps 24
```

`inspect` checks metadata and ZIP record headers. `validate` additionally checks
all referenced CRCs and lossless WebP dimensions. `validate --full` checks every
decoded attribute. It does not certify an audio codec or reconstruction quality.
Outputs are created atomically and existing files are never overwritten.

The encoder is a deterministic reference writer. It uses uniform scalar
codebooks unless you provide learned books; higher-SH clustering must be supplied
by the caller. It is not presented as a replacement for Xiaomi's compression
optimizer. Quantization is lossy; lossless WebP preserves the resulting codes.

## Browser example

The independent [browser example](examples/browser.html) decodes the example
off the UI thread and reports its compact arrays; it does not bundle a renderer.

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Open <http://localhost:8765/examples/browser.html>. The [FTGS Player](https://github.com/OpsiClear-4DGS/ftgs-player)
is a separate AGPL application that can play these files. Our Python and browser
reference codecs have no dependency on that player or its source code.

## Layout

```text
spec/       Normative format and machine-readable schema
src/tsog/   Python metadata, ZIP, codec and packaging tools
web/        Browser ZIP, raw WebP and compact attribute decoding
examples/   Encoding/decoding examples and preserved Slop Example data
tests/      Independent synthetic conformance and corruption tests
docs/       Implementation, compatibility, performance and attribution
tools/      Reproducible fixture and benchmark commands
```

## Attribution and license

The format's research origin is *[TSOG: A Format For Temporally And Spatially
Ordered Gaussians](https://arxiv.org/abs/2607.28049)*, ICIP 2026. Xiaomi's
implementation is BSD-3-Clause-Clear; PlayCanvas splat-transform is MIT.
Our new code, documentation and code examples are **Apache-2.0**; see [LICENSE](LICENSE)
and [NOTICE](NOTICE). No upstream codec or AGPL player source is bundled.

The recorded [Slop Example](examples/README.md) retains the source scene/media
and audio rights; it is **not Apache-licensed media**. The library distribution
excludes that 45 MB asset. [Full attribution and dependency notices](docs/ATTRIBUTION.md).
