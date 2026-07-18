#!/usr/bin/env python3
"""Finish pale skin islands on an approved face artifact without regenerating it."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def load_rgb(path: Path) -> np.ndarray:
    if not path.is_file():
        raise SystemExit(f"missing image: {path}")
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finish(base_path: Path, zone_path: Path, output_path: Path) -> dict:
    zone = json.loads(zone_path.read_text(encoding="utf-8-sig"))
    artifacts = zone["artifacts"]
    box = zone["crop_box"]
    left, top = int(box["x"]), int(box["y"])
    side = int(box["width"])

    base = load_rgb(base_path)
    crop = base[top:top + side, left:left + side].copy()
    if crop.shape[:2] != (side, side):
        raise SystemExit("zone crop falls outside the approved base image")

    with Image.open(artifacts["hard_mask"]) as image:
        hard = np.asarray(
            image.convert("L").resize((side, side), Image.Resampling.NEAREST)
        ) > 127
    with Image.open(artifacts["semantic_labels"]) as image:
        semantic = np.asarray(
            image.convert("RGB").resize((side, side), Image.Resampling.NEAREST)
        )

    # Face, nose, ears, and neck are the complexion mold. Eyes, brows, lips,
    # hair, clothing, and their ink remain untouched.
    skin_colors = np.asarray(
        [(255, 95, 90), (255, 145, 90), (255, 110, 80), (45, 120, 255)],
        dtype=np.uint8,
    )
    semantic_skin = np.any(
        np.all(semantic[:, :, None, :] == skin_colors[None, None, :, :], axis=3),
        axis=2,
    )
    rgb = crop.astype(np.float32)
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB).astype(np.float32)

    # The historical parser mislabeled most of Vegeta's oversized pale forehead
    # as background/headwear. Recover skin-colored pixels by measured pigment,
    # while explicit facial-feature classes keep their material and linework.
    protected_colors = np.asarray(
        [
            (50, 190, 255),  # eyes
            (195, 95, 65),   # brows
            (255, 100, 140), # mouth
            (255, 80, 120),  # lips
            (145, 90, 255),  # clothing
        ],
        dtype=np.uint8,
    )
    protected_feature = np.any(
        np.all(semantic[:, :, None, :] == protected_colors[None, None, :, :], axis=3),
        axis=2,
    )
    recovered_flesh_pigment = (
        (rgb[..., 0] >= 158)
        & (rgb[..., 1] >= 76)
        & (rgb[..., 2] >= 32)
        & (rgb[..., 0] > rgb[..., 1])
        & (rgb[..., 1] > rgb[..., 2])
        & (hsv[..., 0] <= 31)
        & (hsv[..., 1] >= 25)
        & (lab[..., 0] >= 112)
        & ~protected_feature
    )
    # Follow only pigment connected to confirmed skin. Close the *support* to
    # bridge narrow ink strokes, then intersect back with the original pigment
    # pixels so brows, scars, beard, and outlines are never painted over.
    connected_support = cv2.morphologyEx(
        recovered_flesh_pigment.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    ) > 0
    connected_pigment = np.zeros_like(recovered_flesh_pigment)
    component_count, component_labels = cv2.connectedComponents(
        connected_support.astype(np.uint8), connectivity=8
    )
    semantic_touch = cv2.dilate(
        semantic_skin.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
    ) > 0
    for component in range(1, component_count):
        region = component_labels == component
        if np.any(region & semantic_touch):
            connected_pigment |= region & recovered_flesh_pigment
    # Parser skin plus its connected measured pigment is the complete mold.
    # The old hard mask stays only as an audit baseline.
    mold = semantic_skin | connected_pigment

    # Detect only leftover light flesh pigment. Dark linework, beard, nostrils,
    # lips, ear detail, cel shadows, and small white specular marks are excluded.
    pale = (
        mold
        & (rgb[..., 0] >= 158)
        & (rgb[..., 1] >= 76)
        & (rgb[..., 2] >= 32)
        & (rgb[..., 0] > rgb[..., 1])
        & (rgb[..., 1] > rgb[..., 2])
        & (hsv[..., 0] <= 31)
        & (hsv[..., 1] >= 25)
        & (lab[..., 0] >= 142)
    )
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        pale.astype(np.uint8), connectivity=8
    )
    retained = np.zeros_like(pale)
    component_sizes = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= 5:
            retained |= labels == label
            component_sizes.append(area)
    pale = retained

    good_brown = (
        mold
        & (rgb[..., 0] >= 72)
        & (rgb[..., 0] <= 194)
        & (rgb[..., 1] >= 22)
        & (rgb[..., 1] <= 126)
        & (rgb[..., 2] <= 105)
        & (rgb[..., 0] >= rgb[..., 1] * 1.22)
    )
    if int(good_brown.sum()) < 256 or int(pale.sum()) < 32:
        raise SystemExit(
            f"unsafe complexion sample: brown={int(good_brown.sum())}, pale={int(pale.sum())}"
        )

    brown_reference = np.percentile(rgb[good_brown], 67, axis=0)
    pale_reference = np.median(rgb[pale], axis=0)
    ratios = np.clip(brown_reference / np.maximum(pale_reference, 1.0), 0.30, 0.82)
    mapped = np.clip(rgb * ratios[None, None, :], 0, 255)

    # Retain local cel shading and antialiasing. Feathering occurs only inward
    # through the approved complexion mask, so the face border cannot expand.
    alpha = cv2.GaussianBlur(pale.astype(np.float32), (0, 0), 0.55)
    alpha = np.clip(alpha * mold.astype(np.float32), 0.0, 1.0)[..., None]
    repaired = np.uint8(np.clip(rgb * (1.0 - alpha) + mapped * alpha, 0, 255))
    result = base.copy()
    result[top:top + side, left:left + side] = repaired

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result, mode="RGB").save(output_path, "PNG", optimize=True)
    source_card_path = Path(str(base_path) + ".json")
    source_card = (
        json.loads(source_card_path.read_text(encoding="utf-8-sig"))
        if source_card_path.is_file()
        else {}
    )
    card = {
        "artifact_type": "image",
        "status": "needs_review",
        "purpose": "Locked Vegeta baseline; finish Carey complexion coverage without face regeneration",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parent_artifact": str(base_path.resolve()),
        "parent_artifact_sha256": sha256(base_path),
        "parent_card": str(source_card_path.resolve()) if source_card_path.is_file() else None,
        "parent_job_id": source_card.get("job_id"),
        "zone_file": str(zone_path.resolve()),
        "method": "locked-baseline-connected-pale-skin-completion-v1",
        "locked_features": [
            "face size and placement", "eyes and brows", "nose and nostrils",
            "mouth and lips", "ears", "Carey beard and jaw edge", "Vegeta hair and armor",
        ],
        "settings_inherited": {
            key: source_card.get(key)
            for key in (
                "recipe", "workflow", "seed", "steps", "cfg", "sampler",
                "scheduler", "denoise", "checkpoint", "identity_model_strength",
                "identity_clip_strength", "lora", "target_preset",
            )
            if source_card.get(key) is not None
        },
        "finish_metrics": {
            "approved_mold_pixels": int(mold.sum()),
            "historical_hard_mask_pixels": int(hard.sum()),
            "recovered_skin_border_pixels": int((mold & ~hard).sum()),
            "connected_pigment_pixels": int(connected_pigment.sum()),
            "good_brown_sample_pixels": int(good_brown.sum()),
            "pale_skin_pixels_repaired": int(pale.sum()),
            "pale_components_repaired": len(component_sizes),
            "largest_component_pixels": max(component_sizes, default=0),
            "pale_reference_rgb": [round(float(value), 3) for value in pale_reference],
            "brown_reference_rgb": [round(float(value), 3) for value in brown_reference],
            "channel_ratios": [round(float(value), 6) for value in ratios],
        },
    }
    card_path = Path(str(output_path) + ".json")
    card_path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    return {"output": str(output_path), "card": str(card_path), **card["finish_metrics"]}


def _embedded_mask(
    path: str | Path,
    box: dict,
    image_shape: tuple[int, int],
    *,
    threshold: int = 127,
) -> np.ndarray:
    height, width = image_shape
    left, top = int(box["x"]), int(box["y"])
    side = int(box["width"])
    full = np.zeros((height, width), dtype=bool)
    with Image.open(path) as image:
        crop = np.asarray(
            image.convert("L").resize((side, side), Image.Resampling.NEAREST)
        ) > threshold
    full[top:top + side, left:left + side] = crop
    return full


def _embedded_semantic(
    path: str | Path,
    box: dict,
    image_shape: tuple[int, int],
) -> np.ndarray:
    height, width = image_shape
    left, top = int(box["x"]), int(box["y"])
    side = int(box["width"])
    full = np.zeros((height, width, 3), dtype=np.uint8)
    with Image.open(path) as image:
        crop = np.asarray(
            image.convert("RGB").resize((side, side), Image.Resampling.NEAREST)
        )
    full[top:top + side, left:left + side] = crop
    return full


def _components_touching_seed(mask: np.ndarray, seed: np.ndarray) -> np.ndarray:
    retained = np.zeros(mask.shape, dtype=bool)
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    for component in range(1, count):
        region = labels == component
        if np.any(region & seed):
            retained |= region
    return retained


def _retained_components(mask: np.ndarray, minimum_area: int) -> tuple[np.ndarray, list[int]]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    retained = np.zeros(mask.shape, dtype=bool)
    areas: list[int] = []
    for component in range(1, count):
        area = int(stats[component, cv2.CC_STAT_AREA])
        if area >= minimum_area:
            retained |= labels == component
            areas.append(area)
    return retained, areas


def finish_outline_priority(
    base_path: Path,
    zone_path: Path,
    output_path: Path,
    *,
    lift_shadows: bool,
    smooth_seams: bool = False,
    palette_reference: Path | None = None,
    local_donor_fill: bool = False,
) -> dict:
    """Finish the locked Vegeta mold using the immutable target outline.

    The saved historical crop clipped the top of Vegeta's widow's peak.  This
    pass rebuilds skin authority in full-image coordinates from target pigment
    connected to the audited semantic face, then recolors only residual pale
    pigment.  Anime ink and semantic features are hard locks.
    """
    zone = json.loads(zone_path.read_text(encoding="utf-8-sig"))
    artifacts = zone["artifacts"]
    box = zone["crop_box"]
    base = load_rgb(base_path)
    target_path = Path(zone["source"])
    target = load_rgb(target_path)
    if target.shape != base.shape:
        raise SystemExit(
            "locked finish requires target and approved base at identical dimensions"
        )
    height, width = base.shape[:2]
    hard = _embedded_mask(artifacts["hard_mask"], box, (height, width))
    semantic = _embedded_semantic(
        artifacts["semantic_labels"], box, (height, width)
    )

    skin_colors = np.asarray(
        [(255, 95, 90), (255, 145, 90), (255, 110, 80), (45, 120, 255)],
        dtype=np.uint8,
    )
    semantic_skin = np.any(
        np.all(semantic[:, :, None, :] == skin_colors[None, None, :, :], axis=3),
        axis=2,
    )
    protected_colors = np.asarray(
        [
            (255, 220, 70),  # eyeglasses / preserved feature material
            (50, 190, 255),  # eyes
            (195, 95, 65),   # brows
            (255, 100, 140), # mouth
            (255, 80, 120),  # lips
            (40, 220, 80),   # hair
            (255, 210, 55),  # headwear
            (230, 210, 50),  # earrings
            (225, 190, 45),  # necklace
            (145, 90, 255),  # clothing
        ],
        dtype=np.uint8,
    )
    protected_semantic = np.any(
        np.all(
            semantic[:, :, None, :] == protected_colors[None, None, :, :],
            axis=3,
        ),
        axis=2,
    )
    protected_seed_path = artifacts.get("protected_seed_features")
    protected_seed = (
        _embedded_mask(protected_seed_path, box, (height, width), threshold=24)
        if protected_seed_path and Path(protected_seed_path).is_file()
        else np.zeros((height, width), dtype=bool)
    )

    target_rgb = target.astype(np.float32)
    target_hsv = cv2.cvtColor(target, cv2.COLOR_RGB2HSV)
    target_lab = cv2.cvtColor(target, cv2.COLOR_RGB2LAB).astype(np.float32)
    target_flesh = (
        (target_rgb[..., 0] >= 135)
        & (target_rgb[..., 1] >= 55)
        & (target_rgb[..., 2] >= 25)
        & (target_rgb[..., 0] > target_rgb[..., 1] * 1.08)
        & (target_rgb[..., 1] > target_rgb[..., 2] * 1.05)
        & (target_hsv[..., 0] <= 31)
        & (target_hsv[..., 1] >= 25)
        & (target_lab[..., 0] >= 85)
    )
    target_support = cv2.morphologyEx(
        target_flesh.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    ) > 0
    confirmed_seed = cv2.dilate(
        (semantic_skin | (hard & target_flesh)).astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
    ) > 0
    target_skin = _components_touching_seed(target_support, confirmed_seed)
    target_skin &= target_flesh

    base_rgb = base.astype(np.float32)
    base_hsv = cv2.cvtColor(base, cv2.COLOR_RGB2HSV)
    base_lab = cv2.cvtColor(base, cv2.COLOR_RGB2LAB).astype(np.float32)
    base_gray = cv2.cvtColor(base, cv2.COLOR_RGB2GRAY)
    target_gray = cv2.cvtColor(target, cv2.COLOR_RGB2GRAY)
    edge_guard = cv2.dilate(
        np.uint8(
            (cv2.Canny(base_gray, 45, 110) > 0)
            | (cv2.Canny(target_gray, 45, 110) > 0)
        ),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    ) > 0
    ink_guard = (
        (base_gray <= 56)
        | (target_gray <= 56)
        | (edge_guard & ((base_lab[..., 0] < 105) | (target_lab[..., 0] < 105)))
    )
    # The historical anime parser mislabeled several connected forehead-skin
    # islands as hair/headwear.  Immutable target pigment wins only inside the
    # connected skin authority; actual dark hairline ink remains locked by the
    # target/base edge guard below.
    protected = (protected_semantic & ~target_skin) | protected_seed | ink_guard

    good_brown = (
        target_skin
        & ~protected
        & (base_rgb[..., 0] >= 60)
        & (base_rgb[..., 0] <= 194)
        & (base_rgb[..., 1] >= 20)
        & (base_rgb[..., 1] <= 126)
        & (base_rgb[..., 2] <= 125)
        & (base_rgb[..., 0] >= base_rgb[..., 1] * 1.22)
        & (base_hsv[..., 0] <= 25)
        & (base_lab[..., 0] <= 138)
    )
    pale = (
        target_skin
        & ~protected
        & (base_rgb[..., 0] >= 155)
        & (base_rgb[..., 1] >= 75)
        & (base_rgb[..., 2] >= 30)
        & (base_rgb[..., 0] > base_rgb[..., 1])
        & (base_rgb[..., 1] > base_rgb[..., 2])
        & (base_hsv[..., 0] <= 31)
        & (base_hsv[..., 1] >= 25)
        & (base_lab[..., 0] >= 142)
    )
    pale, component_sizes = _retained_components(pale, 5)
    if int(good_brown.sum()) < 256 or int(pale.sum()) < 32:
        raise SystemExit(
            f"unsafe outline complexion sample: brown={int(good_brown.sum())}, "
            f"pale={int(pale.sum())}"
        )

    brown_reference = np.percentile(base_rgb[good_brown], 67, axis=0)
    pale_reference = np.median(base_rgb[pale], axis=0)
    ratios = np.clip(
        brown_reference / np.maximum(pale_reference, 1.0), 0.30, 0.82
    )
    mapped = np.clip(base_rgb * ratios[None, None, :], 0, 255)
    local_donor_resolved = 0
    if local_donor_fill:
        walkable = target_skin & ~protected
        known = good_brown.copy()
        propagated = np.zeros_like(base_rgb, dtype=np.float32)
        propagated[known] = base_rgb[known]
        kernel = np.ones((3, 3), dtype=np.float32)
        for _ in range(48):
            neighbor_count = cv2.filter2D(
                known.astype(np.float32), -1, kernel, borderType=cv2.BORDER_CONSTANT
            )
            frontier = walkable & ~known & (neighbor_count > 0)
            if not np.any(frontier):
                break
            for channel in range(3):
                neighbor_sum = cv2.filter2D(
                    propagated[..., channel],
                    -1,
                    kernel,
                    borderType=cv2.BORDER_CONSTANT,
                )
                propagated[..., channel][frontier] = (
                    neighbor_sum[frontier] / neighbor_count[frontier]
                )
            known |= frontier
        local_resolved = pale & known
        local_donor_resolved = int(local_resolved.sum())
        local_color = propagated.copy()
        local_color[pale & ~known] = brown_reference
        local_detail = base_rgb - cv2.GaussianBlur(base_rgb, (0, 0), 2.2)
        local_color += local_detail * 0.15
        mapped[pale] = np.clip(local_color[pale], 0, 255)
    repair_corridor = cv2.dilate(
        pale.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    ) > 0
    alpha = cv2.GaussianBlur(pale.astype(np.float32), (0, 0), 0.55)
    alpha *= (target_skin & repair_corridor & ~protected).astype(np.float32)
    coverage_rgb = np.clip(
        base_rgb * (1.0 - alpha[..., None]) + mapped * alpha[..., None],
        0,
        255,
    ).astype(np.uint8)

    shadow_pixels = np.zeros((height, width), dtype=bool)
    seam_edges = np.zeros((height, width), dtype=bool)
    seam_corridor = np.zeros((height, width), dtype=bool)
    palette_pixels = np.zeros((height, width), dtype=bool)
    palette_reference_metrics: dict | None = None
    result_rgb = coverage_rgb
    shadow_reference_lab: list[float] | None = None
    if lift_shadows:
        coverage_lab = cv2.cvtColor(coverage_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        coverage_hsv = cv2.cvtColor(coverage_rgb, cv2.COLOR_RGB2HSV)
        low_gradient = ~edge_guard
        shadow_candidate = (
            target_skin
            & ~protected
            & low_gradient
            & (coverage_hsv[..., 0] <= 31)
            & (coverage_hsv[..., 1] >= 25)
            & (coverage_lab[..., 0] >= 45)
            & (coverage_lab[..., 0] < 100)
        )
        shadow_pixels, _ = _retained_components(shadow_candidate, 128)
        midtone = (
            target_skin
            & ~protected
            & (coverage_lab[..., 0] >= 105)
            & (coverage_lab[..., 0] <= 145)
        )
        if int(shadow_pixels.sum()) >= 128 and int(midtone.sum()) >= 128:
            reference = np.median(coverage_lab[midtone], axis=0)
            shadow_reference_lab = [round(float(value), 3) for value in reference]
            goal_l = float(reference[0] - 30.0)
            lifted = coverage_lab.copy()
            lift = np.clip((goal_l - lifted[..., 0]) * 0.75, 0.0, 22.0)
            lifted[..., 0] += lift * shadow_pixels
            lifted[..., 1] = np.where(
                shadow_pixels,
                lifted[..., 1] * 0.65 + float(reference[1]) * 0.35,
                lifted[..., 1],
            )
            lifted[..., 2] = np.where(
                shadow_pixels,
                lifted[..., 2] * 0.65 + float(reference[2]) * 0.35,
                lifted[..., 2],
            )
            lifted_rgb = cv2.cvtColor(
                np.uint8(np.clip(lifted, 0, 255)), cv2.COLOR_LAB2RGB
            )
            result_rgb = coverage_rgb.copy()
            result_rgb[shadow_pixels] = lifted_rgb[shadow_pixels]

    if palette_reference is not None:
        palette_reference = palette_reference.resolve()
        reference_card_path = Path(str(palette_reference) + ".json")
        if not palette_reference.is_file() or not reference_card_path.is_file():
            raise SystemExit(
                "approved palette reference and its sidecar card are required"
            )
        reference_rgb = load_rgb(palette_reference)
        reference_card = json.loads(
            reference_card_path.read_text(encoding="utf-8-sig")
        )
        reference_zone = dict(reference_card.get("face_zone") or {})
        reference_artifacts = dict(reference_zone.get("artifacts") or {})
        reference_box = dict(reference_zone.get("crop_box") or {})
        if not reference_artifacts.get("hard_mask") or not reference_box:
            raise SystemExit("approved palette reference card has no audited face mask")
        reference_hard = _embedded_mask(
            reference_artifacts["hard_mask"],
            reference_box,
            reference_rgb.shape[:2],
        )
        reference_lab = cv2.cvtColor(
            reference_rgb, cv2.COLOR_RGB2LAB
        ).astype(np.float32)
        reference_hsv = cv2.cvtColor(reference_rgb, cv2.COLOR_RGB2HSV)
        reference_float = reference_rgb.astype(np.float32)
        reference_skin = (
            reference_hard
            & (reference_float[..., 0] > reference_float[..., 1] * 1.08)
            & (reference_float[..., 1] > reference_float[..., 2] * 1.02)
            & (reference_hsv[..., 0] <= 30)
            & (reference_lab[..., 0] >= 35)
            & (reference_lab[..., 0] <= 170)
        )
        if int(reference_skin.sum()) < 1024:
            raise SystemExit("approved palette reference has too little safe skin")
        palette_pixels = target_skin & ~protected
        smoothed_target = cv2.bilateralFilter(
            target, d=9, sigmaColor=35, sigmaSpace=7
        )
        smoothed_target_lab = cv2.cvtColor(
            smoothed_target, cv2.COLOR_RGB2LAB
        ).astype(np.float32)
        reference_values = reference_lab[reference_skin]
        mapped_l = np.clip(
            0.72 * smoothed_target_lab[..., 0] - 58.0, 45.0, 125.0
        )
        reference_chroma = np.median(reference_values[:, 1:3], axis=0)
        target_chroma = np.median(
            smoothed_target_lab[palette_pixels][:, 1:3], axis=0
        )
        chroma_low = np.percentile(reference_values[:, 1:3], 5, axis=0)
        chroma_high = np.percentile(reference_values[:, 1:3], 95, axis=0)
        mapped_lab = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        mapped_lab[..., 0] = np.where(palette_pixels, mapped_l, mapped_lab[..., 0])
        for channel in (1, 2):
            value = (
                float(reference_chroma[channel - 1])
                + 0.12
                * (
                    smoothed_target_lab[..., channel]
                    - float(target_chroma[channel - 1])
                )
            )
            value = np.clip(
                value,
                float(chroma_low[channel - 1]),
                float(chroma_high[channel - 1]),
            )
            mapped_lab[..., channel] = np.where(
                palette_pixels, value, mapped_lab[..., channel]
            )
        palette_rgb = cv2.cvtColor(
            np.uint8(np.clip(mapped_lab, 0, 255)), cv2.COLOR_LAB2RGB
        )
        prior_rgb = result_rgb
        result_rgb = prior_rgb.copy()
        result_rgb[palette_pixels] = palette_rgb[palette_pixels]
        palette_reference_metrics = {
            "artifact": str(palette_reference),
            "artifact_sha256": sha256(palette_reference),
            "safe_skin_sample_pixels": int(reference_skin.sum()),
            "skin_lab_p10_p50_p90": [
                [round(float(value), 3) for value in row]
                for row in np.percentile(reference_values, (10, 50, 90), axis=0)
            ],
        }

    if smooth_seams:
        result_lab = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        horizontal_delta = np.linalg.norm(
            result_lab[:, 1:] - result_lab[:, :-1], axis=2
        )
        target_horizontal_delta = np.linalg.norm(
            target_lab[:, 1:] - target_lab[:, :-1], axis=2
        )
        vertical_delta = np.linalg.norm(
            result_lab[1:, :] - result_lab[:-1, :], axis=2
        )
        target_vertical_delta = np.linalg.norm(
            target_lab[1:, :] - target_lab[:-1, :], axis=2
        )
        seam_edges[:, 1:] |= (
            (horizontal_delta >= 14.0) & (target_horizontal_delta < 6.0)
        )
        seam_edges[1:, :] |= (
            (vertical_delta >= 14.0) & (target_vertical_delta < 6.0)
        )
        seam_edges &= target_skin & ~protected
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            seam_edges.astype(np.uint8), connectivity=8
        )
        retained_seams = np.zeros((height, width), dtype=bool)
        for component in range(1, count):
            area = int(stats[component, cv2.CC_STAT_AREA])
            component_width = int(stats[component, cv2.CC_STAT_WIDTH])
            component_height = int(stats[component, cv2.CC_STAT_HEIGHT])
            if area >= 6 and max(component_width, component_height) >= 8:
                retained_seams |= labels == component
        protected_margin = cv2.dilate(
            protected.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        ) > 0
        seam_corridor = cv2.dilate(
            retained_seams.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        ) > 0
        seam_corridor &= target_skin & ~protected_margin
        if np.any(seam_corridor):
            smoothed_lab = cv2.GaussianBlur(result_lab, (0, 0), 3.0)
            seam_alpha = cv2.GaussianBlur(
                retained_seams.astype(np.float32), (0, 0), 2.0
            )
            seam_alpha = np.clip(seam_alpha, 0.0, 1.0)
            seam_alpha *= seam_corridor.astype(np.float32)
            blended_lab = (
                result_lab * (1.0 - seam_alpha[..., None])
                + smoothed_lab * seam_alpha[..., None]
            )
            blended_rgb = cv2.cvtColor(
                np.uint8(np.clip(blended_lab, 0, 255)), cv2.COLOR_LAB2RGB
            )
            prior_rgb = result_rgb
            result_rgb = prior_rgb.copy()
            active = seam_corridor & (seam_alpha > 0.01)
            result_rgb[active] = blended_rgb[active]

    # Close the final handful of unprotected pale antialias pixels after the
    # feathered pass. This never crosses the audited skin authority or ink
    # locks and keeps the acceptance metric literal: no connected pale island.
    prefinal_float = result_rgb.astype(np.float32)
    prefinal_hsv = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2HSV)
    prefinal_lab = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    final_pale_antialias = (
        target_skin
        & ~protected
        & (prefinal_float[..., 0] >= 155)
        & (prefinal_float[..., 1] >= 75)
        & (prefinal_float[..., 2] >= 30)
        & (prefinal_float[..., 0] > prefinal_float[..., 1])
        & (prefinal_float[..., 1] > prefinal_float[..., 2])
        & (prefinal_hsv[..., 0] <= 31)
        & (prefinal_hsv[..., 1] >= 25)
        & (prefinal_lab[..., 0] >= 142)
    )
    result_rgb[final_pale_antialias] = np.uint8(
        np.clip(mapped[final_pale_antialias], 0, 255)
    )

    changed = np.any(result_rgb != base, axis=2)
    outside_authority_drift = int(np.count_nonzero(changed & ~target_skin))
    protected_drift = int(np.count_nonzero(changed & protected))
    if outside_authority_drift or protected_drift:
        raise SystemExit(
            "outline finish violated a hard lock: "
            f"outside={outside_authority_drift}, protected={protected_drift}"
        )
    result_float = result_rgb.astype(np.float32)
    result_hsv = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2HSV)
    result_lab = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    residual_pale = (
        target_skin
        & ~protected
        & (result_float[..., 0] >= 155)
        & (result_float[..., 1] >= 75)
        & (result_float[..., 2] >= 30)
        & (result_float[..., 0] > result_float[..., 1])
        & (result_float[..., 1] > result_float[..., 2])
        & (result_hsv[..., 0] <= 31)
        & (result_hsv[..., 1] >= 25)
        & (result_lab[..., 0] >= 142)
    )
    residual_pale, residual_component_sizes = _retained_components(
        residual_pale, 5
    )
    base_edges = cv2.Canny(base_gray, 45, 110) > 0
    result_edges = cv2.Canny(
        cv2.cvtColor(result_rgb, cv2.COLOR_RGB2GRAY), 45, 110
    ) > 0
    result_edge_support = cv2.dilate(
        result_edges.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    ) > 0
    edge_recall = (
        float(np.mean(result_edge_support[base_edges]))
        if np.any(base_edges)
        else 1.0
    )
    old_crop = np.zeros((height, width), dtype=bool)
    left, top = int(box["x"]), int(box["y"])
    side = int(box["width"])
    old_crop[top:top + side, left:left + side] = True
    recovered_outside_crop = pale & ~old_crop

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result_rgb, mode="RGB").save(output_path, "PNG", optimize=True)
    source_card_path = Path(str(base_path) + ".json")
    source_card = (
        json.loads(source_card_path.read_text(encoding="utf-8-sig"))
        if source_card_path.is_file()
        else {}
    )
    if palette_reference is not None:
        variant = "outline-approved-palette-cel-map"
    elif local_donor_fill:
        variant = "outline-connected-local-donor-fill"
    elif smooth_seams and lift_shadows:
        variant = "outline-coverage-shadow-lift-seam-clean"
    elif smooth_seams:
        variant = "outline-coverage-seam-clean"
    elif lift_shadows:
        variant = "outline-coverage-shadow-lift"
    else:
        variant = "outline-coverage"
    metrics = {
        "target_skin_authority_pixels": int(target_skin.sum()),
        "historical_hard_mask_pixels": int(hard.sum()),
        "good_brown_sample_pixels": int(good_brown.sum()),
        "pale_skin_pixels_repaired": int(pale.sum()),
        "pale_components_repaired": len(component_sizes),
        "largest_component_pixels": max(component_sizes, default=0),
        "recovered_outside_historical_crop_pixels": int(recovered_outside_crop.sum()),
        "recovered_above_historical_crop_pixels": int(
            np.count_nonzero(pale & (np.indices(pale.shape)[0] < top))
        ),
        "shadow_pixels_lifted": int(shadow_pixels.sum()),
        "shadow_reference_lab": shadow_reference_lab,
        "unsupported_seam_edge_pixels": int(seam_edges.sum()),
        "unsupported_seam_corridor_pixels": int(seam_corridor.sum()),
        "approved_palette_pixels": int(palette_pixels.sum()),
        "approved_palette_reference": palette_reference_metrics,
        "local_donor_resolved_pixels": local_donor_resolved,
        "protected_feature_drift_pixels": protected_drift,
        "outside_authority_drift_pixels": outside_authority_drift,
        "residual_pale_skin_pixels": int(residual_pale.sum()),
        "residual_pale_components": len(residual_component_sizes),
        "locked_baseline_edge_recall": round(edge_recall, 6),
        "brown_reference_rgb": [round(float(value), 3) for value in brown_reference],
        "pale_reference_rgb": [round(float(value), 3) for value in pale_reference],
        "channel_ratios": [round(float(value), 6) for value in ratios],
    }
    card = {
        "artifact_type": "image",
        "status": "needs_review",
        "purpose": "Locked Vegeta mold; outline-first full-forehead Carey complexion finish",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parent_artifact": str(base_path.resolve()),
        "parent_artifact_sha256": sha256(base_path),
        "parent_card": str(source_card_path.resolve()) if source_card_path.is_file() else None,
        "parent_job_id": source_card.get("job_id"),
        "immutable_target": str(target_path.resolve()),
        "immutable_target_sha256": sha256(target_path),
        "zone_file": str(zone_path.resolve()),
        "method": "locked-baseline-target-connected-outline-completion-v2",
        "variant": variant,
        "locked_features": [
            "face size and placement", "hairline and target ink", "eyes and brows",
            "nose and nostrils", "mouth and lips", "ear detail",
            "Carey beard and jaw edge", "Vegeta hair, armor, and background",
        ],
        "finish_metrics": metrics,
    }
    card_path = Path(str(output_path) + ".json")
    card_path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    return {"output": str(output_path), "card": str(card_path), **metrics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--zone", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--variant",
        choices=(
            "legacy",
            "outline-coverage",
            "outline-shadow-lift",
            "outline-seam-clean",
            "outline-shadow-seam-clean",
            "outline-approved-palette",
            "outline-local-fill",
        ),
        default="outline-coverage",
    )
    parser.add_argument("--palette-reference", type=Path)
    args = parser.parse_args()
    if args.variant == "outline-approved-palette" and args.palette_reference is None:
        parser.error("--palette-reference is required for outline-approved-palette")
    if args.variant == "legacy":
        result = finish(args.base, args.zone, args.output)
    else:
        result = finish_outline_priority(
            args.base,
            args.zone,
            args.output,
            lift_shadows=args.variant in {
                "outline-shadow-lift", "outline-shadow-seam-clean"
            },
            smooth_seams=args.variant in {
                "outline-seam-clean", "outline-shadow-seam-clean"
            },
            palette_reference=(
                args.palette_reference
                if args.variant == "outline-approved-palette"
                else None
            ),
            local_donor_fill=args.variant == "outline-local-fill",
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
