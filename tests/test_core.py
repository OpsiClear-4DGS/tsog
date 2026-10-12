# SPDX-License-Identifier: Apache-2.0
"""Exercise core tools with third-party codec packages unavailable."""
from array import array
from pathlib import Path
import subprocess
import sys
import unittest

from tsog import Scene, Archive, validate, repackage, __version__


class CoreTests(unittest.TestCase):
    def test_standard_python_buffers_without_a_backend(self):
        positions = memoryview(array("f", [1, 2, 3])).cast("B").cast("f", shape=(1, 3))
        model = Scene(positions, positions, memoryview(array("f", [1, 0, 0, 0])).cast("B").cast("f", shape=(1, 4)),
                      positions, array("f", [1]))
        views = model.as_buffers()
        self.assertEqual(views["positions"].shape, (1, 3))
        self.assertTrue(views["positions"].readonly)
        self.assertEqual(model.attribute_bytes, 56)
        self.assertEqual(model.count, 1)
        self.assertEqual(__version__, "1.0.0")

    def test_import_validation_packaging_and_cli_without_site_packages(self):
        root = Path(__file__).resolve().parents[1]
        # Run without site initialization: no NumPy, Pillow or editable-package hooks.
        script = r'''
import sys,json,tempfile
from io import BytesIO
from pathlib import Path
import zipfile
sys.path.insert(0,sys.argv[1])
from tsog import Archive, Scene, validate, repackage, __version__
from tsog.__main__ import main
assert 'numpy' not in sys.modules and 'PIL' not in sys.modules
meta = {"version":1,"profile":{"id":"org.opsiclear.tsog-playback","version":1},"count":1,
 "means":{"mins":[0,0,0],"maxs":[0,0,0],"files":["low.webp","high.webp"]},
 "quats":{"files":["quat.webp"]},"scales":{"codebook":[-2.0],"files":["scale.webp"]},
 "sh0":{"codebook":[0],"files":["dc.webp"]}}
# Structural validation checks headers/CRCs, not the WebP compressed payload.
image = b'RIFF'+(18).to_bytes(4,'little')+b'WEBPVP8L'+(5).to_bytes(4,'little')+b'\x2f\x00\x00\x00\x00\x00'
with tempfile.TemporaryDirectory() as directory:
 source=Path(directory)/'source.tsog'
 with zipfile.ZipFile(source,'w') as archive:
  archive.writestr('meta.json',json.dumps(meta))
  for name in ['low.webp','high.webp','quat.webp','scale.webp','dc.webp']:
   archive.writestr(name,image)
 assert validate(source)['version']==1
 target=Path(directory)/'packaged.tsog'
 assert repackage(source,target,playback={'duration':1})['version']==1
 sys.argv=['tsog','inspect',str(target)]
 assert main()==0
 try:
  from tsog import decode
 except ImportError as error:
  assert '[codec]' in str(error)
 else:
  raise AssertionError('Optional codec unexpectedly available')
 assert 'numpy' not in sys.modules and 'PIL' not in sys.modules
 print('PASS: dependency-free core and actionable optional-codec error')
'''
        result = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(root/"src")], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dependency-free core", result.stdout)


if __name__ == "__main__":
    unittest.main()
