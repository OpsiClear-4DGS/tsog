# Compatibility

| Producer / consumer | Relationship |
| --- | --- |
| Xiaomi Research TSOG at a58102d | Reference base-v4 layout; legacy files need not contain our profile marker |
| OpsiClear TSOG writer | Emits version 1 and playback profile 1; uniform or caller-supplied scalar books |
| FTGS Player | Separate AGPL reader/player supporting this profile and legacy v4 |
| PlayCanvas SOG | Spatial ancestry; SOG version 2 is distinct from OpsiClear TSOG 1 and Xiaomi TSOG 4 |

New files use `version: 1` and require the profile ID
`org.opsiclear.tsog-playback` with profile version 1. The toolkit and
specification are both `1.0.0`. Xiaomi's `version: 4` denotes its original
encoding, not a later OpsiClear release. Its supported attribute layout is
also accepted as a legacy import. Unmarked version-1 files are rejected.
The format is independent of NumPy or any other array library; implementations
can expose the defined attributes as typed buffers.

Do not change a SOG/PLY extension to make it temporal. Do not apply a sigmoid to
TSOG opacity, exponentiate temporal sigma, treat motion as units per second,
or decode quaternion tags as xyzw. These produce plausible-looking but wrong
data. Continuous base positions are anchored at each point's center time.

Degrees 1–3 use `K=3,8,15` AC coefficients and centroid widths `64*K`.
Per-point padding and palette padding are ignored; references and file ordering
come from metadata. An external encoder may use different filenames and ZIP
data descriptors. Both are supported.

Our profile retains normalized-time motion, discrete frames, higher SH and
embedded audio. It does not define animated rotation/scale/color, nonlinear
motion, multiple audio tracks, streaming chunks, training checkpoints, physical
units or capture-camera calibration. New required temporal features need a new
profile version. Camera bookmarks in the example's sidecar are presentation
data, not an undeclared core-format extension.

Existing player URLs and `jensen-2m` identifiers remain valid. The standalone
format repository names the model `slop-example.tsog` and displays it as
**Slop Example**. Version-1 packaging updates metadata and the container checksum;
attribute images and audio remain unchanged. Its manifest records the original
version-4 container checksum alongside the current checksum.
