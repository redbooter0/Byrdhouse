"""Build an installed ComfyUI mask graph and inspect its saved outputs.

This module never segments or renders images itself. CPU FaceParsing and core
ComfyUI nodes create the masks; Pillow/numpy only inspect collected PNGs.
Schemas and label mappings were checked locally on 2026-10-03.
"""
import hashlib
import io
import re
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image, ImageOps


class MaskError(ValueError):
    pass


GUARD_PIXELS = 8
# Keep the pixel-exact semantic core inside the actual hair/skin boundary so
# source background colors cannot form a hard halo around thin curls.
CORE_SHRINK_PIXELS = 5
# Installed ResultsParser parameter names, not inferred left/right anatomy.
PARSER_FLAG_TO_LABEL_ID = {
    "background": 0, "skin": 1, "nose": 2, "eye_g": 3,
    "r_eye": 4, "l_eye": 5, "r_brow": 6, "l_brow": 7,
    "r_ear": 8, "l_ear": 9, "mouth": 10, "u_lip": 11,
    "l_lip": 12, "hair": 13, "hat": 14, "ear_r": 15,
    "neck_l": 16, "neck": 17, "cloth": 18,
}
# Actual id2label in the installed jonathandinu/face-parsing config.json.
LABEL_ID_TO_NAME = {
    0: "background", 1: "skin", 2: "nose", 3: "eye_g",
    4: "l_eye", 5: "r_eye", 6: "l_brow", 7: "r_brow",
    8: "l_ear", 9: "r_ear", 10: "mouth", 11: "u_lip",
    12: "l_lip", 13: "hair", 14: "hat", 15: "ear_r",
    16: "neck_l", 17: "neck", 18: "cloth",
}
REGION_LABEL_IDS = {"background": {0}, "clothing": {18}}
COVERAGE_LIMIT = (
    "Face parsing is an unreviewed estimate, not identity proof. Inspect the "
    "entire afro including thin curls, forehead/hairline, ears, beard, neck "
    "and accessories. Background may contain missed foreground hands/body. "
    "Clothing may not cover a new garment silhouette. Multi-person selection "
    "is not resolved. The labels output is a color preview, not raw class IDs; "
    "per-class coverage counts cannot be recovered reliably from that PNG."
)


def _region_ids(region):
    if not isinstance(region, str) or region not in REGION_LABEL_IDS:
        raise MaskError("Mask region must be background or clothing")
    return REGION_LABEL_IDS[region]


def build_mask_graph(input_name, job_id, region="background", *, illustrated=False):
    """Return (API graph, save_nodes) for native-size CPU semantic masks.

    save_nodes includes the semantic review masks plus BiRefNet's soft
    foreground alpha. The parser guards feature coverage; the alpha is used
    only to blend the original person over a generated background.
    The protected output includes the eight-pixel conservative head guard.
    All parser toggles are explicit: upstream defaults include clothing.
    The caller owns immutable input snapshots, submission and collection.
    """
    ids = _region_ids(region)
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", job_id):
        raise MaskError("A safe job ID is required for mask output prefixes")
    if not isinstance(input_name, str) or not input_name or input_name != input_name.strip():
        raise MaskError("A relative ComfyUI input name is required")
    normalized = input_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (path.is_absolute() or ":" in normalized or ".." in path.parts
            or any(ord(c) < 32 for c in normalized) or normalized in (".", "/")):
        raise MaskError("A relative ComfyUI input name without traversal is required")

    def parser(selected):
        return {"class_type": "FaceParsingResultsParser(FaceParsing)",
                "inputs": {"result": ["parse", 1], **{
                    flag: label_id in selected
                    for flag, label_id in PARSER_FLAG_TO_LABEL_ID.items()}}}

    graph = {
        "source": {"class_type": "LoadImage", "inputs": {"image": normalized}},
        "matte_model": {"class_type": "LoadBackgroundRemovalModel", "inputs": {
            "bg_removal_name": "birefnet.safetensors"}},
        "matte": {"class_type": "RemoveBackground", "inputs": {
            "bg_removal_model": ["matte_model", 0], "image": ["source", 0]}},
        "parser_model": {"class_type": "FaceParsingModelLoaderNew", "inputs": {"device": "cpu"}},
        "parser_processor": {"class_type": "FaceParsingProcessorLoader(FaceParsing)", "inputs": {}},
        "parse": {"class_type": "FaceParse(FaceParsing)", "inputs": {
            "model": ["parser_model", 0], "processor": ["parser_processor", 0],
            "image": ["source", 0]}},
        "protect_regions": parser(set(range(1, 18))),
        "core_shrink": {"class_type": "GrowMask", "inputs": {
            "mask": ["protect_regions", 0], "expand": -CORE_SHRINK_PIXELS, "tapered_corners": True}},
        "core_binary": {"class_type": "ThresholdMask", "inputs": {
            "mask": ["core_shrink", 0], "value": 0.5}},
        "protect_grow": {"class_type": "GrowMask", "inputs": {
            "mask": ["protect_regions", 0], "expand": GUARD_PIXELS, "tapered_corners": False}},
        "protect_binary": {"class_type": "ThresholdMask", "inputs": {
            "mask": ["protect_grow", 0], "value": 0.5}},
        "region": parser(ids),
        "edit_exclusion": {"class_type": "InvertMask", "inputs": {"mask": ["protect_binary", 0]}},
        "edit_region": {"class_type": "MaskComposite", "inputs": {
            "destination": ["region", 0], "source": ["edit_exclusion", 0],
            "x": 0, "y": 0, "operation": "multiply"}},
        "edit_binary": {"class_type": "ThresholdMask", "inputs": {
            "mask": ["edit_region", 0], "value": 0.5}},
        "protect_image": {"class_type": "MaskToImage", "inputs": {"mask": ["protect_binary", 0]}},
        "core_image": {"class_type": "MaskToImage", "inputs": {"mask": ["core_binary", 0]}},
        "edit_image": {"class_type": "MaskToImage", "inputs": {"mask": ["edit_binary", 0]}},
        "matte_image": {"class_type": "MaskToImage", "inputs": {"mask": ["matte", 0]}},
    }
    for name, image_link in (("protect", ["protect_image", 0]), ("core", ["core_image", 0]),
                             ("edit", ["edit_image", 0]), ("labels", ["parse", 0])):
        graph[name] = {"class_type": "SaveImage", "inputs": {
            "images": image_link,
            "filename_prefix": f"ByrdHouse/source-masks-{job_id}-{name}"}}
    graph["matte_save"] = {"class_type": "SaveImage", "inputs": {
        "images": ["matte_image", 0],
        "filename_prefix": f"ByrdHouse/source-masks-{job_id}-matte"}}
    saves = {name: name for name in ("protect", "core", "edit", "labels")} | {"matte": "matte_save"}
    if illustrated:
        # The existing parser can identify the entire illustrated person,
        # including the shirt. Its tight boundary avoids BiRefNet's wide
        # off-white alpha fringe around the approved anchor's afro.
        graph.update({
            "character_regions": parser(set(range(1, 19))),
            "character_shrink": {"class_type": "GrowMask", "inputs": {
                "mask": ["character_regions", 0], "expand": -4, "tapered_corners": True}},
            "character_blur": {"class_type": "ImpactGaussianBlurMask", "inputs": {
                "mask": ["character_shrink", 0], "kernel_size": 3, "sigma": 1.0}},
            "character_image": {"class_type": "MaskToImage", "inputs": {
                "mask": ["character_blur", 0]}},
            "character_save": {"class_type": "SaveImage", "inputs": {
                "images": ["character_image", 0],
                "filename_prefix": f"ByrdHouse/source-masks-{job_id}-character"}},
        })
        saves["character"] = "character_save"
    return graph, saves


def _read_rgb(path):
    path = Path(path)
    try:
        data = path.read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise MaskError(f"Expected a single still image: {path.name}")
            fmt, size, orientation = image.format, image.size, image.getexif().get(274, 1)
            oriented = ImageOps.exif_transpose(image)
            has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
            if has_alpha and np.any(np.asarray(oriented.convert("RGBA").getchannel("A")) != 255):
                raise MaskError(f"Expected an opaque working image: {path.name}")
            rgb = np.asarray(oriented.convert("RGB"), dtype=np.uint8).copy()
    except (OSError, ValueError) as exc:
        if isinstance(exc, MaskError):
            raise
        raise MaskError(f"Cannot inspect collected image {path.name}: {exc}") from exc
    pixel_hash = hashlib.sha256()
    pixel_hash.update(f"RGB8:{rgb.shape[1]}x{rgb.shape[0]}\n".encode("ascii"))
    pixel_hash.update(rgb.tobytes())
    card = {"path": str(path.resolve()), "file_sha256": hashlib.sha256(data).hexdigest(),
            "rgb_sha256": pixel_hash.hexdigest(), "format": fmt,
            "width": rgb.shape[1], "height": rgb.shape[0],
            "file_width": size[0], "file_height": size[1],
            "exif_orientation": orientation}
    return rgb, card


def _read_mask(path, expected_shape):
    rgb, card = _read_rgb(path)
    if card["format"] != "PNG":
        raise MaskError(f"Collected mask must be a lossless PNG: {Path(path).name}")
    if rgb.shape[:2] != expected_shape:
        raise MaskError(f"Mask/source dimensions differ: {Path(path).name}")
    if not np.all(rgb == rgb[:, :, :1]):
        raise MaskError(f"Mask must have equal grayscale channels: {Path(path).name}")
    values = np.unique(rgb[:, :, 0])
    if not np.all(np.isin(values, [0, 255])):
        raise MaskError(f"Mask is not binary 0/255: {Path(path).name}")
    selected = rgb[:, :, 0] == 255
    count = int(np.count_nonzero(selected))
    if count == 0:
        raise MaskError(f"Mask is empty; review semantic coverage: {Path(path).name}")
    card.update(binary_values=[int(value) for value in values], selected_pixels=count,
                selected_fraction=count / selected.size)
    return selected, card


def inspect_matte(source_path, matte_path, *, expected_source_sha256=None):
    """Inspect a ComfyUI BiRefNet alpha without manufacturing a mask locally."""
    source, source_card = _read_rgb(source_path)
    if expected_source_sha256 is not None and source_card["file_sha256"] != expected_source_sha256:
        raise MaskError("Matte source changed from its saved SHA256")
    rgb, card = _read_rgb(matte_path)
    if card["format"] != "PNG":
        raise MaskError(f"Collected matte must be a lossless PNG: {Path(matte_path).name}")
    if rgb.shape[:2] != source.shape[:2]:
        raise MaskError("Matte/source dimensions differ")
    if not np.all(rgb == rgb[:, :, :1]):
        raise MaskError("Matte must have equal grayscale channels")
    values = rgb[:, :, 0]
    foreground = values >= 128
    opaque = values == 255
    edge = (values > 0) & (values < 255)
    if not np.any(foreground) or not np.any(values == 0):
        raise MaskError("Matte must contain both foreground and background; inspect the source photo")
    card.update(foreground_pixels=int(foreground.sum()), foreground_fraction=float(foreground.mean()),
                opaque_pixels=int(opaque.sum()), edge_pixels=int(edge.sum()),
                value_count=int(np.unique(values).size), soft_edges=bool(np.any(edge)))
    return card


def inspect_masks(source_path, protect_path, edit_path, *, labels_path=None,
                  region="background", expected_source_sha256=None):
    """Validate collected masks without modifying images or guessing coverage.

    Raises MaskError on incompatible dimensions, nonbinary values, overlapping
    edit/protection, empty masks or a changed expected source. A passing report
    requires manual mask review and says nothing about final generated pixels.
    """
    region_ids = _region_ids(region)
    source, source_card = _read_rgb(source_path)
    if expected_source_sha256 is not None and source_card["file_sha256"] != expected_source_sha256:
        raise MaskError("Mask source changed from its saved SHA256")
    shape = source.shape[:2]
    protected, protect_card = _read_mask(protect_path, shape)
    editable, edit_card = _read_mask(edit_path, shape)
    overlap = int(np.count_nonzero(protected & editable))
    if overlap:
        raise MaskError(f"Editable mask overlaps protection at {overlap} pixels")
    labels_card = None
    if labels_path is not None:
        labels, labels_card = _read_rgb(labels_path)
        if labels.shape[:2] != shape:
            raise MaskError("Labels preview/source dimensions differ")
    return {
        "schema": "byrdhouse.source-masks.inspection.v1", "region": region,
        "canvas": {"width": source_card["width"], "height": source_card["height"]},
        "source": source_card, "protect": protect_card, "edit": edit_card,
        "labels": labels_card, "source_sha256": source_card["file_sha256"],
        "source_rgb_sha256": source_card["rgb_sha256"],
        "protect_sha256": protect_card["file_sha256"], "edit_sha256": edit_card["file_sha256"],
        "guard_pixels": GUARD_PIXELS, "overlap_pixels": overlap,
        "validation": {"dimensions_match": True, "binary_masks": True,
                       "nonempty_masks": True, "zero_editable_overlap": True},
        "semantic_model": "jonathandinu/face-parsing", "parser_device": "cpu",
        "label_id_to_name": {str(key): value for key, value in LABEL_ID_TO_NAME.items()},
        "parser_flag_to_label_id": dict(PARSER_FLAG_TO_LABEL_ID),
        "protection_label_ids": list(range(1, 18)), "edit_label_ids": sorted(region_ids),
        "per_class_counts": None, "coverage_limit": COVERAGE_LIMIT,
        "coverage_verified": False, "review_required": True,
        "identity_verified": False, "exact_replica": False,
    }
