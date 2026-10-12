# SPDX-License-Identifier: Apache-2.0
"""Backend-neutral scene fields and standard Python buffer views.

Inputs may be nested numeric sequences or shaped buffer/array objects. A codec
validates logical shapes and values. Decoded arrays expose the buffer protocol;
their owner is retained by memoryview, without copying the attribute data.
"""
from dataclasses import dataclass, field
from typing import Any

ATTRIBUTE_NAMES = ("positions", "scales", "quaternions", "dc", "opacity",
                   "centers", "sigmas", "velocities", "frame_ids", "sh_palette", "sh_labels")


@dataclass
class Scene:
    positions: Any
    scales: Any
    quaternions: Any  # w,x,y,z
    dc: Any  # RGB DC coefficients
    opacity: Any  # linear
    centers: Any = None
    sigmas: Any = None
    velocities: Any = None
    frame_ids: Any = None
    sh_palette: Any = None
    sh_labels: Any = None
    audio: bytes | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def count(self):
        return len(self.positions)

    def as_buffers(self, *, readonly=True):
        """Return shaped memoryviews of packed fields; no NumPy import or copy.

        Float attributes use native-endian float32 after reference decoding;
        labels/frame IDs use uint16. Sequence inputs need codec conversion
        before they can be exported as packed buffers.
        """
        result = {}
        for name in ATTRIBUTE_NAMES:
            value = getattr(self, name)
            if value is None:
                continue
            try:
                view = memoryview(value)
            except TypeError as error:
                raise TypeError(f"{name} is a sequence, not a packed buffer; encode accepts sequences") from error
            result[name] = view.toreadonly() if readonly else view
        return result

    @property
    def attribute_bytes(self):
        return sum(view.nbytes for view in self.as_buffers().values())
