"""CPU face-mesh preparation and exact face-zone compositing for ByrdHouse.

The image generator must never guess where it is allowed to edit.  This module
turns an uploaded target into durable artifacts first: original pixels, a
MediaPipe mesh preview, a 512px face crop, hard/graded/soft masks, and a JSON
mapping back to the original canvas.  GPU generation happens only after this
CPU step.  Final compositing restores every pixel outside the soft face zone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
import cv2
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from safetensors.torch import load_file


MODEL_NAME = "mediapipe_face_fp32.safetensors"
MODEL_SHA256 = "a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a"
MODEL_SOURCE = (
    "https://huggingface.co/Comfy-Org/mediapipe/resolve/main/"
    "detection/mediapipe_face_fp32.safetensors"
)
CANVAS_SIZE = 512
SELFIE_SEGMENTER_NAME = "selfie_multiclass_256x256.tflite"
SELFIE_SEGMENTER_SHA256 = "c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0"
SELFIE_SEGMENTER_SOURCE = (
    "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite"
)
PARSENET_NAME = "parsing_parsenet.pth"
PARSENET_SHA256 = "3d558d8d0e42c20224f13cf5a29c79eba2d59913419f945545d8cf7b72920de2"
PARSENET_SOURCE = "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/parsing_parsenet.pth"


def _configure_cpu_runtime() -> dict:
    """Give CPU vision work most of the worker without starving Windows.

    The gaming worker has twenty logical threads.  OpenCV and PyTorch otherwise
    choose unrelated thread pools, which can either leave cores idle or
    oversubscribe the machine.  One shared setting keeps the detector, parser,
    contour builder and color transfer on the CPU while the RTX remains free
    for diffusion.  ``BYRD_CPU_THREADS`` remains an explicit router override.
    """
    logical = max(1, os.cpu_count() or 1)
    default_threads = max(1, logical - 2) if logical >= 8 else logical
    try:
        requested = int(os.environ.get("BYRD_CPU_THREADS", default_threads))
    except ValueError:
        requested = default_threads
    threads = max(1, min(logical, requested))
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    torch.set_num_threads(threads)
    try:
        torch.set_num_interop_threads(max(1, min(4, threads // 4)))
    except RuntimeError:
        # PyTorch only permits this before its first parallel operation.  The
        # CLI is a fresh process, but keeping this guard makes imports safe.
        pass
    cv2.setUseOptimized(True)
    cv2.setNumThreads(threads)
    return {
        "logical_threads": logical,
        "worker_threads": threads,
        "policy": "logical-minus-two; override with BYRD_CPU_THREADS",
        "opencv_optimized": bool(cv2.useOptimized()),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ordered_rings(edges: Iterable[tuple[int, int]]) -> list[list[int]]:
    adjacency: dict[int, set[int]] = {}
    for a, b in edges:
        adjacency.setdefault(int(a), set()).add(int(b))
        adjacency.setdefault(int(b), set()).add(int(a))
    visited: set[int] = set()
    rings: list[list[int]] = []
    for start in adjacency:
        if start in visited:
            continue
        ring = [start]
        visited.add(start)
        previous, current = -1, start
        while True:
            following = next((value for value in adjacency[current] if value != previous), None)
            if following is None or following == start:
                break
            ring.append(following)
            visited.add(following)
            previous, current = current, following
        rings.append(ring)
    return rings


def _model_path(root: Path) -> Path:
    return root / "Generators" / "ComfyUI" / "models" / "detection" / MODEL_NAME


def _selfie_segmenter_path(root: Path) -> Path:
    return (
        root
        / "Generators"
        / "ComfyUI"
        / "models"
        / "segmentation"
        / SELFIE_SEGMENTER_NAME
    )


def _parsenet_path(root: Path) -> Path:
    return root / "Generators" / "ComfyUI" / "models" / "facedetection" / PARSENET_NAME


@lru_cache(maxsize=2)
def _load_landmarker(model_path_text: str, variant: str):
    model_path = Path(model_path_text)
    if not model_path.is_file():
        raise RuntimeError(
            f"Missing CPU face-landmarker model: {model_path}. "
            f"Official source: {MODEL_SOURCE}"
        )
    actual_hash = sha256(model_path)
    if actual_hash != MODEL_SHA256:
        raise RuntimeError(f"Face-landmarker SHA-256 mismatch: {actual_hash}")

    comfy_root = model_path.parents[2]
    if str(comfy_root) not in sys.path:
        sys.path.insert(0, str(comfy_root))
    from comfy_extras.mediapipe.face_landmarker import FaceLandmarker

    state = load_file(str(model_path), device="cpu")
    shared = {key: value for key, value in state.items() if key.startswith(("mesh.", "blendshapes."))}
    prefix = f"detector_{variant}."
    weights = dict(shared)
    weights.update(
        {f"detector.{key[len(prefix):]}": value for key, value in state.items() if key.startswith(prefix)}
    )
    model = FaceLandmarker(
        device="cpu", dtype=torch.float32, operations=None, detector_variant=variant
    ).eval()
    missing, unexpected = model.load_state_dict(weights, strict=False)
    if missing or unexpected:
        raise RuntimeError(
            f"Face-landmarker weights do not match ({len(missing)} missing, "
            f"{len(unexpected)} unexpected)."
        )
    topology = {
        key.removeprefix("topology."): value.cpu().numpy()
        for key, value in state.items()
        if key.startswith("topology.")
    }
    return model, topology


def _detect_face(
    root: Path, image: Image.Image, min_confidence: float, face_index: int
) -> tuple[dict, dict, str, int]:
    array = np.asarray(image.convert("RGB"))
    model_path = _model_path(root)
    attempts: list[tuple[dict, dict, str]] = []
    for variant in ("short", "full"):
        model, topology = _load_landmarker(str(model_path), variant)
        with torch.inference_mode():
            faces = model.detect_batch(
                [array], num_faces=4, score_thresh=float(min_confidence)
            )[0]
        for face in faces:
            attempts.append((face, topology, variant))
        if attempts:
            break
    if not attempts:
        raise RuntimeError(
            "CPU face outline found no face. Supply --manual-box x,y,width,height; "
            "ByrdHouse will never silently edit an unknown region."
        )
    attempts.sort(
        key=lambda item: float(
            (item[0]["bbox_xyxy"][2] - item[0]["bbox_xyxy"][0])
            * (item[0]["bbox_xyxy"][3] - item[0]["bbox_xyxy"][1])
        ),
        reverse=True,
    )
    if face_index < 0 or face_index >= len(attempts):
        raise RuntimeError(
            f"Requested face index {face_index}, but CPU outline found {len(attempts)} face(s)."
        )
    face, topology, variant = attempts[face_index]
    return face, topology, variant, len(attempts)


def _ellipse_points(box: tuple[float, float, float, float], count: int = 72) -> np.ndarray:
    x, y, width, height = box
    center_x, center_y = x + width / 2, y + height / 2
    return np.asarray(
        [
            (
                center_x + math.cos(index * 2 * math.pi / count) * width / 2,
                center_y + math.sin(index * 2 * math.pi / count) * height / 2,
            )
            for index in range(count)
        ],
        dtype=np.float32,
    )


def _square_crop_box(points: np.ndarray, image_size: tuple[int, int], factor: float) -> tuple[int, int, int, int]:
    image_width, image_height = image_size
    min_x, min_y = points.min(axis=0)
    max_x, max_y = points.max(axis=0)
    center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    # A slight downward bias retains chin/jaw while the target's hair and props
    # stay outside the editable oval.
    center_y += (max_y - min_y) * 0.03
    side = int(math.ceil(max(max_x - min_x, max_y - min_y) * factor / 8) * 8)
    side = max(64, min(side, image_width, image_height))
    left = max(0, min(image_width - side, int(round(center_x - side / 2))))
    top = max(0, min(image_height - side, int(round(center_y - side / 2))))
    return left, top, left + side, top + side


def _transform_points(points: np.ndarray, crop_box: tuple[int, int, int, int]) -> np.ndarray:
    left, top, right, bottom = crop_box
    scale_x = CANVAS_SIZE / (right - left)
    scale_y = CANVAS_SIZE / (bottom - top)
    transformed = points.copy().astype(np.float32)
    transformed[:, 0] = (transformed[:, 0] - left) * scale_x
    transformed[:, 1] = (transformed[:, 1] - top) * scale_y
    return transformed


def _scale_outline(points: np.ndarray, horizontal: float, vertical: float) -> np.ndarray:
    """Expand a landmark outline around its visual center.

    MediaPipe's face oval follows the inner facial contour.  That is useful for
    landmarks, but too conservative for a replacement mask: temples and the
    outside of the jaw can otherwise survive unchanged.  The expansion remains
    tied to the detected face instead of becoming a generic rectangle.
    """
    center = (points.min(axis=0) + points.max(axis=0)) / 2.0
    expanded = points.astype(np.float32).copy()
    expanded[:, 0] = center[0] + (expanded[:, 0] - center[0]) * horizontal
    expanded[:, 1] = center[1] + (expanded[:, 1] - center[1]) * vertical
    return expanded


def _ear_boxes(
    outline: np.ndarray, mesh_points: np.ndarray | None
) -> list[tuple[float, float, float, float]]:
    """Return ear-side lobes that make the zone cover the full visible face.

    The 478-point face mesh intentionally ends at the cheek contour and does
    not trace ears.  Nose displacement provides a cheap CPU yaw estimate: on a
    turned face, the visible ear is opposite the nose direction.  Frontal faces
    receive a small lobe on both sides.  These lobes overlap the expanded oval,
    so the result is one contiguous edit zone.
    """
    min_x, min_y = outline.min(axis=0)
    max_x, max_y = outline.max(axis=0)
    width = max(1.0, float(max_x - min_x))
    height = max(1.0, float(max_y - min_y))
    center_x = float((min_x + max_x) / 2.0)
    center_y = float(min_y + height * 0.46)
    if mesh_points is None or len(mesh_points) <= 1:
        sides = (-1, 1)
    else:
        nose_offset = float(mesh_points[1, 0] - center_x) / width
        sides = (-1, 1) if abs(nose_offset) < 0.055 else ((-1,) if nose_offset > 0 else (1,))

    boxes: list[tuple[float, float, float, float]] = []
    ear_width = width * 0.25
    ear_height = height * 0.48
    for side in sides:
        ear_center_x = (min_x - width * 0.015) if side < 0 else (max_x + width * 0.015)
        boxes.append(
            (
                float(ear_center_x - ear_width / 2.0),
                float(center_y - ear_height / 2.0),
                float(ear_center_x + ear_width / 2.0),
                float(center_y + ear_height / 2.0),
            )
        )
    return boxes


def _verify_model(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing {label}: {path}")
    actual = sha256(path)
    if actual != expected_sha256:
        raise RuntimeError(f"{label} SHA-256 mismatch: {actual}")


def _run_selfie_multiclass(root: Path, crop: Image.Image) -> tuple[np.ndarray, list[np.ndarray], dict]:
    """Run Google's lightweight six-class human segmenter on CPU."""
    model_path = _selfie_segmenter_path(root)
    _verify_model(model_path, SELFIE_SEGMENTER_SHA256, "MediaPipe multiclass segmenter")
    import mediapipe as mp

    options = mp.tasks.vision.ImageSegmenterOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        output_category_mask=True,
        output_confidence_masks=True,
    )
    image_array = np.ascontiguousarray(np.asarray(crop.convert("RGB"), dtype=np.uint8))
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_array)
    with mp.tasks.vision.ImageSegmenter.create_from_options(options) as segmenter:
        result = segmenter.segment(mp_image)
        labels = list(segmenter.labels)
    category = np.squeeze(
        np.asarray(result.category_mask.numpy_view(), dtype=np.uint8)
    ).copy()
    confidence = [
        np.squeeze(np.asarray(mask.numpy_view(), dtype=np.float32)).copy()
        for mask in result.confidence_masks
    ]
    return category, confidence, {
        "name": "mediapipe-selfie-multiclass-256",
        "path": str(model_path),
        "sha256": SELFIE_SEGMENTER_SHA256,
        "source": SELFIE_SEGMENTER_SOURCE,
        "license": "Apache-2.0",
        "labels": labels,
        "deployment_scope": "local-and-deployable",
    }


@lru_cache(maxsize=1)
def _load_parsenet_model(model_path_text: str, reactor_root_text: str):
    model_path = Path(model_path_text)
    reactor_root = Path(reactor_root_text)
    if str(reactor_root) not in sys.path:
        sys.path.insert(0, str(reactor_root))
    from r_facelib.parsing.parsenet import ParseNet

    model = ParseNet(in_size=512, out_size=512, parsing_ch=19).cpu().eval()
    state = torch.load(str(model_path), map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    return model


def _run_parsenet(root: Path, crop: Image.Image) -> tuple[np.ndarray, dict]:
    """Run the already-installed 19-class parser as the local anime fallback."""
    model_path = _parsenet_path(root)
    _verify_model(model_path, PARSENET_SHA256, "ParseNet face parser")
    reactor_root = root / "Generators" / "ComfyUI" / "custom_nodes" / "ComfyUI-ReActor"
    model = _load_parsenet_model(str(model_path), str(reactor_root))
    array = np.asarray(crop.convert("RGB"), dtype=np.float32) / 127.5 - 1.0
    tensor = torch.from_numpy(array.transpose(2, 0, 1)).unsqueeze(0)
    with torch.inference_mode():
        labels = model(tensor)[0].argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
    return labels, {
        "name": "parsenet-19-local-anime-fallback",
        "path": str(model_path),
        "sha256": PARSENET_SHA256,
        "source": PARSENET_SOURCE,
        "license": "deployment-license-review-required",
        "labels": [
            "background", "skin", "nose", "eyeglasses", "left-eye",
            "right-eye", "left-brow", "right-brow", "left-ear", "right-ear",
            "mouth", "upper-lip", "lower-lip", "hair", "hat", "earring",
            "necklace", "neck", "clothing",
        ],
        "deployment_scope": "private-local-evaluation-only",
    }


def _remove_source_accessories(
    root: Path,
    source_image: Image.Image,
    source_mesh: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Inpaint source glasses/jewelry before their pixels enter the face grid."""
    crop_box = _square_crop_box(source_mesh, source_image.size, 1.55)
    source_crop = source_image.crop(crop_box).resize(
        (CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.LANCZOS
    )
    labels, parser = _run_parsenet(root, source_crop)
    # Glasses and jewelry belong to the source photograph, not facial identity.
    accessory = np.isin(labels, (3, 15, 16)).astype(np.uint8) * 255
    source_crop_lab = np.asarray(source_crop.convert("LAB"), dtype=np.uint8)
    specular = np.isin(labels, (1, 2)) & (source_crop_lab[..., 0] > 205)
    specular_pixels = int(np.count_nonzero(specular))
    accessory = np.maximum(accessory, np.uint8(specular) * 255)
    accessory = cv2.dilate(
        accessory,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        iterations=1,
    )
    left, top, right, bottom = crop_box
    native = cv2.resize(
        accessory,
        (right - left, bottom - top),
        interpolation=cv2.INTER_NEAREST,
    )
    full_mask = np.zeros((source_image.height, source_image.width), dtype=np.uint8)
    full_mask[top:bottom, left:right] = native
    source_array = np.asarray(source_image, dtype=np.uint8)
    pixels = int(np.count_nonzero(full_mask))
    if pixels:
        cleaned = cv2.inpaint(source_array, full_mask, 5.0, cv2.INPAINT_TELEA)
    else:
        cleaned = source_array.copy()
    return cleaned, {
        "applied": bool(pixels),
        "pixels": pixels,
        "classes": ["eyeglasses", "earring", "necklace", "skin-specular-highlight"],
        "specular_pixels_512": specular_pixels,
        "parser": parser["name"],
    }


def _head_neck_roi(seed_mask: np.ndarray) -> np.ndarray:
    ys, xs = np.where(seed_mask)
    if len(xs) == 0:
        return np.zeros(seed_mask.shape, dtype=bool)
    top, bottom = int(ys.min()), int(ys.max())
    height = max(1, bottom - top)
    roi = np.zeros(seed_mask.shape, dtype=bool)
    roi[
        max(0, top - int(0.65 * height)): min(seed_mask.shape[0], bottom + int(0.72 * height) + 1),
        :,
    ] = True
    return roi


def _components_touching_seed(mask: np.ndarray, seed: np.ndarray) -> np.ndarray:
    count, components = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    if count <= 1:
        return mask
    keep = np.zeros(mask.shape, dtype=bool)
    for label in range(1, count):
        component = components == label
        if int(np.count_nonzero(component & seed)) >= 12:
            keep |= component
    return keep


def _closed_head_envelope(
    seed: np.ndarray,
    exposed_skin: np.ndarray,
    neck: np.ndarray,
    roi: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Trace one closed outer head contour before subtracting hair.

    Face landmarks describe an inner facial oval, not the full head surface.
    We therefore join the landmark seed to every connected exposed-skin pixel,
    trace their outside points, close that trace with an OpenCV hull, and fill
    it back to its starting point.  The neck is attached afterward through a
    narrow jaw gate so shoulders cannot inflate the head hull.  Hair is *not*
    considered here; it is independently outlined and removed in the next
    stage.
    """
    ys, xs = np.where(seed)
    if len(xs) < 16:
        return seed.copy(), {
            "method": "seed-fallback",
            "closed": True,
            "head_pixels": int(np.count_nonzero(seed)),
            "neck_pixels": 0,
        }

    seed_top, seed_bottom = int(ys.min()), int(ys.max())
    seed_left, seed_right = int(xs.min()), int(xs.max())
    seed_height = max(1, seed_bottom - seed_top)
    seed_width = max(1, seed_right - seed_left)
    rows, cols = np.indices(seed.shape)

    # Only head/ear evidence participates in the closed hull.  Neck evidence
    # is joined later so a shirt collar or shoulder never becomes head skin.
    head_gate = (
        (rows <= min(seed.shape[0] - 1, seed_bottom + int(seed_height * 0.16)))
        & (cols >= max(0, seed_left - int(seed_width * 0.34)))
        & (cols <= min(seed.shape[1] - 1, seed_right + int(seed_width * 0.34)))
        & roi
    )
    support = (seed | exposed_skin) & head_gate
    support = cv2.morphologyEx(
        support.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    ) > 0
    support = _components_touching_seed(
        support,
        cv2.dilate(seed.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0,
    )

    support_y, support_x = np.where(support)
    closed_head = support.copy()
    hull_vertices = 0
    if len(support_x) >= 16:
        points = np.column_stack((support_x, support_y)).astype(np.int32)
        hull = cv2.convexHull(points)
        hull_vertices = int(len(hull))
        closed_head = np.zeros(seed.shape, dtype=np.uint8)
        cv2.fillConvexPoly(closed_head, hull, 1)
        closed_head = (closed_head > 0) & head_gate

    # Reattach only skin/neck evidence physically connected below the jaw.  A
    # mild horizontal allowance retains visible neck on turned heads.
    neck_gate = (
        (rows >= seed_top + int(seed_height * 0.48))
        & (rows <= min(seed.shape[0] - 1, seed_bottom + int(seed_height * 0.62)))
        & (cols >= max(0, seed_left - int(seed_width * 0.24)))
        & (cols <= min(seed.shape[1] - 1, seed_right + int(seed_width * 0.30)))
        & roi
    )
    neck_support = (neck | exposed_skin) & neck_gate
    neck_support = _components_touching_seed(
        cv2.morphologyEx(
            neck_support.astype(np.uint8),
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        ) > 0,
        cv2.dilate(closed_head.astype(np.uint8), np.ones((11, 11), np.uint8)) > 0,
    )
    envelope = closed_head | neck_support
    envelope = cv2.morphologyEx(
        envelope.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
    ) > 0
    return envelope, {
        "method": "opencv-connected-exposed-skin-closed-convex-head-contour",
        "closed": True,
        "hull_vertices": hull_vertices,
        "support_pixels": int(np.count_nonzero(support)),
        "head_pixels": int(np.count_nonzero(closed_head)),
        "neck_pixels": int(np.count_nonzero(neck_support)),
        "envelope_pixels": int(np.count_nonzero(envelope)),
    }


def _semantic_head_zone(
    root: Path, crop: Image.Image, geometric_face: Image.Image
) -> tuple[Image.Image, Image.Image, Image.Image, Image.Image, Image.Image, np.ndarray, dict]:
    """Build `neck + connected head - hair/headwear` on CPU.

    Real images use the small Apache-2.0 MediaPipe model.  Anime frequently
    falls outside that model's domain, so the already-installed ParseNet is a
    private local fallback.  The facial mesh fills eyes, mouth and ink-line
    holes, while semantic hair/headwear always wins as a protection mask.
    """
    seed = np.asarray(geometric_face.convert("L")) > 127
    roi = _head_neck_roi(seed)
    parser: dict
    mode: str
    labels_preview: np.ndarray

    category, confidence, media_info = _run_selfie_multiclass(root, crop)
    face_confidence = float(confidence[3][seed].mean()) if seed.any() else 0.0
    face_fraction = float(np.mean(category[seed] == 3)) if seed.any() else 0.0
    if face_confidence >= 0.12 and face_fraction >= 0.025:
        mode = "mediapipe-selfie-multiclass"
        parser = media_info
        semantic_keep = np.isin(category, (2, 3)) & roi
        neck = (category == 2) & roi
        hair_headwear = (category == 1) & roi
        other_exclusion = np.zeros(seed.shape, dtype=bool)
        exclusion = hair_headwear.copy()
        labels_preview = category
        parser_score = face_confidence
    else:
        category, parse_info = _run_parsenet(root, crop)
        mode = "parsenet-anime-fallback"
        parser = parse_info
        editable_face_ids = np.asarray((1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12), dtype=np.uint8)
        facial_classes = np.isin(category, editable_face_ids)
        parser_score = float(facial_classes[seed].mean()) if seed.any() else 0.0
        if parser_score < 0.08:
            raise RuntimeError(
                "CPU semantic head parser could not identify a reliable face/neck zone; "
                "GPU editing was stopped for manual review."
            )
        semantic_keep = np.isin(
            category, np.asarray((*editable_face_ids.tolist(), 17), dtype=np.uint8)
        ) & roi
        neck = (category == 17) & roi
        # Preserve glasses, hair, hats, earrings, necklaces and clothing.  They
        # may sit inside the geometric face oval but are not facial skin.
        hair_headwear = np.isin(category, (13, 14)) & roi
        other_exclusion = np.isin(category, (3, 15, 16, 18)) & roi
        exclusion = hair_headwear | other_exclusion
        labels_preview = category

    # Recover skin-colored pixels that an anime parser mislabeled specifically
    # as hair. The recovery is color-connected to confirmed face skin and never
    # overrides hats, clothing, glasses or other raw exclusions.
    recoverable_labels = (
        (0, 13) if mode == "parsenet-anime-fallback" else (0, 1)
    )
    recoverable_hair = np.isin(category, recoverable_labels) & roi
    # Bound ambiguous background/hair recovery to a head-shaped corridor.
    # Hat pixels are never recoverable: headwear is a locked target layer.
    seed_y, seed_x = np.where(seed)
    if len(seed_x):
        seed_top, seed_bottom = int(seed_y.min()), int(seed_y.max())
        seed_left, seed_right = int(seed_x.min()), int(seed_x.max())
        seed_height = max(1, seed_bottom - seed_top)
        seed_width = max(1, seed_right - seed_left)
        rows, cols = np.indices(seed.shape)
        recovery_corridor = (
            (rows >= max(0, seed_top - int(seed_height * 0.62)))
            & (rows <= min(seed.shape[0] - 1, seed_bottom + int(seed_height * 0.32)))
            & (cols >= max(0, seed_left - int(seed_width * 0.28)))
            & (cols <= min(seed.shape[1] - 1, seed_right + int(seed_width * 0.28)))
        )
        recoverable_hair &= recovery_corridor
    confirmed_samples = semantic_keep & seed & ~exclusion
    recovered_skin = np.zeros(seed.shape, dtype=bool)
    if int(confirmed_samples.sum()) >= 96:
        lab = np.asarray(crop.convert("LAB"), dtype=np.float32)
        values = lab[confirmed_samples]
        order = np.argsort(values[:, 0])
        values = values[order]
        centers = []
        for start_fraction, end_fraction in ((0.05, 0.35), (0.35, 0.65), (0.65, 0.95)):
            start = int(len(values) * start_fraction)
            end = max(start + 1, int(len(values) * end_fraction))
            centers.append(np.median(values[start:end], axis=0))
        color_like_skin = np.zeros(seed.shape, dtype=bool)
        for center in centers:
            light_delta = np.abs(lab[..., 0] - center[0])
            chroma_delta = np.sqrt(
                (lab[..., 1] - center[1]) ** 2
                + (lab[..., 2] - center[2]) ** 2
            )
            color_like_skin |= (light_delta < 65.0) & (chroma_delta < 22.0)
        # Dark anime ink is a hard region-growing barrier.  This lets flat skin
        # continue across parser mistakes without jumping across a hair/hat
        # outline into a similarly colored straw hat or background.
        crop_gray = cv2.cvtColor(np.asarray(crop, dtype=np.uint8), cv2.COLOR_RGB2GRAY)
        ink_barrier = cv2.Canny(crop_gray, 35, 105) > 0
        ink_barrier = cv2.dilate(
            ink_barrier.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1
        ) > 0
        bridge = color_like_skin & (recoverable_hair | semantic_keep) & roi
        bridge &= ~ink_barrier
        bridge |= confirmed_samples
        attached = _components_touching_seed(
            bridge,
            confirmed_samples,
        )
        recovered_skin = attached & recoverable_hair
        exclusion &= ~recovered_skin
        hair_headwear &= ~recovered_skin
        semantic_keep |= recovered_skin

    # Stage 1: close the complete head/ear contour from exposed skin.  This is
    # intentionally computed before hair is removed so the outer head boundary
    # remains a durable, inspectable artifact.
    head_envelope, head_contour = _closed_head_envelope(
        seed, semantic_keep, neck, roi
    )

    # Stage 2: outline hair/headwear independently *inside or touching* the
    # closed head envelope.  A small outside band retains antialiased hairline
    # pixels without turning the whole semantic background into an exclusion.
    envelope_band = cv2.dilate(
        head_envelope.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        iterations=1,
    ) > 0
    hair_headwear &= envelope_band
    hair_outline = cv2.morphologyEx(
        hair_headwear.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    ) > 0
    exclusion = hair_outline | other_exclusion

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    raw_exclusion = exclusion.copy()
    exclusion = cv2.dilate(exclusion.astype(np.uint8), kernel, iterations=1) > 0
    # Dilation protects the hairline, but it must not erase pixels positively
    # classified as editable skin/features. Raw hair/hat/clothing always wins;
    # only the *dilated spill* is overridden. This matters on sharp anime
    # hairlines such as Vegeta's oversized forehead.
    exclusion &= ~semantic_keep
    exclusion |= raw_exclusion
    # Stage 3: the editable surface is literally closed head/neck minus the
    # independently traced hair/headwear and other protected accessories.
    combined = head_envelope & roi
    combined = cv2.morphologyEx(combined.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    combined &= ~exclusion
    combined = _components_touching_seed(combined, seed & ~exclusion)

    # Stylized parsers sometimes call a visible neck patch "background" even
    # when it is the same flat skin color and physically touches the jaw/ear.
    # Continue confirmed skin downward/sideward by color connectivity, bounded
    # by the head ROI and the semantic hair/headwear/clothing exclusion.
    ys, xs = np.where(seed & ~raw_exclusion)
    color_neck = np.zeros(seed.shape, dtype=bool)
    if len(xs) >= 64:
        seed_top, seed_bottom = int(ys.min()), int(ys.max())
        seed_left, seed_right = int(xs.min()), int(xs.max())
        seed_height = max(1, seed_bottom - seed_top)
        seed_width = max(1, seed_right - seed_left)
        lab = np.asarray(crop.convert("LAB"), dtype=np.float32)
        skin_samples = semantic_keep & seed & ~raw_exclusion
        if int(skin_samples.sum()) < 64:
            skin_samples = seed & ~raw_exclusion
        sample_l = lab[..., 0][skin_samples]
        bright_samples = skin_samples & (
            lab[..., 0] >= float(np.percentile(sample_l, 38))
        )
        skin_median = np.median(lab[bright_samples], axis=0)
        light_delta = np.abs(lab[..., 0] - skin_median[0])
        chroma_delta = np.sqrt(
            (lab[..., 1] - skin_median[1]) ** 2
            + (lab[..., 2] - skin_median[2]) ** 2
        )
        rows, cols = np.indices(seed.shape)
        continuation_gate = (
            (rows >= seed_top + int(seed_height * 0.32))
            & (rows <= min(seed.shape[0] - 1, seed_bottom + int(seed_height * 0.58)))
            & (cols >= max(0, seed_left - int(seed_width * 0.22)))
            & (cols <= min(seed.shape[1] - 1, seed_right + int(seed_width * 0.30)))
        )
        similar_skin = (
            (light_delta < 48.0)
            & (chroma_delta < 28.0)
            & continuation_gate
            & roi
            & ~exclusion
        )
        similar_skin = cv2.morphologyEx(
            similar_skin.astype(np.uint8),
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        ) > 0
        color_neck = _components_touching_seed(
            similar_skin,
            cv2.dilate(combined.astype(np.uint8), kernel, iterations=1) > 0,
        )
        combined |= color_neck
        combined = cv2.morphologyEx(
            combined.astype(np.uint8), cv2.MORPH_CLOSE, kernel
        ) > 0
        combined &= ~exclusion
        combined = _components_touching_seed(combined, seed & ~exclusion)
        neck |= color_neck & ~seed
    if int(combined.sum()) < 256:
        raise RuntimeError("CPU semantic head/neck zone became empty after hair exclusion.")

    final_mask = Image.fromarray(np.uint8(combined) * 255, mode="L")
    hair_mask = Image.fromarray(np.uint8(exclusion) * 255, mode="L")
    neck_mask = Image.fromarray(np.uint8(neck & combined) * 255, mode="L")
    parser.update(
        {
            "mode": mode,
            "score": round(parser_score, 6),
            "neck_visible": bool(np.any(neck & combined)),
            "recovered_skin_pixels": int(np.count_nonzero(recovered_skin)),
            "recovered_skin_by_label": {
                str(label): int(np.count_nonzero(recovered_skin & (labels_preview == label)))
                for label in recoverable_labels
            },
            "head_contour": head_contour,
            "hair_outline_pixels": int(np.count_nonzero(hair_outline)),
            "ordered_stages": [
                "closed-head-envelope-from-exposed-skin",
                "independent-hair-headwear-outline",
                "head-minus-hair-edit-zone",
            ],
            "rule": "close exposed-skin head contour; outline hair separately; subtract hair; attach connected neck",
        }
    )
    head_mask = Image.fromarray(np.uint8(head_envelope) * 255, mode="L")
    hair_outline_mask = Image.fromarray(np.uint8(hair_outline) * 255, mode="L")
    return (
        final_mask,
        head_mask,
        hair_outline_mask,
        hair_mask,
        neck_mask,
        labels_preview,
        parser,
    )


def _semantic_preview(labels: np.ndarray, mode: str) -> Image.Image:
    if mode == "mediapipe-selfie-multiclass":
        palette = np.asarray(
            [
                (0, 0, 0), (40, 220, 80), (45, 120, 255),
                (255, 95, 90), (145, 90, 255), (255, 210, 55),
            ],
            dtype=np.uint8,
        )
    else:
        palette = np.asarray(
            [
                (0, 0, 0), (255, 95, 90), (255, 145, 90), (255, 220, 70),
                (50, 190, 255), (50, 190, 255), (195, 95, 65), (195, 95, 65),
                (255, 110, 80), (255, 110, 80), (255, 100, 140), (255, 80, 120),
                (255, 80, 120), (40, 220, 80), (255, 210, 55), (230, 210, 50),
                (225, 190, 45), (45, 120, 255), (145, 90, 255),
            ],
            dtype=np.uint8,
        )
    clipped = np.clip(labels, 0, len(palette) - 1)
    return Image.fromarray(palette[clipped], mode="RGB")


def _mesh_triangles(topology: dict[str, np.ndarray]) -> list[tuple[int, int, int]]:
    """Derive stable triangle indices from MediaPipe's tesselation edges."""
    adjacency: dict[int, set[int]] = {}
    for a_value, b_value in topology.get("tesselation", []):
        a, b = int(a_value), int(b_value)
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    triangles: set[tuple[int, int, int]] = set()
    for a, neighbors in adjacency.items():
        for b in neighbors:
            for c in neighbors.intersection(adjacency.get(b, set())):
                if a != b and b != c and a != c:
                    triangles.add(tuple(sorted((a, b, c))))
    return sorted(triangles)


def _warp_triangle(
    source: np.ndarray,
    destination: np.ndarray,
    coverage: np.ndarray,
    source_triangle: np.ndarray,
    target_triangle: np.ndarray,
) -> None:
    source_rect = cv2.boundingRect(source_triangle.astype(np.float32))
    target_rect = cv2.boundingRect(target_triangle.astype(np.float32))
    sx, sy, sw, sh = source_rect
    tx, ty, tw, th = target_rect
    if min(sw, sh, tw, th) < 1:
        return
    if sx < 0 or sy < 0 or sx + sw > source.shape[1] or sy + sh > source.shape[0]:
        return
    if tx < 0 or ty < 0 or tx + tw > destination.shape[1] or ty + th > destination.shape[0]:
        return

    source_local = source_triangle - np.asarray((sx, sy), dtype=np.float32)
    target_local = target_triangle - np.asarray((tx, ty), dtype=np.float32)
    patch = source[sy:sy + sh, sx:sx + sw]
    transform = cv2.getAffineTransform(source_local.astype(np.float32), target_local.astype(np.float32))
    warped = cv2.warpAffine(
        patch,
        transform,
        (tw, th),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    triangle_mask = np.zeros((th, tw), dtype=np.float32)
    cv2.fillConvexPoly(
        triangle_mask,
        np.int32(np.round(target_local)),
        1.0,
        lineType=cv2.LINE_AA,
    )
    region = destination[ty:ty + th, tx:tx + tw]
    region_coverage = coverage[ty:ty + th, tx:tx + tw]
    alpha = triangle_mask[..., None]
    region[:] = region * (1.0 - alpha) + warped.astype(np.float32) * alpha
    region_coverage[:] = np.maximum(region_coverage, triangle_mask)


def _feature_mask(
    points: np.ndarray,
    edges: np.ndarray | None,
    *,
    padding: int = 0,
) -> Image.Image:
    """Rasterize closed MediaPipe feature rings into a CPU mask."""
    mask = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
    if edges is None or len(edges) == 0:
        return mask
    draw = ImageDraw.Draw(mask)
    for ring in _ordered_rings(map(tuple, edges)):
        if len(ring) < 3 or max(ring) >= len(points):
            continue
        draw.polygon(
            [(float(points[index, 0]), float(points[index, 1])) for index in ring],
            fill=255,
        )
    if padding > 0:
        size = max(3, padding * 2 + 1)
        if size % 2 == 0:
            size += 1
        mask = mask.filter(ImageFilter.MaxFilter(size))
    return mask


def _target_material_feature_lock(
    crop: Image.Image,
    mesh_points: np.ndarray,
    topology: dict[str, np.ndarray],
    hard_mask: Image.Image,
) -> tuple[Image.Image, dict[str, Image.Image], dict]:
    """Lock iconic target features while identity occupies exposed skin.

    Large anime eyes and mouths are character material, not identity texture.
    Hair/headwear are already outside ``hard_mask``; this companion mask keeps
    target eyes, the complete mouth/teeth shape, scars, brows, nose ink and ear
    linework exact inside the editable skin surface.
    """
    hard = np.asarray(hard_mask.convert("L")) > 127
    left_eye = _feature_mask(mesh_points, topology.get("left_eye"), padding=3)
    right_eye = _feature_mask(mesh_points, topology.get("right_eye"), padding=3)
    eyes = np.maximum(np.asarray(left_eye), np.asarray(right_eye)) > 127
    mouth = np.asarray(
        _feature_mask(mesh_points, topology.get("lips"), padding=4)
    ) > 127

    rgb = np.asarray(crop.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 38, 112) > 0
    dark_edges = edges & (gray < 112)
    ink = cv2.dilate(
        dark_edges.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    ) > 0
    ink &= hard

    eyes &= hard
    mouth &= hard
    combined = (eyes | mouth | ink) & hard
    components = {
        "eyes": Image.fromarray(np.uint8(eyes) * 255, mode="L"),
        "mouth_teeth": Image.fromarray(np.uint8(mouth) * 255, mode="L"),
        "face_ink": Image.fromarray(np.uint8(ink) * 255, mode="L"),
    }
    return (
        Image.fromarray(np.uint8(combined) * 255, mode="L"),
        components,
        {
            "mode": "target-eyes-mouth-teeth-and-dark-linework",
            "eyes_pixels": int(np.count_nonzero(eyes)),
            "mouth_teeth_pixels": int(np.count_nonzero(mouth)),
            "face_ink_pixels": int(np.count_nonzero(ink)),
            "combined_pixels": int(np.count_nonzero(combined)),
            "hair_headwear": "locked by independent subtraction outside edit zone",
        },
    )


def _warp_ring_fan(
    source: np.ndarray,
    destination: np.ndarray,
    coverage: np.ndarray,
    source_points: np.ndarray,
    target_points: np.ndarray,
    edges: np.ndarray | None,
) -> int:
    """Fill feature interiors omitted by MediaPipe's surface tesselation.

    The canonical tesselation deliberately leaves the mouth and eye openings
    empty.  For identity seeding we fill only the lips: each closed ring is
    triangulated around its own centroid, so the source mouth follows the
    target expression instead of exposing the pale target mouth underneath.
    """
    if edges is None or len(edges) == 0:
        return 0
    count = 0
    for ring in _ordered_rings(map(tuple, edges)):
        if len(ring) < 3 or max(ring) >= len(source_points) or max(ring) >= len(target_points):
            continue
        source_ring = source_points[np.asarray(ring, dtype=np.int32)]
        target_ring = target_points[np.asarray(ring, dtype=np.int32)]
        source_center = source_ring.mean(axis=0)
        target_center = target_ring.mean(axis=0)
        for index in range(len(ring)):
            following = (index + 1) % len(ring)
            _warp_triangle(
                source,
                destination,
                coverage,
                np.asarray(
                    (source_center, source_ring[index], source_ring[following]),
                    dtype=np.float32,
                ),
                np.asarray(
                    (target_center, target_ring[index], target_ring[following]),
                    dtype=np.float32,
                ),
            )
            count += 1
    return count


def _warp_feature_affine(
    source: np.ndarray,
    destination: np.ndarray,
    coverage: np.ndarray,
    source_points: np.ndarray,
    target_points: np.ndarray,
    edges: np.ndarray | None,
    allowed: np.ndarray,
) -> dict:
    """Warp a visible eye as one coherent patch instead of leaving a hole."""
    if edges is None or len(edges) == 0:
        return {"applied": False, "reason": "missing-topology"}
    rings = [ring for ring in _ordered_rings(map(tuple, edges)) if len(ring) >= 3]
    if not rings:
        return {"applied": False, "reason": "missing-ring"}
    ring = max(rings, key=len)
    if max(ring) >= len(source_points) or max(ring) >= len(target_points):
        return {"applied": False, "reason": "landmark-range"}
    source_ring = source_points[np.asarray(ring, dtype=np.int32)].astype(np.float32)
    target_ring = target_points[np.asarray(ring, dtype=np.int32)].astype(np.float32)
    feature = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.uint8)
    cv2.fillPoly(feature, [np.int32(np.round(target_ring))], 255, lineType=cv2.LINE_AA)
    feature = cv2.dilate(
        feature,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        iterations=1,
    ).astype(np.float32) / 255.0
    feature_pixels = max(1, int(np.count_nonzero(feature > 0.25)))
    visible_fraction = float(np.count_nonzero((feature > 0.25) & (allowed > 0.5)) / feature_pixels)
    if visible_fraction < 0.45:
        return {
            "applied": False,
            "reason": "feature-covered-by-hair-or-headwear",
            "visible_fraction": round(visible_fraction, 6),
        }

    transform, _ = cv2.estimateAffine2D(
        source_ring,
        target_ring,
        method=cv2.LMEDS,
        refineIters=10,
    )
    if transform is None:
        return {"applied": False, "reason": "affine-fit-failed"}
    linear = transform[:, :2]
    determinant = float(np.linalg.det(linear))
    predicted = cv2.transform(source_ring[None, ...], transform)[0]
    residual = np.linalg.norm(predicted - target_ring, axis=1)
    feature_width = max(1.0, float(np.ptp(target_ring[:, 0])))
    residual_ratio = float(np.median(residual) / feature_width)
    if determinant <= 0.0 or determinant < 0.15 or determinant > 6.0 or residual_ratio > 0.15:
        return {
            "applied": False,
            "reason": "unsafe-affine-fit",
            "determinant": round(determinant, 6),
            "residual_ratio": round(residual_ratio, 6),
        }

    warped = cv2.warpAffine(
        source,
        transform,
        (CANVAS_SIZE, CANVAS_SIZE),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    ).astype(np.float32)
    alpha = np.clip(feature * allowed, 0.0, 1.0)
    destination[:] = destination * (1.0 - alpha[..., None]) + warped * alpha[..., None]
    coverage[:] = np.maximum(coverage, alpha)
    return {
        "applied": True,
        "visible_fraction": round(visible_fraction, 6),
        "determinant": round(determinant, 6),
        "residual_ratio": round(residual_ratio, 6),
    }


def _tone_match_uncovered_region(
    seeded: np.ndarray,
    target: np.ndarray,
    coverage: np.ndarray,
    identity_alpha: np.ndarray,
    allowed: np.ndarray,
    region_mask: Image.Image,
) -> tuple[np.ndarray, dict]:
    """Carry identity skin tone into semantic skin not reached by the mesh.

    FaceMesh has no ear landmarks.  The semantic parser does, so this keeps the
    target ear's native ink/detail while matching its flat fill to the warped
    cheek.  LAB median shifts preserve local shading and are cheap on CPU.
    """
    region = np.asarray(region_mask.convert("L"), dtype=np.float32) / 255.0
    tone_weight = np.clip(region * (1.0 - identity_alpha) * allowed, 0.0, 1.0)
    uncovered = tone_weight > 0.15
    face = (allowed > 0.5) & (coverage > 0.70)
    if int(uncovered.sum()) < 16 or int(face.sum()) < 64:
        return seeded, {"applied": False, "pixels": int(uncovered.sum())}

    seed_u8 = np.uint8(np.clip(seeded, 0, 255))
    target_u8 = np.uint8(np.clip(target, 0, 255))
    seed_lab = cv2.cvtColor(seed_u8, cv2.COLOR_RGB2LAB).astype(np.float32)
    target_lab = cv2.cvtColor(target_u8, cv2.COLOR_RGB2LAB).astype(np.float32)
    face_l = seed_lab[..., 0][face]
    ear_l = target_lab[..., 0][uncovered]
    face_fill = face & (seed_lab[..., 0] >= float(np.percentile(face_l, 42)))
    ear_fill = uncovered & (target_lab[..., 0] >= float(np.percentile(ear_l, 32)))
    if int(face_fill.sum()) < 32 or int(ear_fill.sum()) < 8:
        return seeded, {"applied": False, "pixels": int(uncovered.sum())}

    face_median = np.median(seed_lab[face_fill], axis=0)
    ear_median = np.median(target_lab[ear_fill], axis=0)
    delta = np.clip(face_median - ear_median, (-115.0, -58.0, -58.0), (88.0, 58.0, 58.0))
    adjusted_lab = target_lab.copy()
    adjusted_lab[..., 0] += delta[0] * 0.92
    adjusted_lab[..., 1] += delta[1]
    adjusted_lab[..., 2] += delta[2]
    adjusted_rgb = cv2.cvtColor(
        np.uint8(np.clip(adjusted_lab, 0, 255)), cv2.COLOR_LAB2RGB
    ).astype(np.float32)

    alpha = cv2.GaussianBlur(np.float32(tone_weight), (0, 0), 1.15)
    # Keep the darkest target ink strokes crisp while recoloring the ear fill.
    dark_cutoff = float(np.percentile(ear_l, 23))
    ink_weight = np.where(target_lab[..., 0] <= dark_cutoff, 0.32, 1.0)
    alpha = np.clip(alpha * ink_weight * allowed, 0.0, 1.0)[..., None]
    result = seeded * (1.0 - alpha) + adjusted_rgb * alpha
    return result, {
        "applied": True,
        "pixels": int(uncovered.sum()),
        "mean_weight": round(float(tone_weight[uncovered].mean()), 6),
        "lab_delta": [round(float(value), 3) for value in delta],
    }


def _build_identity_mesh_seed(
    root: Path,
    crop: Image.Image,
    crop_box: tuple[int, int, int, int],
    target_mesh: np.ndarray,
    topology: dict[str, np.ndarray],
    hard_mask: Image.Image,
    preserve_feature_mask: Image.Image,
    uncovered_skin_mask: Image.Image,
    identity_reference: Path,
    mesh_identity_strength_override: float | None = None,
    eye_source_mode: str = "identity",
) -> tuple[Image.Image, Image.Image, Image.Image, dict]:
    """Warp a Carey anime reference through the same 478-point target grid."""
    identity_reference = identity_reference.resolve()
    if not identity_reference.is_file():
        raise RuntimeError(f"Identity mesh reference does not exist: {identity_reference}")
    with Image.open(identity_reference) as opened:
        source_image = ImageOps.exif_transpose(opened).convert("RGB")
    source_face, _, source_variant, source_count = _detect_face(root, source_image, 0.30, 0)
    source_mesh = np.asarray(source_face["landmarks_xy"], dtype=np.float32)
    if len(source_mesh) != len(target_mesh):
        raise RuntimeError(
            f"Identity mesh has {len(source_mesh)} points; target has {len(target_mesh)}."
        )
    target_crop_mesh = _transform_points(target_mesh, crop_box)
    source_array, source_accessory_cleanup = _remove_source_accessories(
        root, source_image, source_mesh
    )
    target_array = np.asarray(crop, dtype=np.float32).copy()
    warped_only = np.zeros_like(target_array)
    coverage = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.float32)
    triangle_count = 0
    for triangle in _mesh_triangles(topology):
        if max(triangle) >= len(source_mesh):
            continue
        _warp_triangle(
            source_array,
            warped_only,
            coverage,
            source_mesh[np.asarray(triangle)],
            target_crop_mesh[np.asarray(triangle)],
        )
        triangle_count += 1

    feature_triangle_count = _warp_ring_fan(
        source_array,
        warped_only,
        coverage,
        source_mesh,
        target_crop_mesh,
        topology.get("lips"),
    )

    allowed = np.asarray(hard_mask.convert("L"), dtype=np.float32) / 255.0
    eye_source_mode = str(eye_source_mode).strip().lower()
    if eye_source_mode not in {"identity", "target"}:
        raise RuntimeError(f"Unsupported eye source mode: {eye_source_mode}")
    if eye_source_mode == "identity":
        eye_feature_warps = {
            key: _warp_feature_affine(
                source_array,
                warped_only,
                coverage,
                source_mesh,
                target_crop_mesh,
                topology.get(key),
                allowed,
            )
            for key in ("left_eye", "right_eye")
        }
    else:
        eye_feature_warps = {
            key: {"applied": False, "reason": "target-material-preserved"}
            for key in ("left_eye", "right_eye")
        }
    hidden_eye_suppression = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.float32)
    for key, result in eye_feature_warps.items():
        if result.get("applied"):
            continue
        if result.get("reason") == "target-material-preserved":
            target_eye = _feature_mask(target_crop_mesh, topology.get(key), padding=3)
            hidden_eye_suppression = np.maximum(
                hidden_eye_suppression,
                np.asarray(target_eye, dtype=np.float32) / 255.0,
            )
            continue
        if result.get("reason") != "feature-covered-by-hair-or-headwear":
            continue
        # The surrounding tesselation can carry eyelashes/highlights beyond the
        # closed eye ring. Use a broad local suppression; the approved pixels
        # are immediately recolored from covered identity skin below.
        hidden = _feature_mask(target_crop_mesh, topology.get(key), padding=25)
        hidden_eye_suppression = np.maximum(
            hidden_eye_suppression,
            np.asarray(hidden, dtype=np.float32) / 255.0,
        )
    coverage = np.clip(coverage * allowed, 0.0, 1.0)
    coverage = cv2.morphologyEx(
        np.uint8(coverage * 255),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    ).astype(np.float32) / 255.0
    preserve = np.asarray(preserve_feature_mask.convert("L"), dtype=np.float32) / 255.0
    coverage *= allowed * (1.0 - hidden_eye_suppression) * (1.0 - preserve)
    covered = coverage > 0.25
    allowed_pixels = max(1, int(np.count_nonzero(allowed > 0.5)))
    coverage_ratio = float(np.count_nonzero(covered) / allowed_pixels)
    if triangle_count < 100 or coverage_ratio < 0.20:
        raise RuntimeError(
            f"Identity mesh warp coverage is unsafe ({triangle_count} triangles, "
            f"{coverage_ratio:.1%} of edit zone)."
        )

    # Human-like targets can use the complete identity texture. For extreme
    # stylization (Vegeta's oversized forehead, for example), low mesh coverage
    # automatically makes target linework the dominant material while keeping
    # the warped identity geometry as a strong guide.
    automatic_mesh_strength = (
        1.0
        if coverage_ratio >= 0.60
        else float(np.interp(coverage_ratio, (0.25, 0.60), (0.45, 0.85)))
    )
    mesh_identity_strength = (
        automatic_mesh_strength
        if mesh_identity_strength_override is None
        else max(0.25, min(1.0, float(mesh_identity_strength_override)))
    )
    identity_alpha_2d = np.clip(
        cv2.GaussianBlur(coverage, (0, 0), 1.4) * mesh_identity_strength,
        0.0,
        1.0,
    )
    alpha = identity_alpha_2d[..., None]
    seeded = target_array * (1.0 - alpha) + warped_only * alpha
    seeded, tone_transfer = _tone_match_uncovered_region(
        seeded,
        target_array,
        coverage,
        identity_alpha_2d,
        allowed,
        uncovered_skin_mask,
    )
    # Reapply iconic target material exactly after all geometry/tone work.
    # This guarantees Luffy's teeth/eyes, Gojo's visible eye and each target's
    # facial ink remain target-authentic before the GPU refinement begins.
    feature_alpha = preserve[..., None]
    seeded = seeded * (1.0 - feature_alpha) + target_array * feature_alpha
    seed_image = Image.fromarray(np.uint8(np.clip(seeded, 0, 255)), mode="RGB")
    warp_image = Image.fromarray(np.uint8(np.clip(warped_only, 0, 255)), mode="RGB")
    warp_mask = Image.fromarray(np.uint8(np.clip(coverage * 255, 0, 255)), mode="L")
    return seed_image, warp_image, warp_mask, {
        "reference": str(identity_reference),
        "reference_sha256": sha256(identity_reference),
        "source_detection_score": float(source_face.get("score", 0.0)),
        "source_detector_variant": source_variant,
        "source_detected_faces": source_count,
        "source_accessory_cleanup": source_accessory_cleanup,
        "triangles": triangle_count,
        "feature_fill_triangles": feature_triangle_count,
        "eye_feature_warps": eye_feature_warps,
        "eye_source_mode": eye_source_mode,
        "hidden_eye_suppression_pixels": int(
            np.count_nonzero((hidden_eye_suppression > 0.25) & (allowed > 0.5))
        ),
        "coverage_ratio": round(coverage_ratio, 6),
        "mesh_identity_strength": round(mesh_identity_strength, 6),
        "mesh_identity_strength_mode": (
            "automatic" if mesh_identity_strength_override is None else "preset-override"
        ),
        "preserved_feature_pixels": int(np.count_nonzero(preserve > 0.25)),
        "uncovered_skin_tone_transfer": tone_transfer,
        "method": "cpu-mediapipe-478-triangle-warp-plus-semantic-tone-transfer",
    }


def _parse_box(value: str) -> tuple[float, float, float, float]:
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("box must be x,y,width,height with positive size")
    return tuple(parts)  # type: ignore[return-value]


def prepare_face_zone(
    root: Path,
    source: Path,
    job_id: str,
    *,
    min_confidence: float = 0.35,
    crop_factor: float = 1.65,
    face_index: int = 0,
    zone_expand: float = 1.10,
    identity_reference: Path | None = None,
    mesh_identity_strength: float | None = None,
    eye_protection_strength: float = 0.55,
    eye_source_mode: str = "identity",
    manual_box: tuple[float, float, float, float] | None = None,
    exclude_boxes: Iterable[tuple[float, float, float, float]] = (),
) -> dict:
    root, source = root.resolve(), source.resolve()
    if not source.is_file():
        raise RuntimeError(f"Uploaded target does not exist: {source}")
    for generated_root in (
        root / "artifacts",
        root / "Generators" / "ComfyUI" / "output",
    ):
        try:
            source.relative_to(generated_root.resolve())
        except ValueError:
            continue
        raise RuntimeError(
            "Fresh-retry policy rejected a generated image as the target. "
            "Use the immutable original upload/target; previous outputs may "
            "never become the next input."
        )
    cpu_runtime = _configure_cpu_runtime()
    with Image.open(source) as opened:
        original = ImageOps.exif_transpose(opened).convert("RGB")

    detection_score: float | None = None
    detection_bbox: np.ndarray | None = None
    detected_faces = 1
    detector_variant = "manual"
    mesh_points: np.ndarray | None = None
    topology: dict[str, np.ndarray] = {}
    if manual_box is None:
        face, topology, detector_variant, detected_faces = _detect_face(
            root, original, min_confidence, face_index
        )
        detection_score = float(face.get("score", 0.0))
        detection_bbox = np.asarray(face.get("bbox_xyxy"), dtype=np.float32)
        mesh_points = np.asarray(face["landmarks_xy"], dtype=np.float32)
        rings = _ordered_rings(map(tuple, topology["face_oval"]))
        if not rings:
            raise RuntimeError("Face outline model returned no face-oval topology.")
        oval_points = mesh_points[max(rings, key=len)]
    else:
        oval_points = _ellipse_points(manual_box)

    zone_expand = max(1.0, min(float(zone_expand), 1.35))
    full_face_points = _scale_outline(oval_points, zone_expand, 1.0 + (zone_expand - 1.0) * 0.72)
    # Never stretch the face toward the detector rectangle: tall hair and hats
    # can enlarge that box and were previously mistaken for forehead.  The
    # later exposed-skin contour grows upward only through skin-colored regions
    # until it reaches the separately traced hair/headwear boundary.
    ear_boxes = _ear_boxes(full_face_points, mesh_points)
    crop_extent = np.vstack(
        [full_face_points]
        + [np.asarray([(x0, y0), (x1, y1)], dtype=np.float32) for x0, y0, x1, y1 in ear_boxes]
    )
    crop_box = _square_crop_box(crop_extent, original.size, crop_factor)
    crop = original.crop(crop_box).resize((CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.LANCZOS)
    crop_oval = _transform_points(oval_points, crop_box)
    crop_full_face = _transform_points(full_face_points, crop_box)
    crop_polygon = [(float(x), float(y)) for x, y in crop_full_face]

    hard = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
    hard_draw = ImageDraw.Draw(hard)
    hard_draw.polygon(crop_polygon, fill=255)
    ear_geometry = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
    included_ear_lobes = 0
    crop_rgb = np.asarray(crop, dtype=np.float32)
    crop_lab = np.asarray(crop.convert("LAB"), dtype=np.float32)
    inner = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
    inner_points = _scale_outline(crop_oval, 0.72, 0.72)
    ImageDraw.Draw(inner).polygon(
        [(float(x), float(y)) for x, y in inner_points], fill=255
    )
    inner_selected = np.asarray(inner) > 0
    skin_lab = np.median(crop_lab[inner_selected], axis=0) if inner_selected.any() else None
    for ear_box in ear_boxes:
        mapped = _transform_points(
            np.asarray([(ear_box[0], ear_box[1]), (ear_box[2], ear_box[3])], dtype=np.float32),
            crop_box,
        )
        candidate = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
        ImageDraw.Draw(candidate).ellipse([tuple(mapped[0]), tuple(mapped[1])], fill=255)
        candidate_array = np.asarray(candidate) > 0
        if skin_lab is None:
            accepted = candidate
        else:
            light_delta = np.abs(crop_lab[..., 0] - skin_lab[0])
            chroma_delta = np.sqrt(
                (crop_lab[..., 1] - skin_lab[1]) ** 2
                + (crop_lab[..., 2] - skin_lab[2]) ** 2
            )
            skin_pixels = candidate_array & (light_delta < 82.0) & (chroma_delta < 27.0)
            accepted = Image.fromarray(np.uint8(skin_pixels) * 255, mode="L")
            # Fill over anime ink lines or small photo shadows without flooding
            # an ear candidate that is actually covered by hair/background.
            accepted = accepted.filter(ImageFilter.MaxFilter(17)).filter(ImageFilter.MinFilter(5))
            accepted = Image.fromarray(
                np.minimum(np.asarray(accepted), np.asarray(candidate)), mode="L"
            )
        outside_base = (np.asarray(accepted) > 0) & (np.asarray(hard) == 0)
        if int(outside_base.sum()) >= 24:
            hard = Image.fromarray(
                np.maximum(np.asarray(hard), np.asarray(accepted)), mode="L"
            )
            ear_geometry = Image.fromarray(
                np.maximum(np.asarray(ear_geometry), np.asarray(accepted)), mode="L"
            )
            hard_draw = ImageDraw.Draw(hard)
            included_ear_lobes += 1
    # Close the joins between the face plane and ear lobes.  This is deliberately
    # stronger than the earlier inner-oval mask: the full forehead, temples,
    # cheeks, jaw and ear-side skin must all be regenerated together.
    hard = hard.filter(ImageFilter.MaxFilter(13))
    geometric_face = hard.copy()
    (
        hard,
        head_envelope,
        hair_boundary,
        hair_exclusion,
        neck_anchor,
        semantic_labels,
        semantic_parser,
    ) = _semantic_head_zone(root, crop, geometric_face)
    # Capture antialiased skin pixels just outside the semantic contour. Without
    # this color-aware fringe, a one-pixel strip of the pale target can survive
    # around a newly dark jaw. Hair/headwear/clothing exclusion still wins.
    hard_before_fringe = np.asarray(hard) > 127
    semantic_skin_ids = (
        (1, 2, 8, 9, 17)
        if semantic_parser["mode"] == "parsenet-anime-fallback"
        else (2, 3)
    )
    semantic_skin = np.isin(semantic_labels, semantic_skin_ids) & hard_before_fringe
    skin_edge_fringe = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=bool)
    if int(semantic_skin.sum()) >= 64:
        expanded = cv2.dilate(
            hard_before_fringe.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
            iterations=1,
        ) > 0
        ring = expanded & ~hard_before_fringe
        lab = np.asarray(crop.convert("LAB"), dtype=np.float32)
        skin_median = np.median(lab[semantic_skin], axis=0)
        light_delta = np.abs(lab[..., 0] - skin_median[0])
        chroma_delta = np.sqrt(
            (lab[..., 1] - skin_median[1]) ** 2
            + (lab[..., 2] - skin_median[2]) ** 2
        )
        skin_edge_fringe = (
            ring
            & (light_delta < 52.0)
            & (chroma_delta < 30.0)
            & (np.asarray(hair_exclusion) < 64)
        )
        hard = Image.fromarray(
            np.uint8(hard_before_fringe | skin_edge_fringe) * 255, mode="L"
        )
    hard_bool = np.asarray(hard) > 127
    ear_bool = np.asarray(ear_geometry) > 0
    if semantic_parser["mode"] == "parsenet-anime-fallback":
        ear_bool |= np.isin(semantic_labels, (8, 9))
    ear_skin_mask = Image.fromarray(np.uint8(ear_bool & hard_bool) * 255, mode="L")

    preserve_feature_mask = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
    protected_color_features = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
    target_feature_components: dict[str, Image.Image] = {}
    target_feature_lock: dict = {"mode": "unavailable-without-target-mesh"}
    if identity_reference is not None and mesh_points is not None:
        crop_mesh = _transform_points(mesh_points, crop_box)
        (
            preserve_feature_mask,
            target_feature_components,
            target_feature_lock,
        ) = _target_material_feature_lock(crop, crop_mesh, topology, hard)
        protected_color_features = preserve_feature_mask.copy()
    for box in exclude_boxes:
        x, y, width, height = box
        mapped = _transform_points(
            np.asarray([(x, y), (x + width, y + height)], dtype=np.float32), crop_box
        )
        ImageDraw.Draw(hard).rectangle([tuple(mapped[0]), tuple(mapped[1])], fill=0)
    preserve_feature_mask = Image.fromarray(
        np.minimum(np.asarray(preserve_feature_mask), np.asarray(hard)), mode="L"
    )
    protected_color_features = Image.fromarray(
        np.minimum(np.asarray(protected_color_features), np.asarray(hard)), mode="L"
    )
    ear_skin_mask = Image.fromarray(
        np.minimum(np.asarray(ear_skin_mask), np.asarray(hard)), mode="L"
    )
    # `hard` is already the semantically approved neck-up skin zone. Every
    # approved pixel not reached by FaceMesh (notably ears, jaw rim and visible
    # neck) must inherit the identity palette; otherwise target skin survives.
    uncovered_skin_bool = (
        (np.asarray(hard) > 127)
        & (np.asarray(preserve_feature_mask) < 64)
    )
    uncovered_skin_mask = Image.fromarray(np.uint8(uncovered_skin_bool) * 255, mode="L")
    hard_array = np.asarray(hard, dtype=np.float32) / 255.0
    geometric_array = np.asarray(geometric_face, dtype=np.float32) / 255.0
    ys, xs = np.where(geometric_array > 0.5)
    if len(xs) == 0:
        raise RuntimeError("Computed face edit zone is empty.")
    face_left, face_right = int(xs.min()), int(xs.max())
    face_top, face_bottom = int(ys.min()), int(ys.max())
    face_width = max(1, face_right - face_left)
    face_height = max(1, face_bottom - face_top)

    # The whole semantic face receives full noise.  Earlier graded masks left
    # the outer forehead/cheeks tied to the target latent even when KSampler
    # denoise was 1.0, which suppressed both identity and skin tone.  Hair,
    # headwear, accessories and clothing are protected by the semantic mask,
    # so the complete remaining face can be regenerated coherently.
    # Protect the exact target eyes, mouth/teeth and dark facial linework from a
    # noisy redraw. Hair/headwear have already been subtracted from ``hard``.
    target_feature_region = np.asarray(preserve_feature_mask, dtype=np.float32) / 255.0
    # This remains configurable for experiments, but production target presets
    # use 1.0 so iconic oversized features are pixel-locked.
    eye_protection_strength = max(0.0, min(1.0, float(eye_protection_strength)))
    graded = hard_array * (1.0 - target_feature_region * eye_protection_strength)
    graded_image = Image.fromarray(np.uint8(np.round(graded * 255)), mode="L")

    identity_seed: Image.Image | None = None
    identity_warp: Image.Image | None = None
    identity_warp_mask: Image.Image | None = None
    identity_mesh: dict | None = None
    if identity_reference is not None:
        if mesh_points is None:
            raise RuntimeError("Identity mesh seeding requires an automatically detected target mesh.")
        identity_seed, identity_warp, identity_warp_mask, identity_mesh = _build_identity_mesh_seed(
            root,
            crop,
            crop_box,
            mesh_points,
            topology,
            hard,
            preserve_feature_mask,
            uncovered_skin_mask,
            identity_reference,
            mesh_identity_strength,
            eye_source_mode,
        )

    # A narrow seam feather is enough because the mesh seed already follows the
    # target contour. The old 10px blur exposed a pale halo around dark faces.
    grown = hard.filter(ImageFilter.MaxFilter(3))
    feather = grown.filter(ImageFilter.GaussianBlur(radius=2.0))
    # Feather only outward. Every semantically approved skin pixel remains
    # fully generated; target skin can no longer leak back inside the hairline.
    soft = Image.fromarray(
        np.maximum(np.asarray(hard), np.asarray(feather)), mode="L"
    )
    core = hard.filter(ImageFilter.MinFilter(25))
    match_ring_array = np.clip(
        np.asarray(soft, dtype=np.int16) - np.asarray(core, dtype=np.int16), 0, 255
    ).astype(np.uint8)
    match_ring = Image.fromarray(match_ring_array, mode="L")

    month = datetime.now().strftime("%Y-%m")
    output_dir = root / "artifacts" / "face_zones" / month / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    original_path = output_dir / "original.png"
    crop_path = output_dir / "face_crop_512.png"
    hard_path = output_dir / "edit_mask_hard.png"
    graded_path = output_dir / "edit_mask_graded.png"
    soft_path = output_dir / "edit_mask_soft.png"
    match_ring_path = output_dir / "skin_match_ring.png"
    hair_path = output_dir / "hair_headwear_exclusion.png"
    head_envelope_path = output_dir / "head_envelope_mask.png"
    hair_boundary_path = output_dir / "hair_boundary_mask.png"
    neck_path = output_dir / "neck_anchor_mask.png"
    semantic_path = output_dir / "semantic_labels.png"
    seed_path = output_dir / "identity_mesh_seed.png"
    warp_path = output_dir / "identity_mesh_warp.png"
    warp_mask_path = output_dir / "identity_mesh_warp_mask.png"
    preserve_feature_path = output_dir / "protected_seed_features.png"
    ear_skin_path = output_dir / "ear_skin_tone_zone.png"
    uncovered_skin_path = output_dir / "uncovered_skin_tone_zone.png"
    skin_edge_path = output_dir / "skin_edge_fringe.png"
    protected_color_path = output_dir / "protected_color_features.png"
    overlay_path = output_dir / "face_outline_preview.png"
    ordered_outline_path = output_dir / "head_hair_outline_preview.png"
    crop_overlay_path = output_dir / "face_crop_outline_preview.png"
    zone_path = output_dir / "face_zone.json"
    original.save(original_path, "PNG", optimize=True)
    crop.save(crop_path, "PNG", optimize=True)
    hard.save(hard_path, "PNG", optimize=True)
    graded_image.save(graded_path, "PNG", optimize=True)
    soft.save(soft_path, "PNG", optimize=True)
    match_ring.save(match_ring_path, "PNG", optimize=True)
    hair_exclusion.save(hair_path, "PNG", optimize=True)
    head_envelope.save(head_envelope_path, "PNG", optimize=True)
    hair_boundary.save(hair_boundary_path, "PNG", optimize=True)
    neck_anchor.save(neck_path, "PNG", optimize=True)
    _semantic_preview(semantic_labels, semantic_parser["mode"]).save(
        semantic_path, "PNG", optimize=True
    )
    if identity_seed is not None and identity_warp is not None and identity_warp_mask is not None:
        identity_seed.save(seed_path, "PNG", optimize=True)
        identity_warp.save(warp_path, "PNG", optimize=True)
        identity_warp_mask.save(warp_mask_path, "PNG", optimize=True)
        preserve_feature_mask.save(preserve_feature_path, "PNG", optimize=True)
        ear_skin_mask.save(ear_skin_path, "PNG", optimize=True)
        uncovered_skin_mask.save(uncovered_skin_path, "PNG", optimize=True)
        Image.fromarray(np.uint8(skin_edge_fringe) * 255, mode="L").save(
            skin_edge_path, "PNG", optimize=True
        )
        protected_color_features.save(protected_color_path, "PNG", optimize=True)

    overlay = original.convert("RGBA")
    zone_fill = Image.new("RGBA", original.size, (0, 0, 0, 0))
    full_size_mask = Image.new("L", original.size, 0)
    left, top, right, bottom = crop_box
    full_size_mask.paste(
        hard.resize((right - left, bottom - top), Image.Resampling.BILINEAR),
        (left, top),
    )
    red_fill = Image.new("RGBA", original.size, (255, 65, 65, 0))
    red_fill.putalpha(full_size_mask.point(lambda value: int(value * 0.28)))
    zone_fill = Image.alpha_composite(zone_fill, red_fill)
    full_hair_mask = Image.new("L", original.size, 0)
    full_hair_mask.paste(
        hair_exclusion.resize((right - left, bottom - top), Image.Resampling.NEAREST),
        (left, top),
    )
    green_fill = Image.new("RGBA", original.size, (40, 230, 90, 0))
    green_fill.putalpha(full_hair_mask.point(lambda value: int(value * 0.30)))
    zone_fill = Image.alpha_composite(zone_fill, green_fill)
    full_neck_mask = Image.new("L", original.size, 0)
    full_neck_mask.paste(
        neck_anchor.resize((right - left, bottom - top), Image.Resampling.NEAREST),
        (left, top),
    )
    blue_fill = Image.new("RGBA", original.size, (45, 120, 255, 0))
    blue_fill.putalpha(full_neck_mask.point(lambda value: int(value * 0.34)))
    zone_fill = Image.alpha_composite(zone_fill, blue_fill)
    overlay = Image.alpha_composite(overlay, zone_fill)
    draw = ImageDraw.Draw(overlay)
    if mesh_points is not None and "tesselation" in topology:
        for a, b in topology["tesselation"]:
            if int(a) < len(mesh_points) and int(b) < len(mesh_points):
                draw.line(
                    [tuple(mesh_points[int(a)]), tuple(mesh_points[int(b)])],
                    fill=(0, 225, 255, 105), width=1,
                )
    edge = full_size_mask.filter(ImageFilter.FIND_EDGES).point(lambda value: 255 if value > 18 else 0)
    yellow = Image.new("RGBA", original.size, (255, 220, 0, 0))
    yellow.putalpha(edge)
    overlay = Image.alpha_composite(overlay, yellow)
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((left, top, right - 1, bottom - 1), outline=(255, 0, 220, 255), width=2)
    overlay.convert("RGB").save(overlay_path, "PNG", optimize=True)

    # Diagnostic contract requested by ByrdHouse: cyan is the first closed
    # head/neck envelope, magenta is the separately detected hair/headwear, and
    # yellow is the exact final change zone after subtraction.
    ordered = original.convert("RGBA")
    full_head_mask = Image.new("L", original.size, 0)
    full_head_mask.paste(
        head_envelope.resize((right - left, bottom - top), Image.Resampling.NEAREST),
        (left, top),
    )
    full_hair_boundary = Image.new("L", original.size, 0)
    full_hair_boundary.paste(
        hair_boundary.resize((right - left, bottom - top), Image.Resampling.NEAREST),
        (left, top),
    )
    for mask, color in (
        (full_head_mask, (0, 235, 255, 255)),
        (full_hair_boundary, (255, 0, 220, 255)),
        (full_size_mask, (255, 220, 0, 255)),
    ):
        outline_edge = mask.filter(ImageFilter.FIND_EDGES).point(
            lambda value: 255 if value > 18 else 0
        )
        ink = Image.new("RGBA", original.size, color)
        ink.putalpha(outline_edge)
        ordered = Image.alpha_composite(ordered, ink)
    ordered.convert("RGB").save(ordered_outline_path, "PNG", optimize=True)

    crop_overlay = crop.convert("RGBA")
    crop_fill = Image.new("RGBA", crop.size, (255, 65, 65, 0))
    crop_fill.putalpha(hard.point(lambda value: int(value * 0.28)))
    crop_overlay = Image.alpha_composite(crop_overlay, crop_fill)
    crop_edge = hard.filter(ImageFilter.FIND_EDGES).point(lambda value: 255 if value > 18 else 0)
    crop_yellow = Image.new("RGBA", crop.size, (255, 220, 0, 0))
    crop_yellow.putalpha(crop_edge)
    crop_overlay = Image.alpha_composite(crop_overlay, crop_yellow)
    crop_overlay.convert("RGB").save(crop_overlay_path, "PNG", optimize=True)

    record = {
        "version": 1,
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_sha256": sha256(source),
        "retry_policy": "fresh-from-immutable-original; no generated parent",
        "generated_parent": None,
        "processor": "cpu-mediapipe-face-landmarker",
        "cpu_runtime": cpu_runtime,
        "model": str(_model_path(root)),
        "model_sha256": MODEL_SHA256,
        "model_source": MODEL_SOURCE,
        "detector_variant": detector_variant,
        "detection_score": detection_score,
        "detected_faces": detected_faces,
        "selected_face_index": face_index,
        "manual_zone": manual_box is not None,
        "zone_kind": "closed-head-envelope-minus-independent-hair-outline-plus-neck",
        "zone_rule": "trace and close the exposed-skin head envelope; trace hair/headwear separately; subtract it; retain connected neck",
        "zone_expand": zone_expand,
        "ear_lobes": included_ear_lobes,
        "semantic_parser": semantic_parser,
        "identity_mesh": identity_mesh,
        "crop_box": {"x": left, "y": top, "width": right - left, "height": bottom - top},
        "canvas_size": CANVAS_SIZE,
        "exclude_boxes": [list(box) for box in exclude_boxes],
        "artifacts": {
            "original": str(original_path),
            "face_crop": str(crop_path),
            "hard_mask": str(hard_path),
            "graded_mask": str(graded_path),
            "soft_mask": str(soft_path),
            "skin_match_ring": str(match_ring_path),
            "hair_headwear_exclusion": str(hair_path),
            "head_envelope": str(head_envelope_path),
            "hair_boundary": str(hair_boundary_path),
            "neck_anchor": str(neck_path),
            "semantic_labels": str(semantic_path),
            **(
                {
                    "identity_mesh_seed": str(seed_path),
                    "identity_mesh_warp": str(warp_path),
                    "identity_mesh_warp_mask": str(warp_mask_path),
                    "protected_seed_features": str(preserve_feature_path),
                    "ear_skin_tone_zone": str(ear_skin_path),
                    "uncovered_skin_tone_zone": str(uncovered_skin_path),
                    "skin_edge_fringe": str(skin_edge_path),
                    "protected_color_features": str(protected_color_path),
                }
                if identity_mesh is not None
                else {}
            ),
            "outline_preview": str(overlay_path),
            "ordered_head_hair_preview": str(ordered_outline_path),
            "crop_outline_preview": str(crop_overlay_path),
        },
        "status": "outlined; GPU edit not yet executed",
    }
    zone_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    record["zone_file"] = str(zone_path)
    return record


def composite_generated(zone_file: Path, generated_crop: Path, output: Path) -> Path:
    zone = json.loads(zone_file.read_text(encoding="utf-8-sig"))
    artifacts = zone["artifacts"]
    with Image.open(artifacts["original"]) as opened:
        original = opened.convert("RGB")
    with Image.open(generated_crop) as opened:
        generated = opened.convert("RGB")
    with Image.open(artifacts["soft_mask"]) as opened:
        soft = opened.convert("L")
    with Image.open(artifacts["face_crop"]) as opened:
        target_crop = opened.convert("RGB")
    with Image.open(artifacts["hard_mask"]) as opened:
        hard = np.asarray(opened.convert("L"), dtype=np.float32) / 255.0
    protected_color = np.zeros(hard.shape, dtype=np.float32)
    protected_color_path = artifacts.get("protected_color_features")
    if protected_color_path and Path(protected_color_path).is_file():
        with Image.open(protected_color_path) as opened:
            protected_color = np.asarray(opened.convert("L"), dtype=np.float32) / 255.0
    # Preserve the generated skin's mean color while matching its contrast to
    # the target artwork. This harmonizes lighting/style without whitening the
    # intended Carey complexion. The soft ring below performs the seam match.
    generated_array = np.asarray(generated, dtype=np.float32)
    target_array = np.asarray(target_crop.resize(generated.size, Image.Resampling.LANCZOS), dtype=np.float32)
    selected = hard > 0.5
    skin_selected = selected & (protected_color < 0.25)
    if int(skin_selected.sum()) >= 128:
        generated_u8 = np.uint8(np.clip(generated_array, 0, 255))
        generated_lab = cv2.cvtColor(generated_u8, cv2.COLOR_RGB2LAB).astype(np.float32)
        skin_l = generated_lab[..., 0][skin_selected]
        lower, upper = np.percentile(skin_l, (34, 76))
        fill_sample = skin_selected & (generated_lab[..., 0] >= lower) & (generated_lab[..., 0] <= upper)
        if int(fill_sample.sum()) >= 64:
            fill_median = np.median(generated_lab[fill_sample], axis=0)
            highlight_start = min(float(np.percentile(skin_l, 84)), float(fill_median[0] + 36.0))
            highlight_cap = min(255.0, float(fill_median[0] + 58.0))
            bright = skin_selected & (generated_lab[..., 0] > highlight_start)
            weight = np.zeros(hard.shape, dtype=np.float32)
            weight[bright] = np.clip(
                (generated_lab[..., 0][bright] - highlight_start)
                / max(1.0, 255.0 - highlight_start),
                0.0,
                1.0,
            )
            generated_lab[..., 0][bright] = np.minimum(
                generated_lab[..., 0][bright], highlight_cap
            )
            for channel in (1, 2):
                generated_lab[..., channel] = (
                    generated_lab[..., channel] * (1.0 - weight * 0.82)
                    + float(fill_median[channel]) * weight * 0.82
                )
            generated_array = cv2.cvtColor(
                np.uint8(np.clip(generated_lab, 0, 255)), cv2.COLOR_LAB2RGB
            ).astype(np.float32)
    if selected.any():
        adjusted = generated_array.copy()
        for channel in range(3):
            generated_values = generated_array[..., channel][selected]
            target_values = target_array[..., channel][selected]
            generated_mean = float(generated_values.mean())
            generated_std = max(1.0, float(generated_values.std()))
            target_std = max(1.0, float(target_values.std()))
            ratio = min(1.25, max(0.75, target_std / generated_std))
            ratio = 1.0 + (ratio - 1.0) * 0.35
            adjusted[..., channel] = (
                generated_array[..., channel] - generated_mean
            ) * ratio + generated_mean
        generated = Image.fromarray(np.uint8(np.clip(adjusted, 0, 255)), mode="RGB")
    box = zone["crop_box"]
    side = int(box["width"])
    generated = generated.resize((side, side), Image.Resampling.LANCZOS)
    soft = soft.resize((side, side), Image.Resampling.BILINEAR)
    original.paste(generated, (int(box["x"]), int(box["y"])), soft)
    output.parent.mkdir(parents=True, exist_ok=True)
    original.save(output, "PNG", optimize=True)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Detect and save a CPU face outline/edit zone.")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--job-id", required=True)
    prepare.add_argument("--min-confidence", type=float, default=0.35)
    prepare.add_argument("--crop-factor", type=float, default=1.65)
    prepare.add_argument("--face-index", type=int, default=0)
    prepare.add_argument("--zone-expand", type=float, default=1.10)
    prepare.add_argument("--identity-reference", type=Path)
    prepare.add_argument("--mesh-identity-strength", type=float)
    prepare.add_argument("--eye-protection", type=float, default=0.55)
    prepare.add_argument("--eye-source", choices=("identity", "target"), default="identity")
    prepare.add_argument("--manual-box", type=_parse_box)
    prepare.add_argument("--exclude-box", type=_parse_box, action="append", default=[])
    composite = sub.add_parser("composite", help="Composite a generated 512px crop through the saved soft zone.")
    composite.add_argument("--zone", type=Path, required=True)
    composite.add_argument("--generated-crop", type=Path, required=True)
    composite.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        record = prepare_face_zone(
            args.root,
            args.input,
            args.job_id,
            min_confidence=args.min_confidence,
            crop_factor=args.crop_factor,
            face_index=args.face_index,
            zone_expand=args.zone_expand,
            identity_reference=args.identity_reference,
            mesh_identity_strength=args.mesh_identity_strength,
            eye_protection_strength=args.eye_protection,
            eye_source_mode=args.eye_source,
            manual_box=args.manual_box,
            exclude_boxes=args.exclude_box,
        )
        print(json.dumps(record, indent=2))
    else:
        output = composite_generated(args.zone, args.generated_crop, args.output)
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
