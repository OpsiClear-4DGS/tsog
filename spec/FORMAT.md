# TSOG Version 1 — Format Specification

Specification release **1.0.0**, 2026-10-12. Maintainer: **OpsiClear-4DGS**.
Status: first release, file version **1**, playback profile **1**.
SPDX-License-Identifier: Apache-2.0.

## 1. Scope and conformance

This specification defines OpsiClear TSOG version 1, using a portable subset of
Xiaomi Research's v4 attribute layout and OpsiClear's playback/audio additions.
Readers also support legacy Xiaomi v4 imports. Its spatial encoding
follows PlayCanvas SOG conventions. It defines interchange semantics; camera
navigation, training, antialiasing, tone mapping and rendering hardware are
outside its scope. It does not claim support for every temporal parameterization
in the original research paper.

The keywords MUST, MUST NOT, SHOULD, SHOULD NOT and MAY specify requirements,
recommendations and choices. Sections 1–10 are normative. Implementation notes
and code examples are informative. A conforming reader supports every defined
attribute/timeline, or explicitly reports a capability/resource limitation.
A conforming writer emits the identifiers below and satisfies every byte,
metadata and cross-field requirement. Passing JSON Schema alone is insufficient.

```json
{"version":1,"profile":{"id":"org.opsiclear.tsog-playback","version":1}}
```

The root version identifies this file format; the profile identifies its playback
semantics. Version 1 MUST include the profile ID and version shown above.
Unsupported values and unmarked version-1 files MUST fail rather than be guessed.
Readers MUST also accept otherwise supported legacy Xiaomi `version: 4` files
without `profile`. Such a file is not a profile declaration; strict validators
MAY require an explicit marker.
Unknown optional metadata is ignored and SHOULD survive metadata-only edits.
Unknown keys inside `temporal` MUST fail: silently dropping animated attributes
would change the scene. An additive annotation may keep profile 1; a new required
behavior or changed interpretation requires a new profile version.

## 2. Container

Extension: `.tsog`. Transport: `application/zip`; no custom registered MIME type
is claimed. The ZIP contains exactly one root `meta.json`, its referenced WebP
images and an optional audio entry. A `.sog` archive is not a `.tsog` merely
because both contain WebP. Filenames are supplied by metadata, not fixed here.

```text
scene.tsog
  meta.json
  means_l.webp   means_u.webp
  scales.webp   quats.webp   sh0.webp
  timeline_l.webp   timeline_u.webp       # temporal scenes
  motion_l.webp   motion_u.webp           # optional translation
  shN_centroids.webp   shN_labels.webp     # optional higher SH
  audio/track.m4a                          # optional audio
```

ZIP32 STORE (0) and DEFLATE (8) MUST be supported. The central directory determines
offsets/sizes. Every consumed entry MUST pass uncompressed-size and CRC-32 checks.
ZIP64, encryption, split archives, duplicate names, overlapping records, truncated
data and conflicting local/central headers MUST fail. No entry is extracted or
executed as part of reading the format. Unreferenced entries MAY be ignored.

Without flag bit 3, local sizes and CRC MUST equal directory values. With bit 3,
local sizes/CRC MUST be zero and a matching trailing data descriptor is required;
both signed and unsigned descriptors are supported. See the
[PKWARE ZIP definition](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT).

References are literal case-sensitive UTF-8 names relative to the package root.
Names MUST be nonempty and MUST NOT include `\\`, control characters U+0000–001F,
`:`, `?`, `#`, empty path segments or `.`/`..` segments. No URL decoding, Unicode
normalization, network lookup or external filesystem resolution occurs.
Non-ASCII names require ZIP's UTF-8 flag. Attribute names MUST differ from
`meta.json`; a group's names MUST be distinct. Audio MUST use its own entry.

| Profile limit | Maximum |
| --- | ---: |
| ZIP entries | 1,024 |
| Central directory | 4 MiB |
| Uncompressed metadata | 4 MiB |
| Uncompressed attribute entry | 512 MiB |
| Audio entry | 128 MiB |
| WebP dimension per axis | 16,384 pixels |

MiB = 1,048,576 bytes. ZIP32 limits also apply. A reader may impose a lower
device budget, reported as a resource limitation rather than a format violation.

## 3. Metadata

`meta.json` is a UTF-8 JSON object. Writers MUST use unique keys. Readers MAY
reject duplicate keys or use the last value. Missing and `null` are different.
All numbers MUST be finite; integers MUST be exactly representable as JavaScript
safe integers. Ranges/codebooks MUST fit finite float32. Used decoded values,
including covariance, MUST remain finite when converted to float32.

| Member | Requirement |
| --- | --- |
| `version`, `profile` | Version 1 with profile 1; legacy Xiaomi version 4 imports as defined in §1 |
| `count` | Integer 1…9,007,199,254,740,991; actual non-padding points |
| `means` | `mins`/`maxs`: three numbers each; two files, low byte then high |
| `scales` | Scalar codebook; one file |
| `quats` | One file |
| `sh0` | Scalar codebook; one file |
| `shN` | Optional degree `bands` 1–3, palette `count` 1–65,536, codebook, two files: centroids then labels |
| `timeline` | Optional discrete or continuous definition in §7 |
| `temporal` | Optional first-order translation in §8 |
| `fps` | Optional legacy positive FPS default |
| `playback`, `audio` | Optional presentation fields in §§9–10 |

Each codebook contains 1–256 numbers. Used indices MUST be in bounds; there is
no rescaling for a short codebook. Each `mins[a] <= maxs[a]`; equal endpoints
are legal constants. No implied point sorting or codebook ordering exists.
The [schema](profile.schema.json) checks structure; archive and semantic checks
are additional requirements.

## 4. Attribute images and coordinates

Attribute images MUST contain exactly one still lossless WebP VP8L image.
An optional VP8X wrapper MUST agree with its dimensions. Lossy VP8, ALPH chunks,
animation and multiple images are unsupported. Decoder output is **raw RGBA8**:
no color management, gamma conversion, premultiplication, orientation transform
or alpha-dependent RGB destruction. Absent alpha means 255. Transparent RGB
must survive; ordinary premultiplied Canvas 2D readback is unsuitable.

Per-point images share `(W,H)` and `W*H >= count`. Point `i` maps to
`(i % W, floor(i/W))`, top-left origin, row-major. Padding after `count` is ignored.
Only the centroid image uses different dimensions (§6). Unused channels are ignored.

Scene space is consistently right-handed; conventional axes are X right, Y up,
Z back. A file does not define a preferred camera or physical length unit.
Reorientation must also transform SH directions. Spatial scale means Gaussian
standard deviation along each rotated principal axis. Time is normalized for
geometry; the soundtrack clock is in media seconds.

Notation: `mix(a,b,u)=a+(b-a)*u`; `L`/`H` are the low/high image pixels.
Two-byte codes are `L.channel + 256*H.channel`. R,G,B correspond to axes 0,1,2.

## 5. Spatial attributes

### 5.1 Position

```text
q[a] = L[a] + 256*H[a]
n[a] = mix(means.mins[a], means.maxs[a], q[a]/65535)
position[a] = sign(n[a]) * expm1(abs(n[a]))
```

`sign(0)=0`. Metadata endpoints live in signed-log space. Writers transform
positions with `sign(p)*log1p(abs(p))` before uniform 16-bit quantization.

### 5.2 Scale and rotation

Scales use `scale[a]=exp(scales.codebook[pixel[a]])`. Quaternion order is **wxyz**.
The quaternion alpha tag MUST be 252…255 and selects omitted component `A-252`.
The three remaining components, in wxyz order, are
`(2*RGB/255-1)/sqrt(2)`. Restore the omitted component as
`sqrt(max(0,1-sum(kept²)))`, insert it, then normalize the four-vector.

For normalized `(w,x,y,z)`, use:

```text
R = [1-2(y²+z²), 2(xy-wz),   2(xz+wy)
     2(xy+wz),   1-2(x²+z²), 2(yz-wx)
     2(xz-wy),   2(yz+wx),   1-2(x²+y²)]
covariance = R * diag(scale²) * transpose(R)
```

### 5.3 DC and opacity

R,G,B index `sh0.codebook`. They are SH DC coefficients, not direct RGB.
Base opacity is linear `A/255`; a reader MUST NOT apply a sigmoid.
For degree zero, color is `max(0,0.5 + 0.28209479177387814*DC)` per channel.
SH describes gamma-space color; the codes remain raw integers.

## 6. Higher spherical harmonics

Degree `d=shN.bands` has `K=(d+1)²-1` additional coefficients per channel.
The centroid image dimensions MUST be `(64*K, ceil(shN.count/64))`.
Widths for degrees 1,2,3 are **192,512,960**. A label is `R+256*G` and MUST be
less than the palette count. For label `l` and extra coefficient `k`:

```text
x = (l % 64)*K + k
y = floor(l/64)
coefficient[k+1].rgb = shN.codebook[centroid(x,y).rgb]
```

Let `(x,y,z)` be the normalized vector **from camera to current Gaussian center**
in scene space. A zero vector may use `(0,0,0)`. The coefficient basis is:

| Index | Basis |
| --- | --- |
| 0 | `0.28209479177387814` |
| 1 | `-0.4886025119029199*y` |
| 2 | `0.4886025119029199*z` |
| 3 | `-0.4886025119029199*x` |
| 4 | `1.0925484305920792*x*y` |
| 5 | `-1.0925484305920792*y*z` |
| 6 | `0.31539156525252005*(2*z*z-x*x-y*y)` |
| 7 | `-1.0925484305920792*x*z` |
| 8 | `0.5462742152960396*(x*x-y*y)` |
| 9 | `-0.5900435899266435*y*(3*x*x-y*y)` |
| 10 | `2.890611442640554*x*y*z` |
| 11 | `-0.4570457994644658*y*(4*z*z-x*x-y*y)` |
| 12 | `0.3731763325901154*z*(2*z*z-3*x*x-3*y*y)` |
| 13 | `-0.4570457994644658*x*(4*z*z-x*x-y*y)` |
| 14 | `1.445305721320277*z*(x*x-y*y)` |
| 15 | `-0.5900435899266435*x*(x*x-3*y*y)` |

Per-channel color is `max(0,0.5+sum(basis[j]*coefficient[j]))` through degree d.
No exposure correction is encoded. Readers SHOULD preserve the shared palette
instead of expanding all higher SH per point.

## 7. Timelines

Without `timeline`, the scene is static: no temporal opacity or motion.
`temporal` MUST then be absent. Static content may have a timed audio presentation.
Timeline numbering here follows the pinned Xiaomi **v4 encoder**, not an arbitrary
paper diagram or other codec revision.

### 7.1 Discrete — type 0

Require `N` in 1…65,536, `delta=floor(65536/N)` and two files, low/high.
Red encodes `q=L.R+256*H.R`; frame ID is `min(N-1,floor(q/delta))`.
A writer SHOULD encode `frame*delta+floor(delta/2)`. The Gaussian is visible only
in its assigned frame with base opacity; there is no interpolation or temporal
fade. A retained `temporal.means` is validated but has no geometric effect.

### 7.2 Continuous — type 1

Require two-number `mins`/`maxs` and low/high files. Red stores center and green
stores **linear temporal standard deviation**, not its logarithm or variance:

```text
center = mix(mins[0],maxs[0],(L.R+256*H.R)/65535)
sigma  = mix(mins[1],maxs[1],(L.G+256*H.G)/65535)
opacity(t) = baseOpacity * exp(-0.5*((t-center)/sigma)²)
```

The sigma range MUST remain positive in float32. Clip time runs 0…1; centers may
be outside that interval and MUST NOT be clamped. There is no hard lifespan cutoff
or encoded opacity floor. Other time units require converting center, sigma and
motion consistently before declaring this profile.

## 8. Motion

`temporal` may contain only `means`. Its ranges have shape `[1][3]`; its one or
two files encode 8-bit or 16-bit translation. R,G,B store velocity components:

```text
q[a] = one file ? L[a] : L[a]+256*H[a]
v[a] = mix(mins[0][a],maxs[0][a],q[a]/(one file ? 255 : 65535))
position(t) = position + v*(t-center)
```

Motion applies only to continuous scenes. The stored position is anchored at
that point's temporal center. Velocity is scene units per normalized clip.
Absent motion means zero velocity. Animated rotation, scale, color and higher
motion orders are not defined by this profile and MUST NOT be silently accepted.

## 9. Media timing and defaults

Optional `playback` members: positive `duration` in seconds, positive `fps`,
`rate` in 0.25…4 (default 1), and boolean `loop` (default true).
FPS defaults to `playback.fps`, then root `fps`, then 30. With default FPS F:

| Geometry | Display frame count M | Media duration D |
| --- | --- | --- |
| Continuous, declared D | `max(2,floor(D*F+0.5)+1)` | Declared D |
| Continuous, no D | 300 | `(M-1)/F` |
| Discrete | N | Declared D, else `N/F` |
| Static | 1 | Declared D, else untimed |

Derived values MUST be finite and frame counts MUST be safe integers. Discrete
content with both declared duration and playback FPS requires
`abs(D*F-N) <= 1e-6*N`; effective FPS is `N/D`. Legacy root FPS does not impose
that agreement. Continuous FPS is a sampling hint, not a restriction on evaluation.

At media second `s`, use `t=clamp(s/D,0,1)`. Discrete playback selects
`min(N-1,floor(t*N))`, including the last full frame interval. Continuous display
frame i uses `i/(M-1)`. Untimed static content has no advancing clock.
Wall-time advancement is multiplied by `rate`; D does not change. Looping wraps
the scene and soundtrack together; otherwise pause at D. Host overrides do not
alter the file. Autoplay and camera selection are host decisions.

## 10. Audio

Optional `audio` has required `file`, optional `mimeType`, and optional `volume`
in 0…1 (default 1). The entry MUST exist, be nonempty and have its own name.
An explicit MIME matches `audio/[A-Za-z0-9.+-]+`, with no parameters.
Absent MIME uses the final filename extension, case-insensitively:

| Extension | MIME |
| --- | --- |
| mp3 | audio/mpeg |
| m4a | audio/mp4 |
| aac | audio/aac |
| ogg, oga, opus | audio/ogg |
| wav | audio/wav |
| flac | audio/flac |
| webm | audio/webm |

An unknown extension requires explicit MIME. One soundtrack starts at media
second zero and follows scene seek, pause, rate and loop. Short audio leaves
silence; long audio stops at D. Audio length MUST NOT redefine D. Static scenes
with audio MUST declare duration. No per-track offset, mixing or independent
loop is defined. Codec support and autoplay permission are host capabilities;
silent fallback MUST be reported. Container validity does not guarantee codec
support or sample-accurate audiovisual latency.

## Informative references

- [Xiaomi Research TSOG v4 source revision a58102d](https://github.com/xiaomi-research/tsog/tree/a58102d0489a68c4f7e18e5e1ddaf613256417dd)
- [Gmira et al., TSOG, ICIP 2026](https://arxiv.org/abs/2607.28049)
- [PlayCanvas SOG](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/)
- [Implementation and conformance checks](../docs/IMPLEMENTATION.md)

This document is independently written. It supersedes the player repository's
description as this project's specification. Migrating a supported legacy v4
file to version 1 changes its metadata declaration and ZIP container; attribute
images and retained audio can remain byte-for-byte unchanged. No array library
is part of the format: implementations may use typed buffers with the specified
shapes and numeric conventions.
