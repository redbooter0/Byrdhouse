#!/usr/bin/env python3
"""Build a local cache of audited target-head geometry masks.

The cache never contains RGB target artwork.  It stores only binary/alpha masks,
closed-contour anchors, hashes, and parameter cards derived from a successful
``byrdfacezone.py`` analysis.  Every generated edit mask is a subset of the
audited editable-skin authority; variants may erode or protect more pixels but
may never expand the authority.

Examples (PowerShell)::

    python scripts/build_head_mold_library.py build `
      --target Images/Targets/anime_games/anime_game_4.jpg `
      --zone-manifest artifacts/face_zones/2026-07/JOB/face_zone.json `
      --library-root artifacts/head_molds

    python scripts/build_head_mold_library.py build-map `
      --map recipes/head_mold_acceptance_map.v1.json `
      --library-root artifacts/head_molds

    python scripts/build_head_mold_library.py verify `
      --mold-dir artifacts/head_molds/MOLD_SHA256

The ``standard48`` profile emits 48 bounded mask variants per target:
4 skin insets x 3 hairline guards x 2 neck policies x 2 feather radii.  Seven
audited targets therefore provide 336 parameterized geometries without
downloading or redistributing character art.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageFilter, ImageOps


SCHEMA_VERSION = 1
MOLD_KIND = "byrdhouse-target-head-mold"
INDEX_KIND = "byrdhouse-target-head-mold-index"
EXPECTED_ZONE_KIND = (
    "closed-head-envelope-minus-independent-hair-outline-plus-neck"
)
DEFAULT_LIBRARY_ROOT = Path("artifacts/head_molds")
MAX_TARGET_BYTES = 200 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CANVAS_EDGE = 4096
MAX_BATCH_TARGETS = 128
MIN_SAFE_PIXELS = 64
MASK_THRESHOLD = 32

REQUIRED_ARTIFACTS = {
    "head": "head_envelope",
    "skin": "hard_mask",
    "lineart": "protected_seed_features",
    "hair_exclusion": "hair_headwear_exclusion",
    "hairline": "hair_boundary",
    "neck": "neck_anchor",
}
OPTIONAL_ARTIFACTS = {
    "protected_color": "protected_color_features",
    "identity_core": "identity_mesh_warp_mask",
}

STANDARD48 = tuple(
    {
        "skin_inset_px": inset,
        "hairline_guard_px": hair_guard,
        "neck_policy": neck_policy,
        "feather_px": feather,
    }
    for inset, hair_guard, neck_policy, feather in product(
        (0, 1, 2, 3),
        (0, 2, 4),
        ("include", "exclude"),
        (0.0, 2.0),
    )
)
VARIANT_PROFILES = {"standard48": STANDARD48}


class MoldError(RuntimeError):
    """Raised when a target cannot produce a trustworthy mold."""


@dataclass(frozen=True)
class ValidatedZone:
    """Loaded authority masks and provenance for one immutable target."""

    target: Path
    target_sha256: str
    target_size: tuple[int, int]
    zone_manifest: Path
    zone_manifest_sha256: str
    zone: dict[str, Any]
    masks: dict[str, Image.Image]
    artifact_sources: dict[str, str]
    anchors: dict[str, Any]
    canvas_size: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise MoldError(f"cannot stat JSON file {path}: {exc}") from exc
    if size > MAX_JSON_BYTES:
        raise MoldError(f"JSON file exceeds {MAX_JSON_BYTES} bytes: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MoldError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MoldError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _checked_file(path: Path, label: str, maximum_bytes: int | None = None) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise MoldError(f"{label} does not exist: {resolved}")
    if maximum_bytes is not None and resolved.stat().st_size > maximum_bytes:
        raise MoldError(f"{label} exceeds {maximum_bytes} bytes: {resolved}")
    return resolved


def _target_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except Exception as exc:  # Pillow exposes several decoder exceptions.
        raise MoldError(f"target image cannot be decoded: {path}: {exc}") from exc
    if width <= 0 or height <= 0:
        raise MoldError(f"target image has invalid dimensions: {width}x{height}")
    if width > 16384 or height > 16384:
        raise MoldError(f"target image is too large: {width}x{height}")
    return width, height


def _artifact_path(raw: Any, zone_manifest: Path, key: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise MoldError(f"face-zone manifest lacks authoritative artifact: {key}")
    path = Path(raw)
    if not path.is_absolute():
        path = zone_manifest.parent / path
    return _checked_file(path, f"face-zone artifact {key}")


def _binary_mask(path: Path, expected_size: tuple[int, int], label: str) -> Image.Image:
    try:
        with Image.open(path) as image:
            if image.size != expected_size:
                raise MoldError(
                    f"{label} dimensions {image.size} do not match canvas "
                    f"{expected_size}"
                )
            mask = image.convert("L").point(
                lambda value: 255 if value >= MASK_THRESHOLD else 0
            )
            mask.load()
    except MoldError:
        raise
    except Exception as exc:
        raise MoldError(f"cannot decode {label} mask {path}: {exc}") from exc
    return mask


def mask_pixels(mask: Image.Image) -> int:
    histogram = mask.convert("L").histogram()
    return sum(index * count for index, count in enumerate(histogram)) // 255


def mask_union(*masks: Image.Image) -> Image.Image:
    if not masks:
        raise MoldError("mask union requires at least one mask")
    result = masks[0].copy()
    for mask in masks[1:]:
        result = ImageChops.lighter(result, mask)
    return result


def mask_subtract(base: Image.Image, excluded: Image.Image) -> Image.Image:
    return ImageChops.subtract(base, excluded)


def mask_intersection_pixels(left: Image.Image, right: Image.Image) -> int:
    return mask_pixels(ImageChops.multiply(left, right))


def _dilate(mask: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return mask.copy()
    return mask.filter(ImageFilter.MaxFilter(radius * 2 + 1))


def _erode(mask: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return mask.copy()
    return mask.filter(ImageFilter.MinFilter(radius * 2 + 1))


def _traversal(zone: dict[str, Any]) -> dict[str, Any]:
    parser = zone.get("semantic_parser") or {}
    head_contour = parser.get("head_contour") or {}
    traversal = head_contour.get("body_part_traversal") or {}
    if not traversal:
        for stage in (zone.get("upload_analysis") or {}).get("stages") or []:
            if (
                isinstance(stage, dict)
                and stage.get("id")
                == "neck-left-to-top-to-right-to-neck-closed-loop"
            ):
                traversal = stage.get("traversal") or {}
                break
    if not traversal.get("passed") or not traversal.get("closed"):
        raise MoldError("closed neck-to-head traversal did not pass")
    checkpoints = traversal.get("checkpoints") or {}
    required = ("neck_left", "left_outer", "top", "right_outer", "neck_right")
    for name in required:
        point = checkpoints.get(name)
        if not isinstance(point, dict):
            raise MoldError(f"closed traversal lacks checkpoint: {name}")
        if not isinstance(point.get("x"), (int, float)) or not isinstance(
            point.get("y"), (int, float)
        ):
            raise MoldError(f"closed traversal checkpoint is invalid: {name}")
    return traversal


def _anchors(zone: dict[str, Any], canvas_size: int) -> dict[str, Any]:
    traversal = _traversal(zone)
    normalized: dict[str, dict[str, float]] = {}
    for name, point in (traversal.get("checkpoints") or {}).items():
        if isinstance(point, dict) and isinstance(point.get("x"), (int, float)):
            normalized[name] = {
                "x": round(float(point["x"]) / canvas_size, 8),
                "y": round(float(point["y"]) / canvas_size, 8),
            }
    analysis = zone.get("upload_analysis") or {}
    contract = analysis.get("acceptance_contract") or {}
    inventory = analysis.get("pixel_feature_inventory") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "coordinate_space": {
            "width": canvas_size,
            "height": canvas_size,
            "origin": "top-left",
        },
        "crop_box": zone.get("crop_box"),
        "closed_head_traversal": {
            "order": traversal.get("order"),
            "checkpoints": traversal.get("checkpoints"),
            "normalized_checkpoints": normalized,
        },
        "target_feature_lock": contract.get("target_feature_lock"),
        "geometry_expression_pose": (
            inventory.get("geometry_expression_pose")
            if isinstance(inventory, dict)
            else None
        ),
    }


def validate_zone(target: Path, zone_manifest: Path) -> ValidatedZone:
    """Load and validate one immutable target plus audited face-zone manifest."""

    target = _checked_file(target, "target image", MAX_TARGET_BYTES)
    zone_manifest = _checked_file(zone_manifest, "face-zone manifest", MAX_JSON_BYTES)
    target_sha = sha256_file(target)
    target_size = _target_size(target)
    zone = read_json(zone_manifest)

    if zone.get("source_sha256") != target_sha:
        raise MoldError(
            "target SHA-256 does not match face-zone source_sha256; refusing "
            "to reuse another image's masks"
        )
    if zone.get("manual_zone"):
        raise MoldError("manual/rectangle zones are not authoritative head molds")
    if zone.get("zone_kind") != EXPECTED_ZONE_KIND:
        raise MoldError(
            f"unsupported zone_kind {zone.get('zone_kind')!r}; expected "
            f"{EXPECTED_ZONE_KIND!r}"
        )
    analysis = zone.get("upload_analysis") or {}
    if analysis.get("all_passed") is not True:
        raise MoldError("face-zone upload analysis did not pass")
    preflight = zone.get("crop_preflight") or {}
    if preflight.get("passed") is not True:
        raise MoldError("face-zone crop preflight did not pass")
    _traversal(zone)

    canvas_size = zone.get("canvas_size")
    if not isinstance(canvas_size, int) or not (32 <= canvas_size <= MAX_CANVAS_EDGE):
        raise MoldError(f"invalid face-zone canvas_size: {canvas_size!r}")
    expected_size = (canvas_size, canvas_size)
    artifacts = zone.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        raise MoldError("face-zone artifacts must be an object")

    masks: dict[str, Image.Image] = {}
    sources: dict[str, str] = {}
    for component, artifact_key in REQUIRED_ARTIFACTS.items():
        path = _artifact_path(artifacts.get(artifact_key), zone_manifest, artifact_key)
        masks[component] = _binary_mask(path, expected_size, artifact_key)
        sources[component] = str(path)

    for component, artifact_key in OPTIONAL_ARTIFACTS.items():
        raw = artifacts.get(artifact_key)
        if not raw:
            continue
        path = _artifact_path(raw, zone_manifest, artifact_key)
        masks[component] = _binary_mask(path, expected_size, artifact_key)
        sources[component] = str(path)

    for required in REQUIRED_ARTIFACTS:
        if mask_pixels(masks[required]) <= 0:
            raise MoldError(f"authoritative {required} mask is empty")

    skin_outside_head = mask_pixels(mask_subtract(masks["skin"], masks["head"]))
    if skin_outside_head:
        raise MoldError(
            f"editable skin escapes the closed head authority by "
            f"{skin_outside_head} pixels"
        )
    if mask_intersection_pixels(masks["neck"], masks["skin"]) <= 0:
        raise MoldError("neck anchor does not intersect editable skin")

    protected_parts = [masks["hair_exclusion"], masks["lineart"]]
    if "protected_color" in masks:
        protected_parts.append(masks["protected_color"])
    masks["protected"] = mask_union(*protected_parts)
    safe_skin = mask_subtract(masks["skin"], masks["protected"])
    if mask_pixels(safe_skin) < MIN_SAFE_PIXELS:
        raise MoldError("audited mold has too little editable skin after protections")

    return ValidatedZone(
        target=target,
        target_sha256=target_sha,
        target_size=target_size,
        zone_manifest=zone_manifest,
        zone_manifest_sha256=sha256_file(zone_manifest),
        zone=zone,
        masks=masks,
        artifact_sources=sources,
        anchors=_anchors(zone, canvas_size),
        canvas_size=canvas_size,
    )


def _artifact_card(
    *,
    artifact_kind: str,
    purpose: str,
    content_sha256: str,
    validated: ValidatedZone,
    derivation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": artifact_kind,
        "purpose": purpose,
        "content_sha256": content_sha256,
        "target_sha256": validated.target_sha256,
        "parent_zone_manifest_sha256": validated.zone_manifest_sha256,
        "derivation": derivation,
        "license_scope": (
            "local-derived-geometry-only; contains no RGB target artwork"
        ),
    }


def _save_mask(
    path: Path,
    mask: Image.Image,
    *,
    validated: ValidatedZone,
    purpose: str,
    derivation: dict[str, Any],
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    mask.convert("L").save(path, "PNG", optimize=True)
    digest = sha256_file(path)
    card = _artifact_card(
        artifact_kind="head-mold-mask",
        purpose=purpose,
        content_sha256=digest,
        validated=validated,
        derivation=derivation,
    )
    card_path = path.with_name(path.name + ".card.json")
    write_json(card_path, card)
    return {
        "path": path.name,
        "card": card_path.name,
        "sha256": digest,
        "pixels": mask_pixels(mask),
    }


def _variant_mask(
    masks: dict[str, Image.Image], parameters: dict[str, Any]
) -> Image.Image:
    inset = int(parameters["skin_inset_px"])
    hair_guard = int(parameters["hairline_guard_px"])
    feather = float(parameters["feather_px"])
    neck_policy = str(parameters["neck_policy"])

    allowed = _erode(masks["skin"], inset)
    guard = mask_union(masks["protected"], _dilate(masks["hairline"], hair_guard))
    allowed = mask_subtract(allowed, guard)
    if neck_policy == "exclude":
        allowed = mask_subtract(allowed, masks["neck"])
    elif neck_policy != "include":
        raise MoldError(f"unknown neck policy: {neck_policy}")
    if mask_pixels(allowed) < MIN_SAFE_PIXELS:
        raise MoldError(f"variant has too little safe authority: {parameters}")
    if feather > 0:
        blurred = allowed.filter(ImageFilter.GaussianBlur(radius=feather))
        allowed = ImageChops.multiply(blurred, allowed)
    return allowed


def _profile(name: str) -> tuple[dict[str, Any], ...]:
    try:
        return VARIANT_PROFILES[name]
    except KeyError as exc:
        raise MoldError(f"unknown variant profile: {name}") from exc


def _safe_remove_tree(path: Path, root: Path) -> None:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved == root_resolved or root_resolved not in resolved.parents:
        raise MoldError(f"refusing to remove path outside library root: {resolved}")
    shutil.rmtree(resolved)


def build_mold(
    target: Path,
    zone_manifest: Path,
    library_root: Path = DEFAULT_LIBRARY_ROOT,
    *,
    profile_name: str = "standard48",
    replace: bool = False,
) -> dict[str, Any]:
    """Build or reuse one SHA-keyed mold directory."""

    validated = validate_zone(target, zone_manifest)
    profile = _profile(profile_name)
    library_root = library_root.expanduser().resolve()
    library_root.mkdir(parents=True, exist_ok=True)
    final_dir = library_root / validated.target_sha256
    final_manifest = final_dir / "mold.json"

    if final_manifest.is_file() and not replace:
        existing = read_json(final_manifest)
        same_authority = (
            existing.get("target_sha256") == validated.target_sha256
            and existing.get("zone_manifest_sha256")
            == validated.zone_manifest_sha256
            and existing.get("variant_profile") == profile_name
        )
        if not same_authority:
            raise MoldError(
                f"cache key already exists with different authority: {final_dir}; "
                "use --replace only after reviewing the new zone"
            )
        verification = verify_mold(final_dir)
        refresh_index(library_root)
        return {
            "status": "cache_hit",
            "mold_dir": str(final_dir),
            "target_sha256": validated.target_sha256,
            "variant_count": verification["variant_count"],
        }

    staging = library_root / f".{validated.target_sha256}.{uuid.uuid4().hex}.staging"
    if staging.exists():
        raise MoldError(f"unexpected staging collision: {staging}")
    staging.mkdir(parents=False)
    try:
        component_inputs = {
            "head": validated.masks["head"],
            "skin": validated.masks["skin"],
            "lineart": validated.masks["lineart"],
            "protected": validated.masks["protected"],
            "hairline": validated.masks["hairline"],
            "neck": validated.masks["neck"],
        }
        if "identity_core" in validated.masks:
            component_inputs["identity_core"] = validated.masks["identity_core"]

        component_purposes = {
            "head": "closed target head-and-neck envelope",
            "skin": "maximum audited editable exposed-skin authority",
            "lineart": "target feature ink that must remain target-authentic",
            "protected": "union of hair, accessories, clothing, and feature locks",
            "hairline": "independently traced hair/headwear boundary guard",
            "neck": "connected neck anchor and handoff authority",
            "identity_core": "validated inner identity-mesh authority when available",
        }
        components: dict[str, Any] = {}
        for name, mask in component_inputs.items():
            components[name] = _save_mask(
                staging / f"{name}.png",
                mask,
                validated=validated,
                purpose=component_purposes[name],
                derivation={
                    "kind": "normalized-authoritative-mask",
                    "source_artifact": validated.artifact_sources.get(name),
                    "threshold": MASK_THRESHOLD,
                },
            )

        anchors_path = staging / "anchors.json"
        anchors_payload = dict(validated.anchors)
        anchors_payload.update(
            {
                "target_sha256": validated.target_sha256,
                "parent_zone_manifest_sha256": validated.zone_manifest_sha256,
            }
        )
        write_json(anchors_path, anchors_payload)
        anchors_sha = sha256_file(anchors_path)
        anchors_card = _artifact_card(
            artifact_kind="head-mold-anchors",
            purpose="closed traversal and semantic feature anchors",
            content_sha256=anchors_sha,
            validated=validated,
            derivation={"kind": "face-zone-manifest-coordinate-extraction"},
        )
        write_json(staging / "anchors.json.card.json", anchors_card)

        variants: list[dict[str, Any]] = []
        variants_dir = staging / "variants"
        for index, parameters in enumerate(profile, start=1):
            variant_id = f"v{index:03d}"
            variant = _variant_mask(validated.masks, parameters)
            output = variants_dir / f"{variant_id}.png"
            saved = _save_mask(
                output,
                variant,
                validated=validated,
                purpose="bounded target-head edit authority variant",
                derivation={
                    "kind": "subset-only-geometry-variant",
                    "base": "skin.png",
                    "operations": [
                        "erode-editable-skin",
                        "subtract-protected-and-hairline-guard",
                        "optionally-subtract-neck",
                        "inward-only-feather",
                    ],
                    "parameters": parameters,
                    "invariant": "alpha-support-is-subset-of-audited-skin",
                },
            )
            variants.append(
                {
                    "id": variant_id,
                    "path": f"variants/{saved['path']}",
                    "card": f"variants/{saved['card']}",
                    "sha256": saved["sha256"],
                    "nonzero_alpha_pixels": saved["pixels"],
                    "parameters": parameters,
                }
            )

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "kind": MOLD_KIND,
            "created_at": utc_now(),
            "cache_key": validated.target_sha256,
            "target_sha256": validated.target_sha256,
            "target_basename": validated.target.name,
            "target_dimensions": {
                "width": validated.target_size[0],
                "height": validated.target_size[1],
            },
            "contains_rgb_target_artwork": False,
            "content_policy": (
                "local derived geometry only; no downloaded character art or "
                "external PNG parts"
            ),
            "zone_manifest_sha256": validated.zone_manifest_sha256,
            "zone_kind": validated.zone.get("zone_kind"),
            "zone_processor": validated.zone.get("processor"),
            "semantic_parser": {
                "name": (validated.zone.get("semantic_parser") or {}).get("name"),
                "license": (validated.zone.get("semantic_parser") or {}).get(
                    "license"
                ),
                "deployment_scope": (
                    validated.zone.get("semantic_parser") or {}
                ).get("deployment_scope"),
            },
            "canvas_size": validated.canvas_size,
            "authority_contract": {
                "upload_analysis_passed": True,
                "crop_preflight_passed": True,
                "closed_head_traversal_passed": True,
                "manual_or_rectangle_zone": False,
                "variants_may_expand_authority": False,
            },
            "components": components,
            "anchors": {
                "path": "anchors.json",
                "card": "anchors.json.card.json",
                "sha256": anchors_sha,
            },
            "variant_profile": profile_name,
            "variant_count": len(variants),
            "variants": variants,
        }
        write_json(staging / "mold.json", manifest)

        if final_dir.exists():
            if not replace:
                raise MoldError(f"cache directory already exists: {final_dir}")
            previous = library_root / f".{validated.target_sha256}.previous.{uuid.uuid4().hex}"
            final_dir.rename(previous)
            staging.rename(final_dir)
            _safe_remove_tree(previous, library_root)
        else:
            staging.rename(final_dir)
    except Exception:
        if staging.exists():
            _safe_remove_tree(staging, library_root)
        raise

    verification = verify_mold(final_dir)
    refresh_index(library_root)
    return {
        "status": "built",
        "mold_dir": str(final_dir),
        "target_sha256": validated.target_sha256,
        "variant_count": verification["variant_count"],
    }


def verify_mold(mold_dir: Path) -> dict[str, Any]:
    """Verify cards, hashes, and mask containment for an existing mold."""

    mold_dir = mold_dir.expanduser().resolve()
    manifest = read_json(_checked_file(mold_dir / "mold.json", "mold manifest"))
    if manifest.get("kind") != MOLD_KIND:
        raise MoldError(f"not a {MOLD_KIND} manifest: {mold_dir}")
    if manifest.get("contains_rgb_target_artwork") is not False:
        raise MoldError("mold must explicitly declare that it contains no RGB artwork")
    expected_size = (int(manifest["canvas_size"]), int(manifest["canvas_size"]))

    loaded: dict[str, Image.Image] = {}
    for name, record in (manifest.get("components") or {}).items():
        if not isinstance(record, dict):
            raise MoldError(f"component record is invalid: {name}")
        path = _checked_file(mold_dir / str(record.get("path")), f"component {name}")
        card_path = _checked_file(
            mold_dir / str(record.get("card")), f"component card {name}"
        )
        digest = sha256_file(path)
        if digest != record.get("sha256"):
            raise MoldError(f"component hash mismatch: {name}")
        card = read_json(card_path)
        if card.get("content_sha256") != digest:
            raise MoldError(f"component card hash mismatch: {name}")
        loaded[name] = _binary_mask(path, expected_size, f"cached {name}")

    for required in ("head", "skin", "lineart", "protected", "hairline", "neck"):
        if required not in loaded:
            raise MoldError(f"cached mold lacks component: {required}")
    if mask_pixels(mask_subtract(loaded["skin"], loaded["head"])):
        raise MoldError("cached skin escapes cached head authority")

    anchors_record = manifest.get("anchors") or {}
    anchors_path = _checked_file(
        mold_dir / str(anchors_record.get("path")), "anchors artifact"
    )
    anchors_card_path = _checked_file(
        mold_dir / str(anchors_record.get("card")), "anchors card"
    )
    anchors_digest = sha256_file(anchors_path)
    if anchors_digest != anchors_record.get("sha256"):
        raise MoldError("anchors hash mismatch")
    if read_json(anchors_card_path).get("content_sha256") != anchors_digest:
        raise MoldError("anchors card hash mismatch")

    variants = manifest.get("variants") or []
    if len(variants) != manifest.get("variant_count"):
        raise MoldError("variant count does not match mold manifest")
    for record in variants:
        variant_id = str(record.get("id"))
        path = _checked_file(
            mold_dir / str(record.get("path")), f"variant {variant_id}"
        )
        card_path = _checked_file(
            mold_dir / str(record.get("card")), f"variant card {variant_id}"
        )
        digest = sha256_file(path)
        if digest != record.get("sha256"):
            raise MoldError(f"variant hash mismatch: {variant_id}")
        if read_json(card_path).get("content_sha256") != digest:
            raise MoldError(f"variant card hash mismatch: {variant_id}")
        mask = _binary_mask(path, expected_size, f"cached variant {variant_id}")
        if mask_pixels(mask) < MIN_SAFE_PIXELS:
            raise MoldError(f"variant is empty or too small: {variant_id}")
        if mask_pixels(mask_subtract(mask, loaded["skin"])):
            raise MoldError(f"variant escapes skin authority: {variant_id}")
        if mask_intersection_pixels(mask, loaded["protected"]):
            raise MoldError(f"variant overlaps protected pixels: {variant_id}")
        if mask_intersection_pixels(mask, loaded["hairline"]):
            raise MoldError(f"variant overlaps hairline pixels: {variant_id}")

    return {
        "status": "verified",
        "mold_dir": str(mold_dir),
        "target_sha256": manifest.get("target_sha256"),
        "variant_count": len(variants),
    }


def refresh_index(library_root: Path) -> dict[str, Any]:
    """Rebuild the small library index from committed mold manifests."""

    library_root = library_root.expanduser().resolve()
    library_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for manifest_path in sorted(library_root.glob("[0-9a-f]" * 64 + "/mold.json")):
        manifest = read_json(manifest_path)
        if manifest.get("kind") != MOLD_KIND:
            raise MoldError(f"unexpected manifest kind: {manifest_path}")
        entries.append(
            {
                "target_sha256": manifest.get("target_sha256"),
                "target_basename": manifest.get("target_basename"),
                "mold_manifest": str(manifest_path.relative_to(library_root)),
                "zone_manifest_sha256": manifest.get("zone_manifest_sha256"),
                "variant_profile": manifest.get("variant_profile"),
                "variant_count": manifest.get("variant_count"),
            }
        )
    index = {
        "schema_version": SCHEMA_VERSION,
        "kind": INDEX_KIND,
        "updated_at": utc_now(),
        "mold_count": len(entries),
        "total_parameterized_variants": sum(
            int(entry.get("variant_count") or 0) for entry in entries
        ),
        "molds": entries,
    }
    write_json(library_root / "index.json", index)
    return index


def _resolve_map_path(value: Any, mapping_path: Path, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise MoldError(f"build map entry lacks {label}")
    path = Path(value)
    if not path.is_absolute():
        path = mapping_path.parent / path
    return path


def build_map(
    mapping_path: Path,
    library_root: Path = DEFAULT_LIBRARY_ROOT,
    *,
    profile_name: str = "standard48",
    replace: bool = False,
) -> dict[str, Any]:
    """Preflight and build an explicit target-to-zone mapping."""

    mapping_path = _checked_file(mapping_path, "head-mold build map", MAX_JSON_BYTES)
    mapping = read_json(mapping_path)
    entries = mapping.get("targets")
    if not isinstance(entries, list) or not entries:
        raise MoldError("build map targets must be a non-empty list")
    if len(entries) > MAX_BATCH_TARGETS:
        raise MoldError(f"build map exceeds {MAX_BATCH_TARGETS} targets")

    resolved: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise MoldError(f"build map entry {index} must be an object")
        target = _resolve_map_path(entry.get("target"), mapping_path, "target")
        zone = _resolve_map_path(
            entry.get("zone_manifest"), mapping_path, "zone_manifest"
        )
        validated = validate_zone(target, zone)
        if validated.target_sha256 in seen:
            raise MoldError(
                f"duplicate target SHA-256 in build map: {validated.target_sha256}"
            )
        seen.add(validated.target_sha256)
        resolved.append((target, zone))

    results = [
        build_mold(
            target,
            zone,
            library_root,
            profile_name=profile_name,
            replace=replace,
        )
        for target, zone in resolved
    ]
    index = refresh_index(library_root)
    return {
        "status": "built_map",
        "targets": len(results),
        "results": results,
        "mold_count": index["mold_count"],
        "total_parameterized_variants": index[
            "total_parameterized_variants"
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a SHA-256-keyed local head-mold cache from audited "
            "byrdfacezone artifacts. Fails closed on missing authority and "
            "never stores RGB target artwork."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build one audited target mold")
    build.add_argument("--target", type=Path, required=True)
    build.add_argument("--zone-manifest", type=Path, required=True)
    build.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    build.add_argument("--profile", choices=sorted(VARIANT_PROFILES), default="standard48")
    build.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing SHA cache only after reviewing the new zone",
    )

    bulk = subparsers.add_parser(
        "build-map", help="preflight and build an explicit JSON target/zone map"
    )
    bulk.add_argument("--map", type=Path, required=True)
    bulk.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    bulk.add_argument("--profile", choices=sorted(VARIANT_PROFILES), default="standard48")
    bulk.add_argument("--replace", action="store_true")

    verify = subparsers.add_parser("verify", help="verify one cached mold")
    verify.add_argument("--mold-dir", type=Path, required=True)

    index = subparsers.add_parser("index", help="rebuild the library index")
    index.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "build":
            result = build_mold(
                args.target,
                args.zone_manifest,
                args.library_root,
                profile_name=args.profile,
                replace=args.replace,
            )
        elif args.command == "build-map":
            result = build_map(
                args.map,
                args.library_root,
                profile_name=args.profile,
                replace=args.replace,
            )
        elif args.command == "verify":
            result = verify_mold(args.mold_dir)
        elif args.command == "index":
            result = refresh_index(args.library_root)
        else:  # pragma: no cover - argparse enforces commands.
            raise MoldError(f"unsupported command: {args.command}")
    except MoldError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
