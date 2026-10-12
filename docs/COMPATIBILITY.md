# Compatibility

| Producer / consumer | Relationship |
| --- | --- |
| Xiaomi Research TSOG at a58102d | Reference base-v4 layout; legacy files need not contain our profile marker |
| OpsiClear TSOG writer | Emits base v4 and playback profile 1; uniform or caller-supplied scalar books |
| FTGS Player | Separate AGPL reader/player supporting this profile and legacy v4 |
| PlayCanvas SOG | Spatial ancestry; SOG version 2 and TSOG version 4 are distinct encodings |

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
format repository names the same binary `slop-example.tsog` and displays it as
**Slop Example**. Its SHA-256 is unchanged.
