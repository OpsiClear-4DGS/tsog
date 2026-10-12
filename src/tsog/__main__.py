# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import sys

from .archive import Archive
from .metadata import timing
from .package import validate, repackage


def main():
    parser = argparse.ArgumentParser(description="TSOG playback profile tools")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Read metadata and ZIP record headers")
    inspect.add_argument("file")
    check = commands.add_parser("validate", help="Validate container, checksums and image headers")
    check.add_argument("file")
    check.add_argument("--full", action="store_true", help="Also decode/check every attribute value")
    check.add_argument("--require-profile", action="store_true")
    pack = commands.add_parser("package", help="Update defaults/audio without recompressing attributes")
    pack.add_argument("source")
    pack.add_argument("destination")
    pack.add_argument("--audio")
    pack.add_argument("--mime-type")
    pack.add_argument("--remove-audio", action="store_true")
    pack.add_argument("--fps", type=float)
    pack.add_argument("--duration", type=float)
    pack.add_argument("--rate", type=float)
    pack.add_argument("--no-loop", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            with Archive(args.file) as archive:
                result = {"metadata": archive.meta, "timing": timing(archive.meta),
                          "validation": "metadata and ZIP record headers; attributes not decoded"}
        elif args.command == "validate":
            result = validate(args.file, full=args.full, require_profile=args.require_profile)
        else:
            playback = {key: getattr(args, key) for key in ("fps", "duration", "rate") if getattr(args, key) is not None}
            if args.no_loop:
                playback["loop"] = False
            result = repackage(args.source, args.destination, playback=playback, audio=args.audio,
                               mime_type=args.mime_type, remove_audio=args.remove_audio)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError, OverflowError, ImportError) as error:
        print(f"TSOG: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
