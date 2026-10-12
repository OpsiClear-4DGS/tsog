# SPDX-License-Identifier: Apache-2.0
"""TSOG version 1 tools; the optional NumPy codec is loaded on demand."""
from importlib import import_module

from .archive import Archive, webp_dimensions
from .metadata import PROFILE, validate_metadata, timing
from .model import Scene
from .package import validate, repackage

__version__ = "1.0.0"

__all__ = ["Archive", "PROFILE", "Scene", "decode", "encode", "evaluate",
           "timing", "validate_metadata", "webp_dimensions", "validate", "repackage", "__version__"]


def __getattr__(name):
    if name not in ("decode", "encode", "evaluate"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        codec = import_module(".codec", __name__)
    except ModuleNotFoundError as error:
        if error.name in ("numpy", "PIL"):
            raise ImportError("The optional codec needs NumPy and Pillow; install with pip install '.[codec]' from the TSOG checkout") from error
        raise
    value = getattr(codec, name)
    globals()[name] = value
    return value
