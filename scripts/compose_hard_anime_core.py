#!/usr/bin/env python3
"""Blend an audited identity-core donor into a locked hard-anime mold."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from finish_locked_complexion import _embedded_mask, load_rgb, sha256


def retained_components(mask: np.ndarray, minimum: int = 5) -> tuple[np.ndarray, int]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    kept = np.zeros(mask.shape, dtype=bool)
    components = 0
    for index in range(1, count):
        if int(stats[index, cv2.CC_STAT_AREA]) >= minimum:
            kept |= labels == index
            components += 1
    return kept, components


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--zone", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strength", type=float, required=True)
    args = parser.parse_args()

    if not 0.05 <= args.strength <= 0.70:
        raise SystemExit("strength must be between 0.05 and 0.70")
    base = load_rgb(args.base)
    donor = load_rgb(args.donor)
    if base.shape != donor.shape:
        raise SystemExit("base and donor dimensions must match")
    zone = json.loads(args.zone.read_text(encoding="utf-8-sig"))
    artifacts = dict(zone.get("artifacts") or {})
    box = dict(zone.get("crop_box") or {})
    if not artifacts.get("identity_mesh_warp_mask") or not box:
        raise SystemExit("audited identity mesh mask and crop box are required")
    height, width = base.shape[:2]
    core = _embedded_mask(
        artifacts["identity_mesh_warp_mask"], box, (height, width), threshold=32
    )
    skin_authority = _embedded_mask(
        artifacts["hard_mask"], box, (height, width), threshold=32
    )
    hair = _embedded_mask(
        artifacts["hair_headwear_exclusion"], box, (height, width), threshold=32
    )
    protected_paths = [
        artifacts.get("protected_seed_features"),
        artifacts.get("protected_color_features"),
    ]
    protected = hair.copy()
    for path in protected_paths:
        if path and Path(path).is_file():
            protected |= _embedded_mask(path, box, (height, width), threshold=32)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    inner = cv2.erode(core.astype(np.uint8), kernel) > 0
    boundary = core & ~inner
    allowed = inner & ~protected
    if int(allowed.sum()) < 512:
        raise SystemExit("identity core has too little safe interior authority")

    base_lab = cv2.cvtColor(base, cv2.COLOR_RGB2LAB).astype(np.float32)
    donor_lab = cv2.cvtColor(donor, cv2.COLOR_RGB2LAB).astype(np.float32)
    base_values = base_lab[allowed]
    donor_values = donor_lab[allowed]
    delta = np.median(base_values, axis=0) - np.median(donor_values, axis=0)
    delta[0] = np.clip(delta[0], -16.0, 16.0)
    delta[1:] = np.clip(delta[1:], -8.0, 8.0)
    donor_lab += delta[None, None, :]
    donor_harmonized = cv2.cvtColor(
        np.uint8(np.clip(donor_lab, 0, 255)), cv2.COLOR_LAB2RGB
    )

    alpha = cv2.GaussianBlur(allowed.astype(np.float32), (0, 0), 3.2)
    alpha = np.clip(alpha * float(args.strength), 0.0, float(args.strength))
    alpha *= allowed.astype(np.float32)
    result = np.uint8(
        np.clip(
            base.astype(np.float32) * (1.0 - alpha[..., None])
            + donor_harmonized.astype(np.float32) * alpha[..., None],
            0,
            255,
        )
    )
    result[boundary | protected | ~core] = base[boundary | protected | ~core]

    changed = np.any(result != base, axis=2)
    outside_drift = int(np.count_nonzero(changed & ~core))
    protected_drift = int(np.count_nonzero(changed & protected))
    if outside_drift or protected_drift:
        raise SystemExit(
            f"hard lock violated: outside={outside_drift}, protected={protected_drift}"
        )

    result_float = result.astype(np.float32)
    hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(result, cv2.COLOR_RGB2LAB).astype(np.float32)
    pale = (
        core
        & skin_authority
        & ~protected
        & (result_float[..., 0] >= 155)
        & (result_float[..., 1] >= 75)
        & (result_float[..., 2] >= 30)
        & (result_float[..., 0] > result_float[..., 1])
        & (result_float[..., 1] > result_float[..., 2])
        & (hsv[..., 0] <= 31)
        & (hsv[..., 1] >= 25)
        & (lab[..., 0] >= 142)
    )
    pale, pale_components = retained_components(pale)
    rejected_donor_pale_pixels = int(pale.sum())
    if rejected_donor_pale_pixels:
        result[pale] = base[pale]
        changed = np.any(result != base, axis=2)
        outside_drift = int(np.count_nonzero(changed & ~core))
        protected_drift = int(np.count_nonzero(changed & protected))
        result_float = result.astype(np.float32)
        hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV)
        lab = cv2.cvtColor(result, cv2.COLOR_RGB2LAB).astype(np.float32)
        pale = (
            core
            & skin_authority
            & ~protected
            & (result_float[..., 0] >= 155)
            & (result_float[..., 1] >= 75)
            & (result_float[..., 2] >= 30)
            & (result_float[..., 0] > result_float[..., 1])
            & (result_float[..., 1] > result_float[..., 2])
            & (hsv[..., 0] <= 31)
            & (hsv[..., 1] >= 25)
            & (lab[..., 0] >= 142)
        )
        pale, pale_components = retained_components(pale)

    repaired_residual_pale_pixels = int(pale.sum())
    if repaired_residual_pale_pixels:
        current = result.astype(np.float32)
        current_hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV)
        current_lab = cv2.cvtColor(result, cv2.COLOR_RGB2LAB).astype(np.float32)
        good_brown = (
            allowed
            & (current[..., 0] >= 60)
            & (current[..., 0] <= 194)
            & (current[..., 1] >= 20)
            & (current[..., 1] <= 126)
            & (current[..., 2] <= 125)
            & (current[..., 0] >= current[..., 1] * 1.22)
            & (current_hsv[..., 0] <= 25)
            & (current_lab[..., 0] <= 138)
        )
        if int(good_brown.sum()) < 256:
            raise SystemExit("bounded core has too little accepted brown skin")
        brown_reference = np.percentile(current[good_brown], 67, axis=0)
        pale_reference = np.median(current[pale], axis=0)
        ratios = np.clip(
            brown_reference / np.maximum(pale_reference, 1.0), 0.30, 0.82
        )
        result[pale] = np.uint8(
            np.clip(current[pale] * ratios[None, :], 0, 255)
        )
        changed = np.any(result != base, axis=2)
        outside_drift = int(np.count_nonzero(changed & ~core))
        protected_drift = int(np.count_nonzero(changed & protected))
        result_float = result.astype(np.float32)
        hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV)
        lab = cv2.cvtColor(result, cv2.COLOR_RGB2LAB).astype(np.float32)
        pale = (
            core
            & skin_authority
            & ~protected
            & (result_float[..., 0] >= 155)
            & (result_float[..., 1] >= 75)
            & (result_float[..., 2] >= 30)
            & (result_float[..., 0] > result_float[..., 1])
            & (result_float[..., 1] > result_float[..., 2])
            & (hsv[..., 0] <= 31)
            & (hsv[..., 1] >= 25)
            & (lab[..., 0] >= 142)
        )
        pale, pale_components = retained_components(pale)
    base_edges = cv2.Canny(cv2.cvtColor(base, cv2.COLOR_RGB2GRAY), 45, 110) > 0
    result_edges = cv2.Canny(cv2.cvtColor(result, cv2.COLOR_RGB2GRAY), 45, 110) > 0
    edge_support = cv2.dilate(
        result_edges.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    ) > 0
    edge_recall = float(np.mean(edge_support[base_edges])) if np.any(base_edges) else 1.0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result, mode="RGB").save(args.output, "PNG", optimize=True)
    metrics = {
        "strength": round(float(args.strength), 4),
        "core_pixels": int(core.sum()),
        "core_skin_authority_pixels": int((core & skin_authority).sum()),
        "safe_inner_core_pixels": int(allowed.sum()),
        "changed_pixels": int(changed.sum()),
        "outside_core_drift_pixels": outside_drift,
        "protected_feature_drift_pixels": protected_drift,
        "rejected_donor_pale_pixels": rejected_donor_pale_pixels,
        "repaired_residual_pale_pixels": repaired_residual_pale_pixels,
        "residual_pale_skin_pixels": int(pale.sum()),
        "residual_pale_components": pale_components,
        "locked_baseline_edge_recall": round(edge_recall, 6),
        "donor_lab_correction": [round(float(value), 3) for value in delta],
    }
    card = {
        "artifact_type": "image",
        "status": "needs_review",
        "purpose": "Vegeta locked-mold bounded identity-core composite",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base": str(args.base.resolve()),
        "base_sha256": sha256(args.base),
        "identity_donor": str(args.donor.resolve()),
        "identity_donor_sha256": sha256(args.donor),
        "zone_file": str(args.zone.resolve()),
        "method": "locked-hard-anime-mold-plus-bounded-identity-core-v1",
        "locked_features": [
            "forehead and widow peak", "hair and skull silhouette", "ear outline",
            "outer jaw and neck boundary", "armor", "background",
        ],
        "metrics": metrics,
    }
    Path(str(args.output) + ".json").write_text(
        json.dumps(card, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "card": str(args.output) + ".json", **metrics}, indent=2))


if __name__ == "__main__":
    main()
