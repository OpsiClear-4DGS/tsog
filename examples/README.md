# Slop Example and codec examples

[Download Slop Example](slop-example.tsog) ·
[Manifest / camera / checksum](slop-example.json) ·
[Play the scene](https://opsiclear-4dgs.github.io/ftgs-player/examples/jensen-2m.html)

The source video was generated with Grok using a few prompts, then reconstructed
into 4DGS through our
[4Danyone pipeline](https://github.com/OpsiClear-4DGS/sam3dbx4danyone).
Hope Jensen is okay with it.

The retained 2,000,000-point reconstruction contains degree-3 SH, 65,536 shared
centroids, 121 source timestamps at 24 fps, five seconds of continuous animation
and one embedded M4A track. Version-1 container size: **45,092,406 bytes**.

```text
SHA-256 7448cb911937cf4570c94e24c1002fdf6d16eb7594c35ebc0fa3f47c303640bc
```

Its attribute images and audio are byte-for-byte those of `jensen-2m.tsog` from
[sam3dbx4danyone](https://github.com/OpsiClear-4DGS/sam3dbx4danyone):
Original Base36 Jensen, 2M zero-velocity cold initialization, original 1M
movement units, fitting seed 2042; checkpoint checksum and study are in the
manifest. Slop Example is its display name. The source dataset name is retained
for reproducible provenance. Only the format declaration and ZIP packaging were
updated for version 1; all decoded attributes are unchanged. The manifest also
records the original version-4 container checksum.

This is generated multiview reconstruction data, not a captured physical ground
truth or reference geometry. Its media and audio retain original rights;
**no Apache media license or commercial clearance is granted**. The example is
excluded from library distributions. Apache-2.0 covers the code examples below.

| Example | Purpose |
| --- | --- |
| [encode.py](encode.py) | Write a continuous synthetic scene with vectorized quantization |
| [decode.py](decode.py) | Read compact arrays and evaluate one normalized time |
| [browser.html](browser.html) | Native browser ZIP/WebP decode in a module worker |

The browser example is a codec demonstration, not a second player. Use the
separate FTGS Player link above to inspect the full 4D scene.
