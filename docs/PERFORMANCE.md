# Reference codec performance

Measured 2026-10-12 on Linux x86-64, **Intel Xeon Gold 6448Y**, Python 3.12.3,
NumPy 2.5.4 and Pillow 12.3.0. Python values are medians of three fresh subprocesses
with warm filesystem cache. The optional browser run uses Chromium
153.0.8010.12, headless SwiftShader. No network, training or scene rendering is
included in decode times.

These measurements used the original version-4 example container. The version-1
release updates metadata/ZIP packaging only; every encoded image, audio byte
and decoded attribute hash was verified unchanged.

| Operation | Input | Time | Memory / output |
| --- | --- | ---: | --- |
| Python full attribute decode and referenced CRC checks | Slop Example, 2M points, degree-3 SH, audio | **0.922 s** | 167.8 MB arrays; ~376 MB process peak |
| Browser worker decode | Same example | **1.420 s**, one run | 167.8 MB transferable arrays |
| Python reference encode | 100k synthetic continuous points, SH0, 16-bit motion, 2 workers, WebP method 4 | **0.143 s** | 1.454 MB output; ~114 MB process peak |

These are different operations on different workloads. The 100k synthetic encode
time must not be extrapolated to a trained 2M degree-3 scene. This writer accepts
an existing SH palette rather than benchmarking palette training. Peak process
memory includes Python/native buffers and temporary images; it is not just array
size. Browser timing includes native WebP/framebuffer readback, but not the model
download, array transfer, rendering upload or subsequent drawing.

## Why the layout matters

The example has 65,536 centroids with 15 additional RGB coefficients each.
Expanding its higher SH to all 2M points would allocate **360 MB for AC alone**.
The shared palette needs 11,796,480 bytes and uint16 point labels need 4,000,000.
All decoded arrays, including positions, scales, rotations, DC, opacity, temporal
parameters, motion and SH, total **167,796,480 bytes**. Audio is another 118,113
unchanged bytes. Python and JavaScript use the same compact representation.

Per-axis signed-log lookup tables replace millions of repeated exponentials.
Quaternion decoding uses 65,536-point vectorized batches to bound scratch space.
Attribute groups are consumed in sequence, and WebP writing bounds pending images
to the configured worker count. Audio/default edits copy image bytes without a
decode or quantization pass.

## Reproduce

```bash
python tools/benchmark.py --runs 3 \
  --output /tmp/tsog-python-benchmark.json
python tests/browser_codec.py --real \
  --report /tmp/tsog-browser-conformance.json
```

The Python benchmark measures decode and a clearly named synthetic encode
separately. `--encode-points` changes only that synthetic workload. Each run
reports seconds, data size and peak RSS. The browser check compares eight
independent vectors across languages and optionally opens the entire real
example in a module worker. The analytic zero-alpha vector checks that RGB
integer codes survive raw native WebP decoding.

The eight synthetic cases matched Python/browser float32 values exactly on this
build. This establishes codec interoperability for the tested vectors, not a
universal performance or browser guarantee. Quantization quality depends on
input data, ranges, scalar books and the caller's SH palette. The separate
[FTGS Player benchmarks](https://github.com/OpsiClear-4DGS/ftgs-player/blob/main/docs/PERFORMANCE.md)
also cover GPU upload and rendered pixel equality; their timings are not numbers
for this independent reference codec.
