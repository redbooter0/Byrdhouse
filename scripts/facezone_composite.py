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


def clamp_mask_border(mask: Image.Image, border_px: int = 6) -> tuple[Image.Image, float]:
    """Zero the outer ``border_px`` frame of a crop-canvas mask.

    A legitimate face zone never reaches the crop border (the crop factor
    guarantees margin), so mask energy on the border is exactly the
    rectangular-crop-leak signature seen on the hard Vegeta target. Returns
    the clamped mask and the fraction of border pixels that carried mask
    energy before clamping — recorded so a leaky mask is visible in the card.
    """
    mask = mask.convert("L")
    w, h = mask.size
    px = mask.load()
    border_total = 0
    border_hot = 0
    for x in range(w):
        for y in (*range(min(border_px, h)), *range(max(0, h - border_px), h)):
            border_total += 1
            if px[x, y] > 8:
                border_hot += 1
    for y in range(border_px, max(border_px, h - border_px)):
        for x in (*range(min(border_px, w)), *range(max(0, w - border_px), w)):
            border_total += 1
            if px[x, y] > 8:
                border_hot += 1
    fraction = border_hot / border_total if border_total else 0.0
    if border_hot:
        clamped = mask.copy()
        cpx = clamped.load()
        for x in range(w):
            for y in range(h):
                if x < border_px or y < border_px or x >= w - border_px or y >= h - border_px:
                    cpx[x, y] = 0
        return clamped, round(fraction, 4)
    return mask, 0.0


def verify_outside_mask(
    original: Image.Image,
    final: Image.Image,
    effective_mask: Image.Image,
    tolerance: int = 0,
) -> dict:
    """Prove pixels outside the effective composite mask are IDENTICAL to the
    immutable original. Returns {passed, changed_pixels, max_delta}; a failure
    means the composite leaked outside its approved zone and must not ship.
    """
    if original.size != final.size or original.size != effective_mask.size:
        raise ValueError("original, final, and mask must share dimensions")
    from PIL import ImageChops
    diff = ImageChops.difference(original.convert("RGB"), final.convert("RGB")).convert("L")
    # Everything under the mask (including its soft skirt) is allowed to change;
    # only mask==0 territory must stay untouched.
    outside = effective_mask.convert("L").point(lambda v: 255 if v == 0 else 0)
    leaked = ImageChops.multiply(diff, outside)
    extrema = leaked.getextrema()
    max_delta = int(extrema[1])
    changed = 0
    if max_delta > tolerance:
        changed = sum(1 for v in leaked.getdata() if v > tolerance)
    return {"passed": max_delta <= tolerance,
            "changed_pixels": changed, "max_delta": max_delta}


def edit_delta(original: Image.Image, final: Image.Image,
               mask: Image.Image | None = None) -> dict:
    """Measure whether an edit ACTUALLY happened (founder law, 2026-07-16:
    an untouched copy must never be presented as a result). Compares final
    vs original — inside ``mask`` when given, else the whole image — and
    returns {edited, mean_delta, max_delta, changed_fraction}. Thresholds
    tolerate recompression noise but catch sampler no-ops and detector
    pass-throughs."""
    from PIL import ImageChops
    if final.size != original.size:
        final = final.resize(original.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(original.convert("RGB"), final.convert("RGB")).convert("L")
    if mask is not None:
        region = mask.convert("L").point(lambda v: 255 if v > 8 else 0)
        diff = ImageChops.multiply(diff, region)
        total = sum(1 for v in region.getdata() if v > 0)
    else:
        total = diff.size[0] * diff.size[1]
    data = diff.getdata()
    changed = sum(1 for v in data if v > 8)
    mean_delta = (sum(data) / total) if total else 0.0
    extrema = diff.getextrema()
    edited = bool(total and (mean_delta >= 1.0 or (changed / total) >= 0.005))
    return {"edited": edited, "mean_delta": round(mean_delta, 3),
            "max_delta": int(extrema[1]),
            "changed_fraction": round(changed / total, 5) if total else 0.0}


def images_effectively_identical(a_path, b_path) -> bool:
    """True when two image files are the same picture for practical purposes
    (the 'spat my input back out' detector for full-image routes)."""
    with Image.open(a_path) as a_img, Image.open(b_path) as b_img:
        return not edit_delta(a_img.convert("RGB"), b_img.convert("RGB"))["edited"]


def mesh_shard_score(image: Image.Image, warp_mask: Image.Image,
                     edge_threshold: int = 48, min_run: int = 12) -> dict:
    """Detect raw-triangle-warp shard artifacts inside the warped region.

    Triangle shards read as dense STRAIGHT high-contrast seams. Heuristic:
    binarize FIND_EDGES inside the (eroded) warp coverage, then measure what
    fraction of edge pixels sit in straight horizontal/vertical runs of at
    least ``min_run`` px, plus overall edge density. Smooth generated or
    blended faces score low; an unhidden CPU warp scores high. This detector
    is a heuristic and is therefore ALWAYS paired with the geometry gate —
    either one failing keeps a CPU-only result from shipping as final.
    """
    from PIL import ImageFilter
    gray = image.convert("L")
    if warp_mask.size != gray.size:
        warp_mask = warp_mask.resize(gray.size, Image.Resampling.NEAREST)
    interior = warp_mask.convert("L").point(lambda v: 255 if v > 128 else 0)
    interior = interior.filter(ImageFilter.MinFilter(5))  # drop the boundary ring
    # FIND_EDGES produces frame artifacts at the image border — exclude a
    # 3px frame so a smooth crop can never false-positive on its own edges.
    w0, h0 = interior.size
    from PIL import ImageOps
    interior = ImageOps.expand(interior.crop((3, 3, w0 - 3, h0 - 3)), 3, 0)
    edges = gray.filter(ImageFilter.FIND_EDGES).point(
        lambda v: 255 if v >= edge_threshold else 0)
    from PIL import ImageChops
    edges = ImageChops.multiply(edges, interior)
    w, h = edges.size
    data = list(edges.getdata())
    region_pixels = sum(1 for v in interior.getdata() if v > 0)
    edge_pixels = sum(1 for v in data if v > 0)
    straight = 0
    for y in range(h):  # horizontal runs
        run = 0
        row = y * w
        for x in range(w):
            if data[row + x] > 0:
                run += 1
            else:
                if run >= min_run:
                    straight += run
                run = 0
        if run >= min_run:
            straight += run
    for x in range(w):  # vertical runs
        run = 0
        for y in range(h):
            if data[y * w + x] > 0:
                run += 1
            else:
                if run >= min_run:
                    straight += run
                run = 0
        if run >= min_run:
            straight += run
    density = edge_pixels / region_pixels if region_pixels else 0.0
    straightness = straight / edge_pixels if edge_pixels else 0.0
    shards = bool(region_pixels and density > 0.02 and straightness > 0.28)
    return {"shards_detected": shards,
            "edge_density": round(density, 4),
            "straight_edge_fraction": round(straightness, 4),
            "region_pixels": region_pixels,
            "note": "heuristic straight-seam detector; paired with the geometry "
                    "gate — either failing blocks a CPU-only final"}
