# Encoding and decoding

The [format](../spec/FORMAT.md) is normative. These independently authored
reference implementations demonstrate the supported profile; the renderer is
deliberately separate. The Python core supports 3.10+ and uses only the standard
library. The optional fast codec uses NumPy 2 and Pillow 11–12.
The browser example needs ES modules, `DecompressionStream('deflate-raw')`,
`createImageBitmap` and OffscreenCanvas WebGL2. Serve modules over HTTP(S).

## Python data model

Install with `python -m pip install -e '.[codec,test]'`. The public API is `Scene`,
`encode`, `decode`, `evaluate`, `validate`, `repackage`, `Archive`,
`validate_metadata`, `webp_dimensions` and `timing`.

| `Scene` attribute | Decoded layout | Meaning |
| --- | --- | --- |
| `positions` | float32 N×3 | Position at the point's temporal center |
| `scales` | float32 N×3 | Positive linear spatial sigma |
| `quaternions` | float32 N×4 | Normalized wxyz |
| `dc` | float32 N×3 | SH DC, not direct RGB |
| `opacity` | float32 N | Linear base opacity |
| `centers`, `sigmas` | float32 N each, optional | Continuous center / positive linear sigma |
| `velocities` | float32 N×3, optional | Translation per normalized clip |
| `frame_ids` | uint16 N, optional | Discrete membership; excludes continuous arrays |
| `sh_palette` | float32 C×K×3, optional | Shared additional SH, K=3/8/15 |
| `sh_labels` | uint16 N, optional | Index into `sh_palette` |
| `audio` | bytes or None | Original soundtrack bytes |
| `metadata` | dict | Original root metadata |

`Scene` is a backend-neutral record. Encoder inputs can be nested numeric
sequences or shaped buffer/array objects; the optional codec converts them to
its working arrays. The table describes the packed layout of decoded data,
not a requirement to use a particular array class.

`decode` consumes every referenced attribute and CRC-checks the soundtrack.
`include_audio=False` discards the audio after checking it. It does not render
or decode the audio codec. Default device limits are 10M points and 64M pixels
per image; adjust `max_points` / `max_image_pixels` for your environment.

```python
from tsog import decode, evaluate, timing

scene = decode("scene.tsog", include_audio=False)
position, opacity = evaluate(scene, 0.25)
print(timing(scene.metadata), scene.attribute_bytes)
# Keep the shared palette; fetching one point's AC values costs K×3 floats.
if scene.sh_palette is not None:
    ac_for_point_0 = scene.sh_palette[scene.sh_labels[0]]
```

`evaluate` accepts normalized time in [0,1]. Continuous points move from their
canonical center and fade with a Gaussian envelope. Discrete points are selected
by exact frame membership. Static points remain unchanged. No viewer cutoff or
opacity floor is inserted.

## Generic attribute buffers

Consumers can use the standard Python buffer protocol rather than NumPy's API:

```python
from tsog import decode  # Requires the optional [codec] extra.

scene = decode("scene.tsog")
view = scene.as_buffers()["positions"]
print(view.format, view.itemsize, view.shape)  # 'f', 4, (N, 3)
raw = view.cast("B")  # Byte view of the same storage; no copy.
```

Float attributes use native-endian float32 (`f`); frame IDs and palette labels
use native-endian uint16 (`H`). Views are read-only by default and retain their
storage owner. They are views, not immutable snapshots: changes through another
alias remain visible. Use `as_buffers(readonly=False)` to preserve the source
buffer's write permissions. A nested list is a valid encoding input but cannot
provide a packed view until converted to buffer-backed storage.

`Scene`, `Archive`, metadata/timing helpers, structural `validate` and `repackage`
work without NumPy or Pillow. `decode`, `encode`, `evaluate` and full decoded
validation use the optional codec. Browser consumers receive standard typed
arrays; native or WASM consumers can use the same attribute layout.

## Writing a scene

[encode.py](../examples/encode.py) is a runnable continuous example. Supply
linear positive scales, normalized-time sigma/motion and linear opacity.
Convert training logits/log scales before creating `Scene`; keep SH in its
original coefficient convention. For FTGS-like training output:

```python
scales = np.exp(log_scales)
opacity = 1 / (1 + np.exp(-opacity_logits))
sigma = np.exp(log_temporal_sigma)
# If training time is seconds and the clip lasts D seconds:
center_normalized = center_seconds / D
sigma_normalized = sigma_seconds / D
velocity_normalized = velocity_per_second * D
```

The encoder quantizes positions/timeline to 16 bits and motion to 8 or 16 bits.
It uses deterministic uniform scalar books by default. `codebooks={"scales":
book, "sh0": book, "shN": book}` accepts pre-trained books of 1–256 values;
indices use nearest scalar distance without changing the caller's index order.
The encoder does not train SH palettes. Supply `sh_palette` and aligned
`sh_labels` from your own optimizer; point `i` must refer to the same row across
all arrays. No silent point reordering or dropping occurs.

```python
from tsog import encode

encode(scene, "new.tsog", playback={"duration": 5, "fps": 24},
       motion_bits=16, workers=2, webp_method=4, width=2048)
```

WebP `method` is 0–6: higher values spend more encoder work seeking smaller
lossless output. It does not change quantized attributes. The pool allows 1–4
workers and bounds pending image buffers. ZIP stores WebP/audio without a
redundant DEFLATE pass; metadata uses DEFLATE. Temporary output is in the target
directory and becomes visible atomically through an exclusive hard link; this
requires a filesystem supporting hard links. Existing destinations fail.

Encoding can change reconstructed values through quantization. For a uniform
range `[a,b]`, code error is at most `(b-a)/(2*(2^bits-1))` in that domain.
Position error is measured after inverse signed-log; codebook and SH palette
error have their own bounds. Report semantic and render error against your
source before adopting a compression configuration. A round-trip test does not
establish reconstruction quality.

## Packaging without recompression

```python
from tsog import repackage

repackage("scene.tsog", "scene-audio.tsog", audio="track.m4a",
          playback={"duration": 5, "fps": 24, "rate": 1})
repackage("scene-audio.tsog", "scene-silent.tsog", remove_audio=True)
```

This preserves every attribute image byte, retained unknown metadata and unrelated
entries. It validates CRCs while copying. Audio bytes are not transcoded. Adding
audio to static content requires a declared duration. Discrete duration/FPS
must agree with N. `Scene.audio` encoding needs `metadata.audio` with an explicit
MIME type or a recognized filename; arbitrary audio bytes are not guessed.

## Browser decoder

The reusable entry is [web/codec.js](../web/codec.js). It has no npm dependency.
Typed arrays are flat and use the same field names/order as the Python table;
palette shape is given by `metadata.shN.count` and `K=(bands+1)^2-1`.

```js
import { decodeTSOG, mediaTiming } from './web/codec.js';

const response = await fetch('./scene.tsog');
if (!response.ok) throw new Error(`HTTP ${response.status}`);
const model = await decodeTSOG(await response.blob());
console.log(model.metadata.count, mediaTiming(model.metadata));
// Audio is an unchanged Blob; create/revoke an object URL when your host uses it.
```

`decodeAttributes(metadata, loadImage, options)` accepts an adapter returning
`{width,height,pixels:Uint8Array}` with raw RGBA8. This permits a native/WASM image
decoder without changing format math. It validates metadata and every used code,
but the caller remains responsible for ZIP checks and raw image fidelity.
`decodeTSOG` also checks ZIP records/CRCs and lossless WebP. Options include
`requireProfile`, `maxPoints`, `maxArchiveBytes`, `signal` and `onProgress`.
The default browser archive budget is 512 MiB, distinct from normative ZIP32 limits.

Use a module worker for a large scene; the complete host is
[browser.html](../examples/browser.html), and
[decode-worker.js](../web/decode-worker.js) transfers every typed-array buffer.
Transfer ownership rather than cloning 168 MB of arrays. Terminating the worker
cancels the standalone host's work and releases its temporary resources.
The decoder creates one native WebP framebuffer and releases it in `finally`.
It copies raw texels directly, without premultiplication or shader color changes.

## Optimization boundaries

- Precompute inverse position values for each 16-bit code per axis, not per point.
- Keep SH labels and the shared palette. The Slop Example uses about 167.8 MB
  for all decoded arrays; expanding its 45 AC floats per point alone needs 360 MB.
- Decode only a pair/group of source images at a time; release temporary raw pixels.
- Run independent WebP encoding in a bounded native worker pool.
- Do not recompress encoded attribute images when editing soundtrack/defaults.
- Renderers can upload palettes directly and sort temporally visible IDs, but
  visibility thresholds, sorting and GPU rendering are not file-format semantics.

Browser performance and support are verified in Chromium. No claim of universal
Safari/Firefox support, a WebGPU backend, a WASM codec, or an official compressed
streaming extension is made. [Measured performance](PERFORMANCE.md).

## Conformance and reproduction

```bash
python -m unittest discover -s tests -v
python tools/create-fixtures.py /tmp/tsog-fixtures
tsog validate examples/slop-example.tsog --full --require-profile
python tests/browser_codec.py --fixtures /tmp/tsog-fixtures --real
```

The tests use an independent analytic code vector, zero-alpha RGB, all supported
SH degrees, constant ranges, both motion depths, timeline types, ZIP descriptors,
malformed headers, CRC failures, byte-preserving audio edits, schema structure
and exclusive/atomic writes. Browser checks compare against Python attribute
values rather than only checking that a page loads. Example source/provenance
is kept separately from synthetic conformance data.
