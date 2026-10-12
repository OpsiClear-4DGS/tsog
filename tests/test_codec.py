# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import jsonschema
import numpy as np
from PIL import Image
from tsog import Archive, Scene, decode, encode, evaluate, repackage, timing, validate, validate_metadata, webp_dimensions
from support import analytic, bundle, scene, webp


class CodecTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_analytic_codes_and_transparent_rgb(self):
        meta, entries = analytic()
        result = decode(bundle(meta, entries))
        np.testing.assert_allclose(result.positions[0], [-np.expm1(1), 0, np.expm1(2)], rtol=1e-7)
        np.testing.assert_allclose(result.scales[0], [.1, .2, .1], rtol=1e-7)
        np.testing.assert_array_equal(result.dc[0], [23, 45, 67])
        self.assertEqual(result.opacity[0], 0)
        self.assertAlmostEqual(float(result.centers[0]), .25)
        self.assertAlmostEqual(float(result.sigmas[0]), .2)
        np.testing.assert_allclose(result.velocities[0], [1, -2, 3/255], rtol=1e-7)
        self.assertGreater(result.quaternions[0, 3], .99)
        self.assertAlmostEqual(float(np.linalg.norm(result.quaternions[0])), 1, delta=1e-7)
        position, opacity = evaluate(result, .5)
        np.testing.assert_allclose(position[0], result.positions[0]+np.array([1, -2, 3/255])*.25, rtol=1e-7)
        self.assertEqual(opacity[0], 0)

    def test_all_quaternion_tags_and_writable_packed_attributes(self):
        original = scene(degree=3)
        original.quaternions[:] = 0
        original.quaternions[np.arange(original.count), np.arange(original.count) % 4] = 1
        path = self.root/"axis-rotations.tsog"
        encode(original, path)
        decoded = decode(path)
        small = (2*128/255-1)/np.sqrt(2)
        expected = np.full((original.count, 4), small)
        expected[np.arange(original.count), np.arange(original.count) % 4] = np.sqrt(1-3*small*small)
        expected /= np.linalg.norm(expected, axis=1)[:, None]
        np.testing.assert_array_equal(decoded.quaternions, expected.astype(np.float32))
        # Consumers may pass packed bytes to a native binding after decode returns.
        for view in decoded.as_buffers(readonly=False).values():
            self.assertTrue(view.c_contiguous)
            self.assertFalse(view.readonly)
            self.assertEqual(view.cast("B").nbytes, view.nbytes)

    def test_unused_scale_extremes_are_ignored_but_used_extremes_fail(self):
        meta, entries = analytic()
        meta["scales"]["codebook"] += [1000, -1000]
        decoded = decode(bundle(meta, entries))
        np.testing.assert_allclose(decoded.scales[0], [.1, .2, .1], rtol=1e-7)
        for index in (2, 3):
            entries["scale.webp"] = webp([[0, index, 0, 255]])
            with self.assertRaisesRegex(ValueError, "scale"):
                decode(bundle(meta, entries))
        path = self.root/"unused-extremes.tsog"
        encode(scene(), path, codebooks={"scales": [np.log(.02), np.log(.06), 1000, -1000]})
        self.assertTrue(np.isfinite(decode(path).scales).all())

    def test_unused_position_overflow_is_ignored_but_used_overflow_fails(self):
        meta, entries = analytic()
        meta["means"]["maxs"][0] = 1000
        decoded = decode(bundle(meta, entries))
        self.assertAlmostEqual(float(decoded.positions[0, 0]), -np.expm1(1), delta=1e-7)
        entries["lo.webp"] = webp([[255, 0, 255, 255]])
        entries["hi.webp"] = webp([[255, 0, 255, 255]])
        with self.assertRaisesRegex(ValueError, "position"):
            decode(bundle(meta, entries))

    def test_continuous_roundtrip_both_motion_depths_and_all_sh_degrees(self):
        for bits in (8, 16):
            for degree in range(4):
                with self.subTest(bits=bits, degree=degree):
                    original = scene(degree=degree)
                    rotations = original.quaternions.copy()
                    path = self.root/f"{bits}-{degree}.tsog"
                    encode(original, path, motion_bits=bits, playback={"duration": 2, "fps": 24}, width=8)
                    result = decode(path)
                    np.testing.assert_array_equal(original.quaternions, rotations)
                    np.testing.assert_allclose(result.positions, original.positions, atol=2e-5)
                    np.testing.assert_allclose(result.velocities, original.velocities, atol=.004 if bits == 8 else 2e-5)
                    np.testing.assert_allclose(result.opacity, original.opacity, atol=1/510+1e-7)
                    self.assertEqual(timing(result.metadata)["frames"], 49)
                    if degree:
                        np.testing.assert_array_equal(result.sh_labels, original.sh_labels)
                        np.testing.assert_allclose(result.sh_palette, original.sh_palette, atol=.8/510+1e-7)
                        self.assertEqual(result.sh_labels.dtype, np.uint16)
                    validate(path, full=True, require_profile=True)

    def test_static_and_discrete_semantics(self):
        for kind in ("static", "discrete"):
            path = self.root/f"{kind}.tsog"
            original = scene(kind)
            encode(original, path, playback={"duration": 1, "fps": 3})
            result = decode(path)
            if kind == "discrete":
                np.testing.assert_array_equal(result.frame_ids, original.frame_ids)
                for time, frame in ((0, 0), (.4, 1), (1, 2)):
                    _, opacity = evaluate(result, time)
                    np.testing.assert_array_equal(opacity, result.opacity*(result.frame_ids == frame))
            else:
                position, opacity = evaluate(result, .7)
                self.assertIs(position, result.positions)
                self.assertIs(opacity, result.opacity)

    def test_supplied_unsorted_codebooks_preserve_indices(self):
        original = scene("static")
        original.dc[:] = [.2, -.3, .5]
        path = self.root/"books.tsog"
        encode(original, path, codebooks={"sh0": [.5, .2, -.3]})
        np.testing.assert_allclose(decode(path).dc, original.dc, atol=1e-7)

    def test_metadata_rejection_and_legacy_compatibility(self):
        meta, _ = analytic()
        validate_metadata(meta)
        with self.assertRaises(ValueError):
            validate_metadata(meta, require_profile=True)
        for mutation in (
            lambda m: m.update(version=2),
            lambda m: m.update(count=True),
            lambda m: m.update(profile={"id": "unknown", "version": 1}),
            lambda m: m["means"]["mins"].__setitem__(0, 2),
            lambda m: m["means"].update(files=["../x.webp", "hi.webp"]),
            lambda m: m["timeline"].update(type=2),
            lambda m: m["timeline"]["mins"].__setitem__(1, 0),
            lambda m: m["temporal"].update(rotation={}),
            lambda m: m.update(playback={"rate": 5}),
            lambda m: m.update(audio={"file": "dc.webp"}),
        ):
            with self.subTest(mutation=mutation):
                invalid = deepcopy(meta)
                mutation(invalid)
                with self.assertRaises(ValueError):
                    validate_metadata(invalid)

    def test_invalid_decoded_tags_indices_ranges_and_padding(self):
        for name, pixel in (("q.webp", [128,128,128,0]), ("scale.webp", [2,0,0,255])):
            meta, entries = analytic()
            entries[name] = webp([pixel])
            with self.assertRaises(ValueError):
                decode(bundle(meta, entries))
        meta, entries = analytic()
        meta["means"]["mins"][0] = meta["means"]["maxs"][0] = 100
        with self.assertRaises(ValueError):
            decode(bundle(meta, entries))

    def test_image_dimensions_and_lossy_webp_rejected(self):
        meta, entries = analytic()
        entries["q.webp"] = webp([[128,128,128,255]]*2)
        with self.assertRaises(ValueError):
            decode(bundle(meta, entries))
        output = BytesIO()
        Image.new("RGB", (1, 1)).save(output, format="WEBP", lossless=False)
        with self.assertRaises(ValueError):
            webp_dimensions(output.getvalue())

    def test_zip_corruption_duplicates_local_headers_and_crc(self):
        meta, entries = analytic()
        valid = bundle(meta, entries)
        invalid = bytearray(valid)
        struct.pack_into("<I", invalid, 14, 123)
        with self.assertRaises(ValueError):
            Archive(invalid)
        invalid = bytearray(valid)
        with zipfile.ZipFile(BytesIO(valid)) as z:
            i = z.getinfo("q.webp")
            offset = i.header_offset+30+len(i.filename)
        invalid[offset+20] ^= 1
        with self.assertRaises(ValueError):
            decode(invalid)
        with self.assertRaises(ValueError):
            Archive(valid[:-1])
        duplicate = BytesIO()
        with zipfile.ZipFile(duplicate, "w") as z:
            z.writestr("meta.json", json.dumps(meta))
            z.writestr("meta.json", json.dumps(meta))
        with self.assertRaises(ValueError):
            Archive(duplicate.getvalue())

    def test_signed_and_unsigned_zip_descriptors(self):
        meta, entries = analytic()
        class Stream(BytesIO):
            def seekable(self): return False
            def seek(self, *args): raise OSError("stream")
        stream = Stream()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("meta.json", json.dumps(meta))
            for name, data in entries.items():
                z.writestr(name, data)
        payload = stream.getvalue()
        self.assertEqual(decode(payload).count, 1)
        # A handcrafted single STORE member fixes the unsigned descriptor case.
        data = b"{}"
        crc = zipfile.crc32(data)
        name = b"meta.json"
        local = struct.pack("<I5H3I2H", 0x04034b50, 20, 8, 0, 0, 0, 0, 0, 0, len(name), 0)+name+data
        local += struct.pack("<3I", crc, len(data), len(data))
        directory = struct.pack("<I6H3I5H2I", 0x02014b50, 20, 20, 8, 0, 0, 0, crc, len(data), len(data), len(name), 0, 0, 0, 0, 0, 0)+name
        end = struct.pack("<I4H2IH", 0x06054b50, 0, 0, 1, 1, len(directory), len(local), 0)
        with self.assertRaisesRegex(ValueError, "version"):
            Archive(local+directory+end)  # Descriptor accepted; metadata is intentionally invalid.

    def test_audio_packaging_preserves_all_attribute_bytes(self):
        source = self.root/"source.tsog"
        encode(scene(), source, playback={"duration": 1, "fps": 24})
        track = self.root/"track.mp3"
        track.write_bytes(b"synthetic-audio-container-bytes")
        result = self.root/"audio.tsog"
        repackage(source, result, audio=track, playback={"rate": 2})
        with Archive(source) as a, Archive(result) as b:
            for name in a.zip.namelist():
                if name != "meta.json":
                    self.assertEqual(a.read(name), b.read(name))
        self.assertEqual(decode(result).audio, track.read_bytes())
        silent = self.root/"silent.tsog"
        repackage(result, silent, remove_audio=True)
        self.assertNotIn("audio", decode(silent).metadata)

    def test_writer_is_atomic_and_does_not_overwrite(self):
        path = self.root/"scene.tsog"
        encode(scene("static"), path)
        original = path.read_bytes()
        with self.assertRaises(ValueError):
            encode(scene("static"), path)
        self.assertEqual(path.read_bytes(), original)
        broken = scene()
        broken.sigmas[:] = 0
        destination = self.root/"broken.tsog"
        with self.assertRaises(ValueError):
            encode(broken, destination)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob('.tsog-*')))

    def test_resource_limits_are_explicit(self):
        meta, entries = analytic()
        with self.assertRaisesRegex(ValueError, "resource"):
            decode(bundle(meta, entries), max_points=0)

    def test_float32_underflow_covariance_overflow_and_json_integers(self):
        meta, entries = analytic()
        meta["version"] = 4.0
        meta["timeline"]["type"] = 1.0
        self.assertEqual(decode(bundle(meta, entries)).count, 1)
        meta["timeline"]["mins"][1] = 7.006492321624085e-46
        with self.assertRaises(ValueError):
            validate_metadata(meta)
        meta, entries = analytic()
        meta["scales"]["codebook"] = [float(np.log(1e30))]*2
        with self.assertRaisesRegex(ValueError, "covariance"):
            decode(bundle(meta, entries))
        invalid = scene("static")
        invalid.scales[:] = 1e-50
        with self.assertRaises(ValueError):
            encode(invalid, self.root/"underflow.tsog")
        encoded = self.root/"float-json.tsog"
        encode(scene(degree=1), encoded)
        with Archive(encoded) as archive:
            meta = deepcopy(archive.meta)
            meta["shN"]["bands"] = 1.0
            meta["shN"]["count"] = 5.0
            members = {name: archive.read(name) for name in archive.zip.namelist() if name != "meta.json"}
        self.assertEqual(decode(bundle(meta, members)).sh_palette.shape, (5, 3, 3))

    def test_metadata_annotations_survive_packaging_and_legacy_fps_survives_encoding(self):
        original = scene()
        original.metadata["fps"] = 24
        source = self.root/"original.tsog"
        encode(original, source)
        self.assertEqual(timing(decode(source).metadata)["fps"], 24)
        with Archive(source) as archive:
            meta = deepcopy(archive.meta)
            meta["customAnnotation"] = {"keep": True}
            members = {name: archive.read(name) for name in archive.zip.namelist() if name != "meta.json"}
        annotated = self.root/"annotated.tsog"
        annotated.write_bytes(bundle(meta, members))
        output = self.root/"updated.tsog"
        repackage(annotated, output, playback={"rate": .5})
        self.assertEqual(decode(output).metadata["customAnnotation"], {"keep": True})

    def test_schema_accepts_valid_modes_and_rejects_unknown_temporal_keys(self):
        schema = json.loads((Path(__file__).resolve().parents[1]/"spec/profile.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        for kind in ("static", "discrete", "continuous"):
            path = self.root/f"schema-{kind}.tsog"
            meta = encode(scene(kind, 3), path)
            jsonschema.validate(meta, schema)
        meta, _ = analytic()
        jsonschema.validate(meta, schema)
        meta["temporal"]["scale"] = {}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(meta, schema)

    def test_version1_requires_identity_and_legacy_v4_remains_readable(self):
        meta, entries = analytic()
        old = decode(bundle(meta, entries))
        meta["version"] = 1
        schema = json.loads((Path(__file__).resolve().parents[1]/"spec/profile.schema.json").read_text())
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(meta, schema)
        with self.assertRaises(ValueError):
            decode(bundle(meta, entries))
        meta["profile"] = {"id": "org.opsiclear.tsog-playback", "version": 1}
        jsonschema.validate(meta, schema)
        current = decode(bundle(meta, entries))
        for key in current.as_buffers():
            np.testing.assert_array_equal(getattr(current, key), getattr(old, key))
        path = self.root/"v1.tsog"
        written = encode(scene(), path)
        self.assertEqual(written["version"], 1)
        self.assertEqual(written["profile"]["version"], 1)

    def test_generic_sequence_inputs_and_zero_copy_buffer_views(self):
        original = scene()
        generic = deepcopy(original)
        for key in original.as_buffers():
            setattr(generic, key, getattr(original, key).tolist())
        path = self.root/"sequences.tsog"
        encode(generic, path)
        decoded = decode(path)
        readonly = decoded.as_buffers()
        self.assertEqual(readonly["positions"].shape, (17, 3))
        self.assertEqual(readonly["positions"].format, "f")
        self.assertTrue(readonly["positions"].readonly)
        self.assertEqual(sum(v.nbytes for v in readonly.values()), decoded.attribute_bytes)
        writable = decoded.as_buffers(readonly=False)["positions"]
        writable[0, 0] = 9
        self.assertEqual(decoded.positions[0, 0], 9)
        self.assertEqual(readonly["positions"][0, 0], 9)
        positions, opacity = evaluate(generic, .25)
        self.assertEqual(positions.shape, (17, 3))
        self.assertEqual(opacity.shape, (17,))


if __name__ == "__main__":
    unittest.main()
