# Changelog

## Unreleased

- Optimize Python decoding with smaller lookup tables, fewer image copies,
  in-place byte assembly and a single read of the SH centroid image.
- Reduce Python encoder scale-validation work and avoid unrelated image-plugin
  initialization. Quantization, compression defaults and file version 1 remain
  unchanged.
- Verify bit-identical decoded/evaluated values and encoded payloads against
  the released implementation; extend numerical-boundary and buffer checks.

## 1.0.0 — 2026-10-12

- Establish the independent Apache-2.0 format repository.
- Define file version 1 and playback profile 1 in specification release 1.0.0.
- Read supported legacy Xiaomi version-4 files without relabeling their source.
- Add vectorized Python encoding/decoding, structural/full validation and
  byte-preserving audio packaging.
- Add dependency-free browser decoding and independent conformance examples.
- Keep the Python core dependency-free; make NumPy/Pillow an optional codec.
- Expose decoded attributes through standard buffer views.
- Package the 2M Slop Example as version 1, preserving attribute/audio bytes and
  recording its original container checksum in provenance.

This is the first release of the independent OpsiClear format and toolkit.
