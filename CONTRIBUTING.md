# Contributing

Install `python -m pip install -e '.[codec,test]'`, then run:

```bash
python -m unittest discover -s tests -v
python tools/create-fixtures.py /tmp/tsog-fixtures
tsog validate examples/slop-example.tsog --full --require-profile
```

The core-only checks also run without optional packages:

```bash
python -m unittest discover -s tests -p 'test_core.py' -v
```

They launch an isolated interpreter without site packages to verify metadata,
ZIP validation and byte-preserving packaging independently of NumPy/Pillow.

For browser conformance, install the optional test requirements in
`tests/browser-requirements.txt`, install Chromium with Playwright, and run
`python tests/browser_codec.py`. This checks independent Python/browser values,
lossless transparent RGB and static/discrete/continuous fixtures.

Every source file must retain its Apache SPDX identifier. Contributions are
provided under Apache-2.0. Do not copy AGPL player or trainer implementation
into this repository. Keep example provenance and rights notices intact.
Do not commit benchmark outputs, decoded NPZ dumps, environments or build trees.
The one recorded example is deliberately versioned; other fixtures are small
and generated from synthetic data.

Specification editorial revisions do not change the profile identifier.
Add incompatible temporal semantics only under a new version, with migration
notes, a schema and independent vectors. Test both metadata structure and decoded
meaning; a round-trip alone can hide matching encoder/decoder mistakes.
