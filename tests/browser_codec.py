# SPDX-License-Identifier: Apache-2.0
"""Check independent Python/browser attributes, corruption and worker decoding."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def flat(values):
    if isinstance(values, list):
        return [n for value in values for n in flat(value)]
    return [values]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--browser")
    parser.add_argument("--real", action="store_true", help="Decode full 2M Slop Example through the module worker")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    temporary = tempfile.TemporaryDirectory()
    try:
        fixtures = args.fixtures or Path(temporary.name)/"fixtures"
        if not args.fixtures:
            subprocess.run([sys.executable, str(root/"tools/create-fixtures.py"), str(fixtures)], check=True)
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *_): pass
            def translate_path(self, path):
                url = urlsplit(path).path
                if url.startswith("/fixtures/"):
                    return str(fixtures/Path(url).name)
                return super().translate_path(path)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        report = {"cases": []}
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=args.browser, headless=True, args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--disable-dev-shm-usage"])
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"http://127.0.0.1:{server.server_port}/examples/browser.html")
                for case in ("static", "discrete", "continuous8", "continuous16", "degree1", "degree2", "degree3", "analytic"):
                    actual = page.evaluate("""async name => {
                      const {decodeTSOG} = await import('/web/codec.js');
                      const model = await decodeTSOG(await (await fetch(`/fixtures/${name}.tsog`)).blob());
                      return Object.fromEntries(Object.entries(model).filter(([, value]) => ArrayBuffer.isView(value)).map(([key, value]) => [key, Array.from(value)]));
                    }""", case)
                    expected = json.loads((fixtures/f"{case}.json").read_text())
                    assert set(actual) == set(expected), (case, actual.keys(), expected.keys())
                    maximum = 0
                    for key in expected:
                        values = flat(expected[key])
                        assert len(actual[key]) == len(values), (case, key)
                        for a, b in zip(actual[key], values):
                            assert math.isfinite(a) and abs(a-b) <= 1e-6*max(1, abs(b)), (case, key, a, b)
                            maximum = max(maximum, abs(a-b))
                    report["cases"].append({"name": case, "maximum_absolute_difference": maximum})
                corruption = page.evaluate("""async () => {
                  const {decodeTSOG} = await import('/web/codec.js');
                  const data = new Uint8Array(await (await fetch('/fixtures/static.tsog')).arrayBuffer());
                  data[14] ^= 1;
                  try { await decodeTSOG(new Blob([data])); return null; }
                  catch (error) { return error.message; }
                }""")
                assert "mismatch" in corruption, corruption
                report["corruption"] = corruption
                if args.real:
                    page.locator("#decode").click()
                    page.wait_for_function("window.decodedExample?.metadata.count === 2000000 || document.querySelector('#status').textContent.startsWith('Failed:')", timeout=90000)
                    assert page.evaluate("window.decodedExample?.metadata.count") == 2000000, page.locator("#status").inner_text()
                    report["real"] = json.loads(page.locator("#status").inner_text())
                    assert report["real"]["audioBytes"] == 118113
                    assert report["real"]["attributeMB"] == "167.8"
                    assert page.evaluate("window.decodedExample.sh_labels instanceof Uint16Array")
                    assert page.evaluate("window.decodedExample.positions.length") == 6000000
                assert not errors, errors
                report["browser"] = browser.version
                browser.close()
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, indent=2)+"\n")
            print(json.dumps(report, indent=2))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    finally:
        temporary.cleanup()


if __name__ == "__main__":
    main()
