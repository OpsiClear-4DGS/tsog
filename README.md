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
**[Play the example](https://opsiclear-4dgs.github.io/ftgs-player/examples/jensen-2m.html)** ·
[Acknowledgments](#acknowledgments)

| Supported content | Encoding |
| --- | --- |
| Static splats | Positions, anisotropic scales, wxyz rotations, opacity |
| Continuous 4DGS | Gaussian temporal opacity and optional linear translation |
| Frame sequences | Discrete per-Gaussian frame IDs |
| View-dependent color | SH degrees 0–3; shared higher-SH palette |
| Playback | Duration, FPS hint, 0.25–4× speed, loop default |
| Embedded audio | One track, synchronized to the scene's media clock |
| Compatibility | TSOG version 1 with playback profile 1; legacy Xiaomi v4 imports |

The format describes typed buffers, shapes and numeric conventions independently
of any array library. The Python core uses only the standard library; its optional
fast codec uses NumPy and Pillow and exposes decoded attributes through standard
`memoryview` buffers. The browser codec uses typed arrays. Position decoding uses
per-axis 16-bit lookup tables; SH stays in a shared palette instead of allocating
45 coefficients for every point. Encoding uses vectorized quantization and a
bounded WebP worker pool. Updating audio/defaults preserves every attribute
image byte. [Measured costs and limits](docs/PERFORMANCE.md).

## Format overview

TSOG represents geometry, appearance and time as aligned attribute images,
with metadata describing how to decode them. The following sections describe
the file set, metadata and encodings; the [full specification](spec/FORMAT.md)
defines the conformance requirements.

### 1. File set

A `.tsog` is a ZIP archive with a root `meta.json` and the files it references.
The names below are examples; `meta.json` supplies the actual names and order.

| Entry | Contents | Used image channels |
| --- | --- | --- |
| `meta.json` | Version, point count, ranges, codebooks and file references | — |
| `means_l.webp`, `means_u.webp` | Low/high bytes of quantized positions | RGB |
| `quats.webp` | Compressed rotation and omitted-component tag | RGBA |
| `scales.webp` | Indices into the log-scale codebook | RGB |
| `sh0.webp` | DC spherical harmonics and linear base opacity | RGBA |
| `shN_centroids.webp` | Optional shared higher-SH palette | RGB |
| `shN_labels.webp` | Optional per-point palette labels | RG |
| `timeline_l.webp`, `timeline_u.webp` | Optional temporal center/sigma or discrete frame ID | RG for continuous; R for discrete |
| `motion_l.webp`, `motion_u.webp` | Optional translation; high-byte image omitted for 8-bit motion | RGB |
| `audio/track.m4a` | Optional embedded soundtrack | — |

All attribute images are still, lossless WebP with raw RGBA8 values. Their bytes
must survive decoding without color conversion or alpha premultiplication.
Quantization can lose precision; WebP preserves the resulting integer codes.
ZIP supports STORE and DEFLATE, with length and CRC checks on consumed entries.

Per-point images share width `W` and height `H`. Point `i` uses pixel
`(i % W, floor(i / W))`, starting at the top left; `count <= W*H`, and padding
pixels are ignored. The SH centroid image has its own dimensions. Scene space
is right-handed, conventionally X right, Y up and Z back, with no prescribed
physical length unit.

### 2. Metadata — `meta.json`

| Member | Meaning |
| --- | --- |
| `version` | `1` for this first release; `4` is accepted for legacy Xiaomi imports. |
| `profile` | `{"id":"org.opsiclear.tsog-playback","version":1}` for new files. |
| `count` | Number of valid Gaussian rows, excluding image padding. |
| `means` | Three-axis signed-log `mins`/`maxs` and two low/high image references. |
| `quats` | One rotation image reference. |
| `scales`, `sh0` | Each has a scalar `codebook` and one image reference. |
| `shN` | Optional SH degree `bands`, palette `count`, scalar `codebook` and centroid/label references. |
| `timeline` | Optional discrete or continuous time metadata and two image references. |
| `temporal.means` | Optional velocity ranges of shape `[1][3]` and one or two image references. |
| `playback` | Optional duration in seconds, FPS, playback rate and loop default. |
| `audio` | Optional package-relative file, MIME type and initial volume. |

Scalar codebooks contain 1–256 finite values. Range endpoints can be equal for
constant attributes. File references resolve inside the archive; their order
matters. Legacy root `fps` is also accepted as a playback default.

### 3. Property encodings

Spatial properties use the following conventions, with R/G/B corresponding to
x/y/z or red/green/blue as appropriate:

| Property | Decoding |
| --- | --- |
| Position | Combine low/high bytes into 16-bit codes, interpolate in the signed-log range, then invert with `sign(n)*expm1(abs(n))`. |
| Orientation | Quaternion order is **wxyz**. RGB encodes the three retained components; `A-252` selects the omitted component. Reconstruct it and normalize. |
| Scale | Each channel indexes a log standard deviation: `sigma = exp(codebook[index])`. |
| DC color and opacity | RGB indexes DC SH coefficients; base opacity is linear `A/255`. Degree-zero color is `max(0, 0.5 + 0.28209479177387814*DC)`. |
| Higher SH | Degrees 1–3 use a shared palette with 3, 8 or 15 additional RGB coefficients. Each point's label is `R + 256*G`. |

A 16-bit code is always `q = low + 256*high`. Higher-SH palettes hold at most
65,536 entries. With `K=(bands+1)^2-1`, centroid dimensions are
`64*K` by `ceil(shN.count/64)`; a point's label selects its coefficient block.
The specification fixes the SH basis and coefficient order.

Temporal properties extend the spatial data:

| Timeline | Interpretation |
| --- | --- |
| Absent | Static geometry with unchanged base opacity. |
| `type: 0` | Discrete frame membership: `frame = min(N-1, floor(q/delta))`, where `delta=floor(65536/N)` and q comes from red. |
| `type: 1` | Continuous center and **linear positive temporal sigma**, from 16-bit red and green codes respectively. |

For continuous scenes, geometry time `t` spans 0…1. Optional velocity uses 8- or
16-bit RGB codes and is measured per normalized clip. The stored position is
anchored at each point's center time:

```text
dt = t - center
position(t) = basePosition + velocity * dt
opacity(t) = baseOpacity * exp(-0.5 * (dt / sigma)^2)
```

Timed playback maps media seconds `s` to `t=clamp(s/duration,0,1)`. Its speed multiplier
changes wall-time playback, not the clip's duration. One embedded audio track
starts at media second zero and follows seeking, pause, rate and looping.

### 4. Example `meta.json`

This valid metadata example describes one continuous Gaussian with constant
ranges and an optional soundtrack. A complete archive also needs the referenced
images and nonempty audio entry.

```json
{
  "version": 1,
  "profile": { "id": "org.opsiclear.tsog-playback", "version": 1 },
  "count": 1,
  "means": {
    "mins": [0, 0, 0], "maxs": [0, 0, 0],
    "files": ["means_l.webp", "means_u.webp"]
  },
  "quats": { "files": ["quats.webp"] },
  "scales": { "codebook": [-4.605170185988091], "files": ["scales.webp"] },
  "sh0": { "codebook": [0], "files": ["sh0.webp"] },
  "timeline": {
    "type": 1,
    "mins": [0.5, 0.2], "maxs": [0.5, 0.2],
    "files": ["timeline_l.webp", "timeline_u.webp"]
  },
  "temporal": {
    "means": {
      "mins": [[0, 1, 0]], "maxs": [[0, 1, 0]],
      "files": ["motion_l.webp", "motion_u.webp"]
    }
  },
  "playback": { "duration": 5, "fps": 24, "rate": 1, "loop": true },
  "audio": { "file": "audio/track.m4a", "mimeType": "audio/mp4", "volume": 1 }
}
```

### 5. Versioning and compatibility

This first release uses file `version: 1`, playback `profile.version: 1` and
toolkit/specification version `1.0.0`. New files require the profile ID
`org.opsiclear.tsog-playback`. Readers also accept Xiaomi's legacy `version: 4`
attribute layout, including files without a profile marker. An unmarked
version-1 file is rejected to avoid confusing formats with the same number.
PlayCanvas SOG version 2 is a separate format.
Unsupported versions fail explicitly. Optional annotations can be ignored, but
unknown temporal attributes are rejected to avoid silently discarding motion.
See the [compatibility guide](docs/COMPATIBILITY.md) and
[normative specification](spec/FORMAT.md) for exact limits and validation rules.

## Start

Python 3.10+; install from this checkout:

```bash
python -m pip install -e '.[codec,test]'
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
positions_buffer = scene.as_buffers()["positions"]
print(positions_buffer.format, positions_buffer.shape)  # 'f', (N, 3)
# Higher SH for point i: scene.sh_palette[scene.sh_labels[i]].
# Expand individual coefficients only where the consumer needs them.
```

Use `pip install .` for the core metadata, ZIP validation and packaging tools
without NumPy or Pillow. `decode`, `encode`, `evaluate` and `validate --full`
need the optional `[codec]` extra. `Scene` also accepts nested numeric sequences
or shaped buffers as encoder inputs; consumers can use its
[generic attribute buffers](docs/IMPLEMENTATION.md#generic-attribute-buffers).

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

## Acknowledgments

We thank the original authors and teams whose research and tools made this
project possible:

- **[FreeTimeGS](https://zju3dv.github.io/freetimegs/)** — Yifan Wang, Peishan Yang,
  Zhen Xu, Jiaming Sun, Zhanhua Zhang, Yong Chen, Hujun Bao, Sida Peng and Xiaowei
  Zhou. Their CVPR 2025 work provides the dynamic Gaussian representation used
  in the reconstruction behind our example. [Paper](https://arxiv.org/abs/2506.05348).
- **[Xiaomi Research TSOG](https://github.com/xiaomi-research/tsog)** — Shady Gmira,
  Evangelos Alexiou, Emmanouil Potetsianakis and Emmanuel Thomas. Their ICIP 2026
  work introduced TSOG and its temporal extension of SOG.
  [Paper](https://arxiv.org/abs/2607.28049).
- **[PlayCanvas](https://playcanvas.com/)** and its contributors — for the
  [SOG format](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/),
  [SplatTransform tools](https://github.com/playcanvas/splat-transform) and
  public format documentation that underpin the spatial encoding conventions.

Thank you for sharing the research, implementations and documentation that
allow others to build on this work. Please credit the original projects when
using their methods and tools.

## License

Xiaomi's implementation is BSD-3-Clause-Clear; PlayCanvas splat-transform is MIT.
Our new code, documentation and code examples are **Apache-2.0**; see [LICENSE](LICENSE)
and [NOTICE](NOTICE). No upstream codec or AGPL player source is bundled.
[Full attribution and dependency notices](docs/ATTRIBUTION.md).

[Slop Example](examples/README.md) started as a video generated with Grok using
a few prompts, then reconstructed into 4DGS through our
[4Danyone pipeline](https://github.com/OpsiClear-4DGS/sam3dbx4danyone).
Hope Jensen is okay with it.
