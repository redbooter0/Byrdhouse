"""Dependency-light helpers for the final ByrdHouse face-zone composite.

This module intentionally depends only on Pillow so its pixel-preservation
contract can be regression-tested in the normal zero-GPU integration suite.
"""

from __future__ import annotations

from PIL import Image


def restore_protected_material(
    generated: Image.Image,
    target: Image.Image,
    protected_mask: Image.Image,
) -> Image.Image:
    """Restore target eyes, mouth, and ink at their original output scale.

    ``protected_mask`` is prepared as a binary subset of the hard edit zone.
    Restoring after GPU cleanup prevents VAE/KSampler leakage from changing
    target-character material while the unprotected skin remains generated.
    """
    if generated.size != target.size or generated.size != protected_mask.size:
        raise ValueError(
            "generated, target, and protected mask must have the same dimensions"
        )
    return Image.composite(
        target.convert("RGB"),
        generated.convert("RGB"),
        protected_mask.convert("L"),
    )
