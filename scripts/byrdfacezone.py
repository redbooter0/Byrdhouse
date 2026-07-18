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
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
import cv2
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
from safetensors.torch import load_file
from facezone_composite import restore_protected_material


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
    # MediaPipe's inner oval can start below most of an extreme anime
    # forehead. Give semantic analysis up to 1.45 face-heights of headroom;
    # hair/headwear remain separate protected classes and are subtracted later.
    roi[
        max(0, top - int(1.45 * height)): min(seed_mask.shape[0], bottom + int(0.72 * height) + 1),
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

    def bounds(mask: np.ndarray) -> dict | None:
        bound_y, bound_x = np.where(mask)
        if not len(bound_x):
            return None
        return {
            "x": int(bound_x.min()),
            "y": int(bound_y.min()),
            "width": int(bound_x.max() - bound_x.min() + 1),
            "height": int(bound_y.max() - bound_y.min() + 1),
        }

    # Only head/ear evidence participates in the closed hull.  Neck evidence
    # is joined later so a shirt collar or shoulder never becomes head skin.
    head_gate = (
        (rows <= min(seed.shape[0] - 1, seed_bottom + int(seed_height * 0.16)))
        # Match the semantic recovery corridor on the turned side.  Extreme
        # anime hair can split a forehead lobe farther than a normal ear box;
        # clipping the head gate here would discover that skin but discard its
        # outer half before the contour is traced.
        & (cols >= max(0, seed_left - int(seed_width * 0.65)))
        & (cols <= min(seed.shape[1] - 1, seed_right + int(seed_width * 0.34)))
        & roi
    )
    support = (seed | exposed_skin) & head_gate
    support = cv2.morphologyEx(
        support.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    ) > 0
    attached_support = _components_touching_seed(
        support,
        cv2.dilate(seed.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0,
    )
    recovered_upper_skin = np.zeros(seed.shape, dtype=bool)
    # Extreme anime foreheads can begin well above MediaPipe's inner face oval
    # and be separated from that seed by eyebrow/hairline ink.  Keep large
    # semantic-skin components that extend above the seed, overlap its head
    # width, and reach back to the seed's upper corridor.  This is still
    # semantic skin only; hair/headwear are traced and subtracted afterward.
    upper_support = cv2.morphologyEx(
        (exposed_skin & head_gate).astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    ) > 0
    component_count, component_labels, component_stats, _ = (
        cv2.connectedComponentsWithStats(
            upper_support.astype(np.uint8), connectivity=8
        )
    )
    minimum_overlap = max(12, int(round(seed_width * 0.10)))
    reconnect_floor = seed_top - int(round(seed_height * 0.26))
    for component in range(1, component_count):
        area = int(component_stats[component, cv2.CC_STAT_AREA])
        component_left = int(component_stats[component, cv2.CC_STAT_LEFT])
        component_top = int(component_stats[component, cv2.CC_STAT_TOP])
        component_width = int(component_stats[component, cv2.CC_STAT_WIDTH])
        component_height = int(component_stats[component, cv2.CC_STAT_HEIGHT])
        component_right = component_left + component_width - 1
        component_bottom = component_top + component_height - 1
        horizontal_overlap = max(
            0,
            min(component_right, seed_right) - max(component_left, seed_left) + 1,
        )
        if (
            area >= 64
            and component_top < seed_top
            and component_bottom >= reconnect_floor
            and horizontal_overlap >= minimum_overlap
        ):
            recovered_upper_skin |= (
                (component_labels == component) & exposed_skin & head_gate
            )
    support = attached_support | recovered_upper_skin

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
    traversal = _ordered_body_part_traversal(envelope, neck_support)
    if not traversal.get("passed"):
        raise RuntimeError(
            f"Closed head/body traversal failed: {traversal.get('reason', 'unsafe geometry')}")
    return envelope, {
        "method": "opencv-connected-exposed-skin-closed-convex-head-contour",
        "closed": True,
        "hull_vertices": hull_vertices,
        "support_pixels": int(np.count_nonzero(support)),
        "recovered_upper_skin_pixels": int(np.count_nonzero(recovered_upper_skin)),
        "seed_bbox": bounds(seed),
        "roi_bbox": bounds(roi),
        "exposed_skin_bbox": bounds(exposed_skin),
        "recovered_upper_skin_bbox": bounds(recovered_upper_skin),
        "support_bbox": bounds(support),
        "head_pixels": int(np.count_nonzero(closed_head)),
        "neck_pixels": int(np.count_nonzero(neck_support)),
        "envelope_pixels": int(np.count_nonzero(envelope)),
        "body_part_traversal": traversal,
    }


def _semantic_head_zone(
    root: Path,
    crop: Image.Image,
    geometric_face: Image.Image,
    absent_accessories: Iterable[str] = (),
) -> tuple[Image.Image, Image.Image, Image.Image, Image.Image, Image.Image, np.ndarray, dict]:
    """Build `neck + connected head - hair/headwear` on CPU.

    Real images use the small Apache-2.0 MediaPipe model.  Anime frequently
    falls outside that model's domain, so the already-installed ParseNet is a
    private local fallback.  The facial mesh fills eyes, mouth and ink-line
    holes, while semantic hair/headwear always wins as a protection mask.
    """
    seed = np.asarray(geometric_face.convert("L")) > 127
    requested_absent = tuple(
        dict.fromkeys(str(name).strip().lower() for name in absent_accessories if str(name).strip())
    )
    supported_absent = {"eyeglasses": 3, "headwear": 14, "earrings": 15, "necklaces": 16}
    unknown_absent = sorted(set(requested_absent) - set(supported_absent))
    if unknown_absent:
        raise RuntimeError(
            "Unsupported preset absent-accessory class(es): " + ", ".join(unknown_absent)
        )
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
        # A target preset may assert that an accessory is truly absent. Anime
        # parsers otherwise confuse eye ink and large foreheads with glasses or
        # hats, punching holes in the identity seed. Only unlock contradictory
        # pixels inside the detected 478-point face; everything outside that
        # audited geometry remains protected, and hair/clothing never unlock.
        corrected_absent: dict[str, int] = {}
        reclassified_absent: dict[str, int] = {}
        for name in requested_absent:
            label = supported_absent[name]
            if name == "headwear":
                raw_hair = ((category == 13) & roi).astype(np.uint8)
                component_count, components, stats, _ = cv2.connectedComponentsWithStats(
                    raw_hair, connectivity=8
                )
                confirmed_hair = np.zeros(seed.shape, dtype=bool)
                for component_id in range(1, component_count):
                    if int(stats[component_id, cv2.CC_STAT_AREA]) >= 400:
                        confirmed_hair |= components == component_id
                hair_connected = cv2.dilate(
                    confirmed_hair.astype(np.uint8),
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)),
                    iterations=1,
                ) > 0
                protected_as_hair = (category == label) & roi & hair_connected
                contradictory = (category == label) & roi & ~protected_as_hair
                reclassified_absent[name] = int(np.count_nonzero(protected_as_hair))
            else:
                contradictory = (category == label) & seed
                reclassified_absent[name] = 0
            corrected_absent[name] = int(np.count_nonzero(contradictory))
            semantic_keep |= contradictory
            hair_headwear &= ~contradictory
            other_exclusion &= ~contradictory
        exclusion = hair_headwear | other_exclusion
        labels_preview = category

        residual_absent = {
            name: max(
                0,
                int(np.count_nonzero((category == supported_absent[name]) & seed & exclusion))
                - int(reclassified_absent.get(name, 0)),
            )
            for name in requested_absent
        }
        parser["preset_absent_accessories"] = list(requested_absent)
        parser["preset_absent_accessory_reclassified_as_hair"] = reclassified_absent

        parser["preset_absent_accessory_corrections"] = corrected_absent
        parser["residual_absent_accessory_pixels_in_geometric_face"] = residual_absent
    parser.setdefault("preset_absent_accessories", list(requested_absent))
    parser.setdefault("preset_absent_accessory_corrections", {})
    parser.setdefault("preset_absent_accessory_reclassified_as_hair", {})
    parser.setdefault("residual_absent_accessory_pixels_in_geometric_face", {})


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
            # The landmark oval can begin at the eyes on hard-anime faces.
            # Search a full head-height above it and farther toward the turned
            # side so a hair spike cannot hide a detached forehead lobe from
            # color discovery.  Hair is still independently protected and
            # subtracted after the complete skin silhouette is recovered.
            (rows >= max(0, seed_top - int(seed_height * 1.45)))
            & (rows <= min(seed.shape[0] - 1, seed_bottom + int(seed_height * 0.32)))
            & (cols >= max(0, seed_left - int(seed_width * 0.65)))
            & (cols <= min(seed.shape[1] - 1, seed_right + int(seed_width * 0.38)))
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
        # Follow every connected occurrence of the measured skin pigment.
        # Close only the connectivity support so narrow anime ink/scar strokes
        # do not split one skin surface into false islands; recovery itself is
        # intersected with the original color match and therefore never paints
        # over that linework. Hats/clothing/accessories remain ineligible.
        color_support = color_like_skin & (recoverable_hair | semantic_keep) & roi
        connected_support = cv2.morphologyEx(
            color_support.astype(np.uint8),
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
        ) > 0
        attached = _components_touching_seed(
            connected_support,
            cv2.dilate(
                confirmed_samples.astype(np.uint8),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
            ) > 0,
        )
        recovered_skin = attached & color_like_skin & recoverable_hair

        # A deep anime hair wedge can completely split one forehead into two
        # skin islands.  Connectivity alone then discards the outer lobe.  Add
        # large, measured-skin components that occupy the upper-head corridor,
        # approach the landmark oval laterally, and descend back to its brow
        # band.  We add only the original color-matched pixels; the bridge is
        # used for discovery, never painted into the editable mask.  The
        # independent hair outline below is subsequently subtracted, keeping
        # the widow's-peak boundary and interior hair locked.
        detached_upper_skin = np.zeros(seed.shape, dtype=bool)
        detached_component_count = 0
        candidate_support = cv2.morphologyEx(
            (color_like_skin & recoverable_hair).astype(np.uint8),
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        ) > 0
        candidate_count, candidate_labels, candidate_stats, _ = (
            cv2.connectedComponentsWithStats(
                candidate_support.astype(np.uint8), connectivity=8
            )
        )
        minimum_detached_area = max(128, int(round(seed_width * seed_height * 0.008)))
        approach_left = seed_left - int(round(seed_width * 0.22))
        corridor_left = seed_left - int(round(seed_width * 0.65))
        corridor_right = seed_right + int(round(seed_width * 0.18))
        reconnect_floor = seed_top - int(round(seed_height * 0.18))
        for component_id in range(1, candidate_count):
            area = int(candidate_stats[component_id, cv2.CC_STAT_AREA])
            component_left = int(candidate_stats[component_id, cv2.CC_STAT_LEFT])
            component_top = int(candidate_stats[component_id, cv2.CC_STAT_TOP])
            component_width = int(candidate_stats[component_id, cv2.CC_STAT_WIDTH])
            component_height = int(candidate_stats[component_id, cv2.CC_STAT_HEIGHT])
            component_right = component_left + component_width - 1
            component_bottom = component_top + component_height - 1
            component_mask = candidate_labels == component_id
            already_attached = int(np.count_nonzero(component_mask & attached)) >= 12
            if (
                not already_attached
                and area >= minimum_detached_area
                and component_top < seed_top
                and component_bottom >= reconnect_floor
                and component_left >= max(0, corridor_left)
                and component_right >= max(0, approach_left)
                and component_right <= min(seed.shape[1] - 1, corridor_right)
            ):
                detached_upper_skin |= component_mask & color_like_skin & recoverable_hair
                detached_component_count += 1
        recovered_skin |= detached_upper_skin
        exclusion &= ~recovered_skin
        hair_headwear &= ~recovered_skin
        semantic_keep |= recovered_skin
        parser["detached_upper_skin_pixels"] = int(
            np.count_nonzero(detached_upper_skin)
        )
        parser["detached_upper_skin_components"] = int(detached_component_count)
        if np.any(detached_upper_skin):
            detached_y, detached_x = np.where(detached_upper_skin)
            parser["detached_upper_skin_bbox"] = {
                "x": int(detached_x.min()),
                "y": int(detached_y.min()),
                "width": int(detached_x.max() - detached_x.min() + 1),
                "height": int(detached_y.max() - detached_y.min() + 1),
            }
        else:
            parser["detached_upper_skin_bbox"] = None

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
        # Anime ink can fully disconnect the exposed neck strip behind an ear.
        # Recover skin-colored background islands inside the audited jaw-to-
        # collar corridor; color distance and the corridor reject sky/collar.
        detached_neck_skin = similar_skin & (category == 0)
        color_neck |= detached_neck_skin
        parser["detached_neck_skin_pixels"] = int(np.count_nonzero(detached_neck_skin))
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
            "skin_recovery_rule": "all measured skin-pigment pixels connected to confirmed skin; linework preserved",
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
) -> bool:
    if not (
        np.all(np.isfinite(source_triangle))
        and np.all(np.isfinite(target_triangle))
    ):
        return False
    source_edges = source_triangle[1:] - source_triangle[0]
    target_edges = target_triangle[1:] - target_triangle[0]
    source_area = abs(
        float(
            source_edges[0, 0] * source_edges[1, 1]
            - source_edges[0, 1] * source_edges[1, 0]
        )
    ) * 0.5
    target_area = abs(
        float(
            target_edges[0, 0] * target_edges[1, 1]
            - target_edges[0, 1] * target_edges[1, 0]
        )
    ) * 0.5
    if min(source_area, target_area) < 0.25:
        return False
    source_rect = cv2.boundingRect(source_triangle.astype(np.float32))
    target_rect = cv2.boundingRect(target_triangle.astype(np.float32))
    sx, sy, sw, sh = source_rect
    tx, ty, tw, th = target_rect
    # BORDER_REFLECT_101 is pathological for a one-pixel source axis on some
    # OpenCV Windows builds. Degenerate anime-mesh slivers are visually empty,
    # so reject them instead of letting one triangle spin the CPU indefinitely.
    if min(sw, sh, tw, th) < 2:
        return False
    if sx < 0 or sy < 0 or sx + sw > source.shape[1] or sy + sh > source.shape[0]:
        return False
    if tx < 0 or ty < 0 or tx + tw > destination.shape[1] or ty + th > destination.shape[0]:
        return False

    source_local = source_triangle - np.asarray((sx, sy), dtype=np.float32)
    target_local = target_triangle - np.asarray((tx, ty), dtype=np.float32)
    patch = source[sy:sy + sh, sx:sx + sw]
    transform = cv2.getAffineTransform(source_local.astype(np.float32), target_local.astype(np.float32))
    if not np.all(np.isfinite(transform)):
        return False
    try:
        condition = float(np.linalg.cond(transform[:, :2]))
    except np.linalg.LinAlgError:
        return False
    if not math.isfinite(condition) or condition > 250.0:
        return False
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
    return True


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


def _feature_harmonize_mask(
    identity_seed: Image.Image,
    hard_mask: Image.Image,
    hair_exclusion: Image.Image,
    crop_mesh: np.ndarray,
    topology: dict[str, np.ndarray],
) -> Image.Image:
    """Build a soft facial-ink mask for a local masked latent pass.

    Eye and lip rings guarantee feature coverage. Canny edges add brows, nose,
    beard and cheek ink. An eroded semantic core prevents the pass from
    touching hair, headwear, clothing or the outer composite seam.
    """
    hard = np.asarray(hard_mask.convert("L")) > 127
    protected = np.asarray(hair_exclusion.convert("L")) > 63
    core = cv2.erode(
        hard.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)),
        iterations=1,
    ) > 0
    explicit = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.uint8)
    for key, padding in (("left_eye", 9), ("right_eye", 9), ("lips", 10)):
        explicit = np.maximum(
            explicit,
            np.asarray(_feature_mask(crop_mesh, topology.get(key), padding=padding)),
        )

    rgb = np.asarray(identity_seed.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ink = cv2.Canny(gray, 38, 112)
    ink = cv2.dilate(
        ink,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        iterations=1,
    )
    combined = (((explicit > 0) & hard) | ((ink > 0) & core)) & ~protected
    if int(np.count_nonzero(combined)) < 64:
        raise RuntimeError("Facial-feature harmonize mask is unexpectedly empty.")
    soft = cv2.GaussianBlur(combined.astype(np.float32), (0, 0), 1.35)
    soft = np.clip(soft * hard.astype(np.float32), 0.0, 1.0)
    return Image.fromarray(np.uint8(np.round(soft * 255)), mode="L")


def _point_dict(point: np.ndarray) -> dict[str, int]:
    return {"x": int(point[0]), "y": int(point[1])}



def _ordered_body_part_traversal(
    envelope: np.ndarray,
    neck_support: np.ndarray,
) -> dict:
    """Audit the closed neck-left -> top -> neck-right head traversal."""
    contours, _ = cv2.findContours(
        envelope.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    if not contours:
        return {"passed": False, "reason": "no-closed-envelope-contour"}
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    neck_y, neck_x = np.where(neck_support)
    if len(neck_x) < 8:
        return {"passed": False, "reason": "no-connected-neck-anchor"}

    neck_floor = float(np.percentile(neck_y, 78))
    floor_points = np.column_stack((neck_x[neck_y >= neck_floor], neck_y[neck_y >= neck_floor]))
    if len(floor_points) < 2:
        return {"passed": False, "reason": "neck-anchor-has-no-width"}
    neck_left = floor_points[np.argmin(floor_points[:, 0])]
    neck_right = floor_points[np.argmax(floor_points[:, 0])]
    left = contour[np.argmin(contour[:, 0])]
    top = contour[np.argmin(contour[:, 1])]
    right = contour[np.argmax(contour[:, 0])]

    vertical_span = int(max(neck_left[1], neck_right[1]) - top[1])
    horizontal_span = int(right[0] - left[0])
    neck_width = int(neck_right[0] - neck_left[0])
    checks = {
        "closed-contour": len(contour) >= 32,
        "head-above-neck": vertical_span >= 32,
        "head-has-width": horizontal_span >= 32,
        "neck-has-width": neck_width >= 4,
        # A sharp anime forehead lobe can make the uppermost point coincide
        # with the outermost point on the first, still-clipped crop.  Treat an
        # inclusive cap as valid here; crop-boundary preflight below owns the
        # clipping decision and will expand/translate before GPU execution.
        "top-between-sides": bool(left[0] <= top[0] <= right[0]),
        "top-above-neck": bool(top[1] < min(neck_left[1], neck_right[1])),
    }
    failed_checks = [name for name, result in checks.items() if not result]
    passed = not failed_checks
    return {
        "passed": bool(passed),
        "closed": True,
        "contour_points": int(len(contour)),
        "order": [
            "neck-left",
            "left-outer-head-and-ear",
            "top-of-head",
            "right-outer-head-and-ear",
            "neck-right",
            "neck-anchor-close",
        ],
        "checkpoints": {
            "neck_left": _point_dict(neck_left),
            "left_outer": _point_dict(left),
            "top": _point_dict(top),
            "right_outer": _point_dict(right),
            "neck_right": _point_dict(neck_right),
        },
        "vertical_span": vertical_span,
        "horizontal_span": horizontal_span,
        "neck_width": neck_width,
        "checks": checks,
        "failed_checks": failed_checks,
        "reason": ",".join(failed_checks) if failed_checks else None,
    }



def _mask_pixel_record(mask: np.ndarray) -> dict:
    mask = np.asarray(mask, dtype=bool)
    pixels = int(mask.sum())
    if not pixels:
        return {"visible": False, "pixels": 0, "bbox": None, "components": 0, "boundary_pixels": 0}
    ys, xs = np.where(mask)
    component_count, _, _, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    boundary = cv2.morphologyEx(
        mask.astype(np.uint8),
        cv2.MORPH_GRADIENT,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    ) > 0
    return {
        "visible": True,
        "pixels": pixels,
        "bbox": {"x": int(xs.min()), "y": int(ys.min()), "width": int(xs.max() - xs.min() + 1), "height": int(ys.max() - ys.min() + 1)},
        "components": int(component_count - 1),
        "boundary_pixels": int(boundary.sum()),
    }


def _pixel_feature_inventory(
    crop: Image.Image,
    semantic_labels: np.ndarray,
    parser_mode: str,
    hard: np.ndarray,
    hair: np.ndarray,
    neck: np.ndarray,
    mesh_points: np.ndarray | None,
) -> dict:
    rgb = np.asarray(crop.convert("RGB"), dtype=np.uint8)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if parser_mode == "parsenet-anime-fallback":
        definitions = {
            "face_skin": (1,), "nose": (2,), "eyeglasses": (3,),
            "left_eye": (4,), "right_eye": (5,), "left_eyebrow": (6,), "right_eyebrow": (7,),
            "left_ear": (8,), "right_ear": (9,), "mouth_cavity": (10,),
            "upper_lip": (11,), "lower_lip": (12,), "hair": (13,), "headwear": (14,),
            "earrings": (15,), "necklace": (16,), "neck": (17,), "clothing": (18,),
        }
    else:
        definitions = {
            "background": (0,), "hair": (1,), "body_skin": (2,),
            "face_skin": (3,), "clothing": (4,), "accessory_or_other": (5,),
        }
    features = {
        name: _mask_pixel_record(np.isin(semantic_labels, ids))
        for name, ids in definitions.items()
    }
    features["exact_editable_exposed_skin"] = _mask_pixel_record(hard)
    features["protected_hair_headwear_accessory_clothing"] = _mask_pixel_record(hair)
    features["connected_neck_skin"] = _mask_pixel_record(neck)
    if parser_mode == "parsenet-anime-fallback":
        eye_mask = np.isin(semantic_labels, (4, 5))
        eye_socket = cv2.dilate(
            eye_mask.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 9)),
            iterations=1,
        ).astype(bool) & ~eye_mask & hard
        mouth = np.isin(semantic_labels, (10, 11, 12))
        teeth = mouth & (gray >= 172) & (hsv[..., 1] <= 92)
        features["eye_socket"] = _mask_pixel_record(eye_socket)
        features["teeth_candidate"] = _mask_pixel_record(teeth)

    skin = hard.astype(bool)
    skin_values = lab[skin]
    appearance = {"available": bool(len(skin_values))}
    if len(skin_values):
        median = np.median(skin_values, axis=0)
        delta = np.linalg.norm(lab - median[None, None, :], axis=2)
        edge = cv2.Canny(gray, 38, 112) > 0
        detail = skin & (edge | (lab[..., 0] < float(np.percentile(skin_values[:, 0], 18))))
        nonuniform = skin & (delta > max(24.0, float(np.percentile(delta[skin], 94))))
        cols = np.indices(skin.shape)[1]
        center_x = float(np.median(np.where(skin)[1]))
        left_l = lab[..., 0][skin & (cols <= center_x)]
        right_l = lab[..., 0][skin & (cols > center_x)]
        left_med = float(np.median(left_l)) if len(left_l) else 0.0
        right_med = float(np.median(right_l)) if len(right_l) else 0.0
        appearance = {
            "available": True,
            "complexion_lab_median": [round(float(v), 3) for v in median],
            "lightness_p10_p50_p90": [round(float(v), 3) for v in np.percentile(skin_values[:, 0], (10, 50, 90))],
            "pigmentation_delta_e_p50_p90_p98": [round(float(v), 3) for v in np.percentile(delta[skin], (50, 90, 98))],
            "potential_discoloration_or_scar_pixels": int(nonuniform.sum()),
            "facial_ink_edge_and_beard_candidate_pixels": int(detail.sum()),
            "lighting_left_lab_l": round(left_med, 3),
            "lighting_right_lab_l": round(right_med, 3),
            "lighting_direction": "left-brighter" if left_med > right_med + 3 else "right-brighter" if right_med > left_med + 3 else "balanced",
        }

    small = crop.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    quantized = small.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    colors = quantized.getcolors(maxcolors=4096) or []
    palette = quantized.getpalette() or []
    dominant = []
    for count, index in sorted(colors, reverse=True)[:5]:
        offset = int(index) * 3
        dominant.append({"rgb": palette[offset:offset + 3], "fraction": round(float(count / 4096.0), 4)})
    scene = {
        "brightness_median": round(float(np.median(lab[..., 0])), 3),
        "contrast_p10_p90": round(float(np.percentile(lab[..., 0], 90) - np.percentile(lab[..., 0], 10)), 3),
        "saturation_median": round(float(np.median(hsv[..., 1])), 3),
        "edge_density": round(float(np.mean(cv2.Canny(gray, 45, 125) > 0)), 6),
        "dominant_palette": dominant,
        "note": "Measured scene/theme/light/style signals; no unsupported semantic scene guess.",
    }
    geometry = _face_geometry_reads(mesh_points) if mesh_points is not None else {}
    if mesh_points is not None:
        mouth_width = max(1.0, float(np.linalg.norm(mesh_points[291] - mesh_points[61])))
        geometry["mouth_corner_tilt"] = round(float((mesh_points[291][1] - mesh_points[61][1]) / mouth_width), 4)
    warnings = [{
        "code": "BODY_HAND_POSE_ANALYZER_NOT_IN_FACE_LANE",
        "severity": "warning",
        "message": "Hands, full-body posture, and body skin are not silently inferred by the face lane; route them to a licensed pose/hand/body analyzer when visible-skin replacement outside the head is requested.",
    }]
    return {
        "version": 1,
        "pixel_coordinate_space": {"width": int(crop.width), "height": int(crop.height), "zoom_basis": "native 512 crop with exact masks"},
        "features": features,
        "appearance": appearance,
        "geometry_expression_pose": geometry,
        "scene_theme_light": scene,
        "warnings": warnings,
    }


def _build_upload_analysis(
    *,
    detection_score: float,
    detected_faces: int,
    crop: Image.Image,
    mesh_points: np.ndarray | None,
    semantic_labels: np.ndarray,
    semantic_parser: dict,
    hard_mask: Image.Image,
    hair_exclusion: Image.Image,
    neck_anchor: Image.Image,
    identity_mesh: dict | None,
) -> dict:
    """Summarize what the belt knows about the immutable upload before GPU work."""
    absent_accessories = list(semantic_parser.get("preset_absent_accessories") or [])
    accessory_corrections = dict(
        semantic_parser.get("preset_absent_accessory_corrections") or {}
    )
    accessory_reclassified = dict(
        semantic_parser.get("preset_absent_accessory_reclassified_as_hair") or {}
    )
    residual_absent = dict(
        semantic_parser.get("residual_absent_accessory_pixels_in_geometric_face") or {}
    )
    hard = np.asarray(hard_mask.convert("L")) > 127
    hair = np.asarray(hair_exclusion.convert("L")) > 127
    neck = np.asarray(neck_anchor.convert("L")) > 127
    head_contour = dict(semantic_parser.get("head_contour") or {})
    traversal = dict(head_contour.get("body_part_traversal") or {})
    hard_pixels = int(np.count_nonzero(hard))
    hair_pixels = int(np.count_nonzero(hair))
    neck_pixels = int(np.count_nonzero(neck))
    protected_overlap = int(np.count_nonzero(hard & hair))
    overlap_ratio = float(protected_overlap / max(1, hard_pixels))

    accessories: dict[str, int] = {}
    if semantic_parser.get("mode") == "parsenet-anime-fallback":
        accessory_ids = {
            "eyeglasses": 3,
            "hair": 13,
            "headwear": 14,
            "earrings": 15,
            "necklaces": 16,
            "clothing": 18,
        }
        accessories = {
            name: int(np.count_nonzero(semantic_labels == label))
            for name, label in accessory_ids.items()
        }
    else:
        accessories = {
            "hair": hair_pixels,
            "headwear": 0,
            "eyeglasses": 0,
            "earrings": 0,
            "necklaces": 0,
            "clothing": 0,
        }

    mesh = dict(identity_mesh or {})
    eye_warps = dict(mesh.get("eye_feature_warps") or {})
    visible_eyes = sum(
        1 for result in eye_warps.values()
        if result.get("applied") or result.get("reason") == "target-material-preserved"
    )
    pixel_inventory = _pixel_feature_inventory(
        crop,
        semantic_labels,
        str(semantic_parser.get("mode") or "unknown"),
        hard,
        hair,
        neck,
        mesh_points,
    )
    minimum_identity_whole_coverage = (
        0.12
        if mesh.get("mesh_geometry_fit_mode") == "target-landmarks-core"
        else 0.20
    )
    stages = [
        {
            "id": "face-detection-and-478-point-mesh",
            "passed": bool(
                detected_faces >= 1
                and detection_score >= 0.30
                and mesh_points is not None
                and len(mesh_points) == 478
            ),
            "detected_faces": int(detected_faces),
            "detection_score": round(float(detection_score), 6),
            "mesh_points": int(len(mesh_points)) if mesh_points is not None else 0,
        },
        {
            "id": "neck-anchor",
            "passed": bool(semantic_parser.get("neck_visible") and neck_pixels >= 8),
            "pixels": neck_pixels,
        },
        {
            "id": "neck-left-to-top-to-right-to-neck-closed-loop",
            "passed": bool(traversal.get("passed") and traversal.get("closed")),
            "traversal": traversal,
        },
        {
            "id": "whole-face-head-and-ears",
            "passed": bool(
                hard_pixels >= 256
                and int(head_contour.get("head_pixels", 0)) >= 256
                and int(head_contour.get("envelope_pixels", 0)) >= hard_pixels
            ),
            "editable_pixels": hard_pixels,
            "head_pixels": int(head_contour.get("head_pixels", 0)),
            "envelope_pixels": int(head_contour.get("envelope_pixels", 0)),
        },
        {
            "id": "hair-headwear-accessory-and-clothing-classification",
            "passed": bool(
                semantic_labels.shape == hard.shape
                and overlap_ratio <= 0.01
                and all(int(pixels) == 0 for pixels in residual_absent.values())
            ),
            "protected_pixels": hair_pixels,
            "protected_overlap_pixels": protected_overlap,
            "protected_overlap_ratio": round(overlap_ratio, 6),
            "classes": accessories,
            "preset_absent_accessories": absent_accessories,
            "preset_reclassified_as_hair_pixels": accessory_reclassified,
            "preset_correction_pixels": accessory_corrections,
            "residual_absent_accessory_pixels_in_geometric_face": residual_absent,
        },
        {
            "id": "visible-eyes-mouth-and-identity-pose-map",
            "passed": bool(
                mesh
                and int(mesh.get("triangles", 0)) >= 100
                and float(mesh.get("coverage_ratio", 0.0)) >= minimum_identity_whole_coverage
                and float(mesh.get("core_coverage_ratio", 0.0)) >= 0.55
                and visible_eyes >= 1
                and int(mesh.get("feature_fill_triangles", 0)) > 0
            ),
            "visible_identity_eyes": visible_eyes,
            "eye_results": eye_warps,
            "mouth_fill_triangles": int(mesh.get("feature_fill_triangles", 0)),
            "mesh_triangles": int(mesh.get("triangles", 0)),
            "mesh_coverage": float(mesh.get("coverage_ratio", 0.0)),
            "minimum_mesh_coverage": minimum_identity_whole_coverage,
            "facial_core_coverage": float(mesh.get("core_coverage_ratio", 0.0)),
        },
        {
            "id": "target-theme-overlay-ready",
            "passed": bool(mesh.get("target_theme_overlay")),
            "overlay": mesh.get("target_theme_overlay"),
        },
    ]
    return {
        "version": 1,
        "purpose": "understand-and-audit-immutable-upload-before-generation",
        "ordered_pipeline": [stage["id"] for stage in stages],
        "all_passed": all(bool(stage["passed"]) for stage in stages),
        "stages": stages,
        "pixel_feature_inventory": pixel_inventory,
        "acceptance_contract": {
            "editable_skin_zone": pixel_inventory["features"]["exact_editable_exposed_skin"],
            "target_feature_lock": {
                "eyes": pixel_inventory["features"].get("left_eye"),
                "mouth": pixel_inventory["features"].get("mouth_cavity"),
                "nose": pixel_inventory["features"].get("nose"),
                "brows": {
                    "left": pixel_inventory["features"].get("left_eyebrow"),
                    "right": pixel_inventory["features"].get("right_eyebrow"),
                },
                "ears": {
                    "left": pixel_inventory["features"].get("left_ear"),
                    "right": pixel_inventory["features"].get("right_ear"),
                },
                "neck": pixel_inventory["features"].get("connected_neck_skin"),
            },
            "warnings": pixel_inventory["warnings"],
        },
    }
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
    eye_region = np.maximum(np.asarray(left_eye), np.asarray(right_eye)) > 127
    mouth_region = np.asarray(
        _feature_mask(mesh_points, topology.get("lips"), padding=4)
    ) > 127

    rgb = np.asarray(crop.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    edges = cv2.Canny(gray, 38, 112) > 0
    mouth_edges = cv2.dilate(
        edges.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    ) > 0
    eye_edges = mouth_edges
    # Target eye geometry/linework stays; target pale eye-area skin does not.
    eyes = eye_region & (eye_edges | (gray < 92))
    mouth_width = float(np.linalg.norm(mesh_points[291] - mesh_points[61]))
    mouth_gap = float(np.linalg.norm(mesh_points[14] - mesh_points[13]))
    mouth_open_ratio = mouth_gap / max(1.0, mouth_width)
    teeth = mouth_region & (gray >= 172) & (hsv[..., 1] <= 92)
    inner_mouth = mouth_region & (gray < 76)
    # Closed lips are wholly Carey identity warped through target geometry.
    # Only an open target contributes cavity/teeth material.
    mouth = (teeth | inner_mouth) if mouth_open_ratio >= 0.045 else np.zeros_like(mouth_region)
    dark_edges = edges & (gray < 112)
    ink = cv2.dilate(
        dark_edges.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    ) > 0
    ink &= hard

    # Target eyes, mouth, brows, nose and ear ink are character material, but
    # the lower-face/jaw ink belongs to identity. Do not paste the target jaw
    # or target beard back over Carey's warped lower face.
    face_oval = np.asarray(
        _feature_mask(mesh_points, topology.get("face_oval"), padding=0)
    ) > 127
    lips_y, _ = np.where(mouth_region)
    jaw_identity_region = np.zeros(hard.shape, dtype=bool)
    if len(lips_y):
        mouth_floor = int(np.percentile(lips_y, 55))
        row_grid = np.arange(hard.shape[0], dtype=np.int32)[:, None]
        jaw_identity_region = face_oval & (row_grid >= mouth_floor)
    jaw_ink_removed = int(np.count_nonzero(ink & jaw_identity_region))
    ink &= ~jaw_identity_region

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
            "eye_fill_policy": "carey-eye-fill-in-target-geometry; target-linework-only",
            "mouth_teeth_pixels": int(np.count_nonzero(mouth)),
            "mouth_region_pixels": int(np.count_nonzero(mouth_region & hard)),
            "mouth_open_ratio": round(float(mouth_open_ratio), 6),
            "mouth_fill_policy": "carey-mouth-fill-in-target-geometry; target-cavity-and-teeth-only-when-open",
            "face_ink_pixels": int(np.count_nonzero(ink)),
            "combined_pixels": int(np.count_nonzero(combined)),
            "target_jaw_ink_removed_pixels": jaw_ink_removed,
            "jaw_owner": "carey-identity-seed",
            "hair_headwear": "locked by independent subtraction outside edit zone",
        },
    )

def _identity_beard_detail_mask(
    identity_seed: Image.Image,
    hard_mask: Image.Image,
    crop_mesh: np.ndarray,
    topology: dict[str, np.ndarray],
) -> tuple[Image.Image, dict]:
    """Extract Carey's warped jawline beard/goatee as a post-GPU detail lock."""
    hard = np.asarray(hard_mask.convert("L")) > 127
    face_oval = np.asarray(
        _feature_mask(crop_mesh, topology.get("face_oval"), padding=0)
    ) > 127
    lips = np.asarray(_feature_mask(crop_mesh, topology.get("lips"), padding=1)) > 127
    lip_y, _ = np.where(lips)
    if not len(lip_y):
        empty = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
        return empty, {"applied": False, "reason": "missing-lip-geometry", "pixels": 0}

    mouth_floor = int(np.percentile(lip_y, 60))
    rows = np.arange(CANVAS_SIZE, dtype=np.int32)[:, None]
    mouth_safety = cv2.dilate(
        lips.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 13)),
        iterations=1,
    ) > 0
    beard_interior = cv2.erode(
        (hard & face_oval).astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)),
        iterations=1,
    ) > 0
    lower_face = beard_interior & (rows >= mouth_floor + 5) & ~mouth_safety
    rgb = np.asarray(identity_seed.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    values = gray[lower_face]
    if len(values) < 64:
        empty = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
        return empty, {"applied": False, "reason": "lower-face-region-too-small", "pixels": 0}

    cutoff = min(float(np.percentile(values, 38)), float(np.median(values) - 12.0), 118.0)
    dark = gray <= cutoff
    edges = cv2.Canny(gray, 34, 104) > 0
    edges = cv2.dilate(
        edges.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    ) > 0
    beard = lower_face & (dark | (edges & (gray <= cutoff + 18.0)))
    beard = cv2.morphologyEx(
        beard.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    ) > 0
    soft = cv2.GaussianBlur(beard.astype(np.float32), (0, 0), 0.70)
    soft = np.clip(soft * hard.astype(np.float32), 0.0, 1.0)
    return Image.fromarray(np.uint8(np.round(soft * 255)), mode="L"), {
        "applied": bool(np.any(beard)),
        "pixels": int(np.count_nonzero(beard)),
        "gray_cutoff": round(cutoff, 3),
        "source": "warped-carey-identity-seed",
        "region": "lower-face-jawline-and-goatee",
        "mouth_safety_pixels": int(np.count_nonzero(mouth_safety & hard)),
        "outer_jaw_safety_pixels": int(np.count_nonzero((hard & face_oval) & ~beard_interior)),
        "mouth_safety_rule": "beard-detail-never-touches-lips-mouth-interior-teeth-or-expression-linework",
    }


def _warp_ring_fan(    source: np.ndarray,
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
            applied = _warp_triangle(
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
            if applied:
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


def _fit_target_mesh_jaw_to_semantic_outline(
    target_points: np.ndarray,
    topology: dict[str, np.ndarray],
    hard_mask: Image.Image,
    neck_mask: Image.Image,
) -> tuple[np.ndarray, dict]:
    """Expand extreme stylized meshes to the approved jaw-to-jaw face plane.

    MediaPipe can place a valid 478-point grid *inside* an oversized anime
    face. The semantic mask knows the actual exposed-skin silhouette, so sample
    its cheek/jaw widths while excluding the neck. Normal heads remain
    unchanged; only a large measured mismatch activates the bounded fit.
    """
    rings = _ordered_rings(map(tuple, topology.get("face_oval", ())))
    if not rings:
        return target_points.copy(), {
            "applied": False,
            "reason": "missing-face-oval-topology",
        }
    ring_indices = max(rings, key=len)
    if max(ring_indices) >= len(target_points):
        return target_points.copy(), {
            "applied": False,
            "reason": "face-oval-landmark-range",
        }

    face_oval = target_points[np.asarray(ring_indices, dtype=np.int32)]
    mesh_width = float(np.ptp(face_oval[:, 0]))
    mesh_height = float(np.ptp(face_oval[:, 1]))
    if mesh_width < 24.0 or mesh_height < 24.0:
        return target_points.copy(), {
            "applied": False,
            "reason": "unsafe-face-oval-size",
        }

    hard = np.asarray(hard_mask.convert("L")) > 127
    neck = np.asarray(neck_mask.convert("L")) > 127
    top = float(face_oval[:, 1].min())
    widths: list[float] = []
    centers: list[float] = []
    sampled_rows: list[int] = []
    for fraction in np.linspace(0.35, 0.82, 16):
        row = int(round(top + mesh_height * float(fraction)))
        if row < 0 or row >= hard.shape[0]:
            continue
        columns = np.where(hard[row] & ~neck[row])[0]
        if len(columns) < 16:
            continue
        width = float(np.ptp(columns))
        if width < mesh_width * 0.85 or width > mesh_width * 2.20:
            continue
        widths.append(width)
        centers.append(float((columns.min() + columns.max()) / 2.0))
        sampled_rows.append(row)

    if len(widths) < 5:
        return target_points.copy(), {
            "applied": False,
            "reason": "insufficient-semantic-jaw-rows",
            "sampled_rows": len(widths),
        }

    semantic_width = float(np.median(widths))
    raw_ratio = semantic_width / max(1.0, mesh_width)
    base = {
        "fit_basis": "semantic-hard-minus-neck-row-median",
        "mesh_jaw_width": round(mesh_width, 6),
        "semantic_jaw_width": round(semantic_width, 6),
        "raw_jaw_ratio": round(raw_ratio, 6),
        "sampled_rows": sampled_rows,
    }
    if raw_ratio <= 1.18:
        return target_points.copy(), {
            **base,
            "applied": False,
            "reason": "mesh-already-fills-semantic-face",
            "scale_x": 1.0,
            "scale_y": 1.0,
            "center_shift_x": 0.0,
        }

    # Bound the fit so an extreme anime forehead/hairline (V-shaped DBZ hair,
    # Bleach pompadour, etc.) still gets covered.  Previous 1.35 cap left the
    # mesh inside the parser-detected face oval, which on Vegeta was only
    # ~75% of the visually rendered face.
    scale_x = float(np.clip(raw_ratio, 1.0, 1.85))
    scale_y = float(min(1.25, 1.0 + (scale_x - 1.0) * 0.55))
    mesh_center_x = float(face_oval[:, 0].mean())
    mesh_center_y = float(face_oval[:, 1].mean())
    semantic_center_x = float(np.median(centers))
    center_shift_x = float(np.clip(semantic_center_x - mesh_center_x, -32.0, 32.0))

    fitted = target_points.astype(np.float32).copy()
    fitted[:, 0] = (
        mesh_center_x + center_shift_x
        + (fitted[:, 0] - mesh_center_x) * scale_x
    )
    fitted[:, 1] = (
        mesh_center_y + (fitted[:, 1] - mesh_center_y) * scale_y
    )
    for axis in (0, 1):
        lower = float(fitted[:, axis].min())
        upper = float(fitted[:, axis].max())
        if lower < 1.0:
            fitted[:, axis] += 1.0 - lower
        upper = float(fitted[:, axis].max())
        if upper > CANVAS_SIZE - 2:
            fitted[:, axis] -= upper - (CANVAS_SIZE - 2)

    fitted_oval = fitted[np.asarray(ring_indices, dtype=np.int32)]
    return fitted, {
        **base,
        "applied": True,
        "scale_x": round(scale_x, 6),
        "scale_y": round(scale_y, 6),
        "center_shift_x": round(center_shift_x, 6),
        "fitted_jaw_width": round(float(np.ptp(fitted_oval[:, 0])), 6),
        "rule": "fit Carey jaw-to-jaw to the semantic face width, then warp features on the bounded 478-point grid",
    }


def _soften_identity_seed_nose(
    identity_seed: Image.Image,
    target_mesh: np.ndarray,
    crop_box: tuple[int, int, int, int],
    topology: dict[str, np.ndarray],
    target_crop: Image.Image | None = None,
) -> tuple[Image.Image, dict]:
    """Reduce high-frequency canny input in the nose region of the identity seed.

    The warped identity seed carries Carey's full 3D-rendered nose into the
    target's face grid.  When v3 ControlNet CANNY extracts edges from that seed,
    the high-frequency cel-shading of Carey's nose ridge is read as a strong
    edge and the GPU redraws it as a long, sculpted photoreal-looking nose
    instead of the flat anime line the target artwork has.

    Fix: build a nose-region mask from MediaPipe landmarks 1, 2, 4-6 and the
    168-197 outer nose ring, bilateral-filter the seed within that mask with
    a heavy sigma so the cel-shading edges are smoothed while the broad nose
    shape is preserved, then blend.  The canny now reads a soft nose outline
    and the GPU draws flat anime shading.  Carey's identity survives the GPU
    pass via the complexion attack and the identity detail lock; only the
    high-frequency nose edges are removed.
    """
    nose_indices = set()
    nose_indices.update([1, 2, 4, 5, 6])
    nose_indices.update(range(168, 198))
    nose_topology = topology.get("nose")
    if nose_topology is not None and len(nose_topology) > 0:
        for edge in nose_topology:
            nose_indices.update(int(v) for v in edge)
    valid_indices = sorted(i for i in nose_indices if 0 <= i < len(target_mesh))
    if len(valid_indices) < 6:
        return identity_seed, {
            "applied": False,
            "reason": "insufficient-nose-landmarks",
            "landmarks": len(valid_indices),
        }

    crop_left, crop_top, crop_right, crop_bottom = crop_box
    scale_x = CANVAS_SIZE / (crop_right - crop_left)
    scale_y = CANVAS_SIZE / (crop_bottom - crop_top)
    canvas_mesh = target_mesh.copy().astype(np.float32)
    canvas_mesh[:, 0] = (canvas_mesh[:, 0] - crop_left) * scale_x
    canvas_mesh[:, 1] = (canvas_mesh[:, 1] - crop_top) * scale_y

    nose_points = canvas_mesh[valid_indices]
    hull = cv2.convexHull(np.int32(nose_points))
    hull_mask = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.float32)
    cv2.fillConvexPoly(hull_mask, hull, 1.0)
    # Generous dilation to cover the full nose + adjacent shading region
    hull_mask = cv2.dilate(
        hull_mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)),
        iterations=1,
    )
    feathered = cv2.GaussianBlur(hull_mask, (0, 0), sigmaX=5.0)
    feathered = np.clip(feathered, 0.0, 1.0)

    seed_rgb = np.asarray(identity_seed.convert("RGB"), dtype=np.float32)
    seed_u8 = np.uint8(np.clip(seed_rgb, 0, 255))
    # Aggressive bilateral: high sigmaColor smooths cel-shading edges,
    # high d averages over a wide neighborhood for natural face planes
    bilateral = cv2.bilateralFilter(seed_u8, d=11, sigmaColor=85, sigmaSpace=14)
    feather3 = feathered[..., None]
    softened = seed_rgb * (1.0 - feather3) + bilateral.astype(np.float32) * feather3

    return Image.fromarray(np.uint8(np.clip(softened, 0, 255)), mode="RGB"), {
        "applied": True,
        "landmarks": len(valid_indices),
        "nose_mask_area_pixels": int(np.count_nonzero(feathered > 0.5)),
        "feather_radius_px": 5.0,
        "bilateral_d": 11,
        "bilateral_sigma_color": 85,
        "bilateral_sigma_space": 14,
        "rule": "aggressive bilateral-filter nose region so CANNY reads soft anime nose line",
    }


def _build_identity_mesh_seed(
    root: Path,
    crop: Image.Image,
    crop_box: tuple[int, int, int, int],
    target_mesh: np.ndarray,
    topology: dict[str, np.ndarray],
    hard_mask: Image.Image,
    neck_mask: Image.Image,
    preserve_feature_mask: Image.Image,
    uncovered_skin_mask: Image.Image,
    identity_reference: Path,
    mesh_identity_strength_override: float | None = None,
    eye_source_mode: str = "identity",
    mesh_geometry_fit_mode: str = "semantic-outline",
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
    mesh_geometry_fit_mode = str(mesh_geometry_fit_mode).strip().lower()
    if mesh_geometry_fit_mode == "semantic-outline":
        target_crop_mesh, semantic_geometry_fit = _fit_target_mesh_jaw_to_semantic_outline(
            target_crop_mesh, topology, hard_mask, neck_mask
        )
    elif mesh_geometry_fit_mode in {"target-landmarks", "target-landmarks-core"}:
        semantic_geometry_fit = {
            "applied": False,
            "reason": "preset-keeps-target-landmark-feature-skeleton",
            "scale_x": 1.0,
            "scale_y": 1.0,
            "center_shift_x": 0.0,
            "rule": (
                "target landmarks own eyes/nose/mouth placement; semantic outline "
                "owns full head complexion and GPU edit authority"
            ),
        }
    else:
        raise RuntimeError(
            "Unsupported identity mesh geometry fit mode: "
            f"{mesh_geometry_fit_mode}"
        )
    source_array, source_accessory_cleanup = _remove_source_accessories(
        root, source_image, source_mesh
    )
    target_array = np.asarray(crop, dtype=np.float32).copy()
    warped_only = np.zeros_like(target_array)
    coverage = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.float32)
    triangle_count = 0
    skipped_triangle_count = 0
    for triangle in _mesh_triangles(topology):
        if max(triangle) >= len(source_mesh):
            continue
        applied = _warp_triangle(
            source_array,
            warped_only,
            coverage,
            source_mesh[np.asarray(triangle)],
            target_crop_mesh[np.asarray(triangle)],
        )
        if applied:
            triangle_count += 1
        else:
            skipped_triangle_count += 1

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

    mesh_hull = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.uint8)
    cv2.fillConvexPoly(
        mesh_hull,
        cv2.convexHull(np.int32(np.round(target_crop_mesh))),
        1,
    )
    core_eligible = (
        (mesh_hull > 0)
        & (allowed > 0.5)
        & (hidden_eye_suppression < 0.25)
        & (preserve < 0.25)
    )
    core_pixels = max(1, int(np.count_nonzero(core_eligible)))
    core_coverage_ratio = float(np.count_nonzero(covered & core_eligible) / core_pixels)
    if core_coverage_ratio < 0.55:
        raise RuntimeError(
            "Identity mesh facial-core coverage is unsafe "
            f"({core_coverage_ratio:.1%}; minimum 55%)."
        )
    minimum_whole_zone_coverage = (
        0.12 if mesh_geometry_fit_mode == "target-landmarks-core" else 0.20
    )
    if triangle_count < 100 or coverage_ratio < minimum_whole_zone_coverage:
        raise RuntimeError(
            f"Identity mesh warp coverage is unsafe ({triangle_count} triangles, "
            f"{coverage_ratio:.1%} of edit zone; minimum "
            f"{minimum_whole_zone_coverage:.0%})."
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
        "skipped_degenerate_triangles": skipped_triangle_count,
        "feature_fill_triangles": feature_triangle_count,
        "eye_feature_warps": eye_feature_warps,
        "eye_source_mode": eye_source_mode,
        "hidden_eye_suppression_pixels": int(
            np.count_nonzero((hidden_eye_suppression > 0.25) & (allowed > 0.5))
        ),
        "coverage_ratio": round(coverage_ratio, 6),
        "core_coverage_ratio": round(core_coverage_ratio, 6),
        "core_eligible_pixels": core_pixels,
        "semantic_geometry_fit": semantic_geometry_fit,
        "mesh_geometry_fit_mode": mesh_geometry_fit_mode,
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
    mesh_geometry_fit_mode: str = "semantic-outline",
    eye_protection_strength: float = 0.55,
    eye_source_mode: str = "identity",
    absent_accessories: Iterable[str] = (),
    manual_box: tuple[float, float, float, float] | None = None,
    exclude_boxes: Iterable[tuple[float, float, float, float]] = (),
    _crop_attempt: int = 0,
    _crop_shift_y: int = 0,
) -> dict:
    eye_source_mode = str(eye_source_mode).strip().lower()
    absent_accessories = tuple(absent_accessories)
    exclude_boxes = tuple(exclude_boxes)
    _crop_attempt = max(0, int(_crop_attempt))
    _crop_shift_y = int(_crop_shift_y)
    if eye_source_mode not in {"identity", "target"}:
        raise RuntimeError(f"Unsupported eye source mode: {eye_source_mode}")
    eye_protection_strength = max(0.0, min(1.0, float(eye_protection_strength)))
    lock_target_features = (
        eye_source_mode == "target" and eye_protection_strength > 0.0
    )
    root, source = root.resolve(), source.resolve()
    if not source.is_file():
        raise RuntimeError(f"Uploaded target does not exist: {source}")
    for generated_root in (
        # artifacts/_sources contains immutable uploads and is valid input.
        root / "artifacts" / "careyrpg",
        root / "artifacts" / "sandbox",
        root / "artifacts" / "byrdhouse",
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
    unshifted_crop_box = _square_crop_box(crop_extent, original.size, crop_factor)
    crop_left, crop_top, crop_right, crop_bottom = unshifted_crop_box
    crop_side = crop_right - crop_left
    shifted_top = max(
        0,
        min(original.height - crop_side, crop_top + _crop_shift_y),
    )
    crop_box = (crop_left, shifted_top, crop_right, shifted_top + crop_side)
    applied_crop_shift_y = shifted_top - crop_top
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
    ) = _semantic_head_zone(
        root,
        crop,
        geometric_face,
        absent_accessories=absent_accessories,
    )
    head_boundary = np.asarray(head_envelope.convert("L")) > 127
    preflight_skin_ids = (
        (1, 2, 8, 9, 17)
        if semantic_parser["mode"] == "parsenet-anime-fallback"
        else (2, 3)
    )
    semantic_skin_boundary = np.isin(semantic_labels, preflight_skin_ids)
    preflight_boundary = head_boundary | semantic_skin_boundary
    crop_left, crop_top, crop_right, crop_bottom = crop_box
    source_width, source_height = original.size
    edge_band = max(1, CANVAS_SIZE // 128)
    boundary_contacts: list[str] = []
    semantic_skin_boundary_contacts: list[str] = []
    if np.any(preflight_boundary[:edge_band, :]):
        boundary_contacts.append("top")
    if np.any(preflight_boundary[-edge_band:, :]):
        boundary_contacts.append("bottom")
    if np.any(preflight_boundary[:, :edge_band]):
        boundary_contacts.append("left")
    if np.any(preflight_boundary[:, -edge_band:]):
        boundary_contacts.append("right")
    if np.any(semantic_skin_boundary[:edge_band, :]):
        semantic_skin_boundary_contacts.append("top")
    if np.any(semantic_skin_boundary[-edge_band:, :]):
        semantic_skin_boundary_contacts.append("bottom")
    if np.any(semantic_skin_boundary[:, :edge_band]):
        semantic_skin_boundary_contacts.append("left")
    if np.any(semantic_skin_boundary[:, -edge_band:]):
        semantic_skin_boundary_contacts.append("right")
    expandable_contacts = [
        edge
        for edge in boundary_contacts
        if (
            (edge == "top" and crop_top > 0)
            or (edge == "bottom" and crop_bottom < source_height)
            or (edge == "left" and crop_left > 0)
            or (edge == "right" and crop_right < source_width)
        )
    ]
    if expandable_contacts:
        # A square crop can have ample collar/shoulder space below while an
        # extreme anime forehead or hairline is clipped above.  When exposed
        # skin itself touches the top edge and the audited head/neck envelope
        # has bottom clearance, translate the same square upward before making
        # it larger.  This keeps pixels concentrated on the face and prevents
        # Vegeta-like widow's peaks from losing their upper skin/hair outline.
        if (
            "top" in semantic_skin_boundary_contacts
            and "bottom" not in boundary_contacts
            and crop_top > 0
            and _crop_attempt < 2
        ):
            audited_content = (
                preflight_boundary
                | (np.asarray(neck_anchor.convert("L")) > 127)
            )
            content_rows = np.where(audited_content)[0]
            if len(content_rows):
                desired_top_margin = max(16, int(round(CANVAS_SIZE * 0.12)))
                required_bottom_margin = max(10, int(round(CANVAS_SIZE * 0.04)))
                bottom_clearance = CANVAS_SIZE - 1 - int(content_rows.max())
                transferable_canvas = min(
                    desired_top_margin,
                    max(0, bottom_clearance - required_bottom_margin),
                )
                shift_up = min(
                    crop_top,
                    int(math.ceil(
                        transferable_canvas * (crop_right - crop_left) / CANVAS_SIZE
                    )),
                )
                if shift_up > 0:
                    return prepare_face_zone(
                        root,
                        source,
                        job_id,
                        min_confidence=min_confidence,
                        crop_factor=crop_factor,
                        face_index=face_index,
                        zone_expand=zone_expand,
                        identity_reference=identity_reference,
                        mesh_identity_strength=mesh_identity_strength,
                        mesh_geometry_fit_mode=mesh_geometry_fit_mode,
                        eye_protection_strength=eye_protection_strength,
                        eye_source_mode=eye_source_mode,
                        absent_accessories=absent_accessories,
                        manual_box=manual_box,
                        exclude_boxes=exclude_boxes,
                        _crop_attempt=_crop_attempt + 1,
                        _crop_shift_y=_crop_shift_y - shift_up,
                    )
        if _crop_attempt >= 2:
            raise RuntimeError(
                "CPU head/neck analysis still touches expandable crop edge(s) "
                f"{', '.join(expandable_contacts)} after {_crop_attempt} reroutes; "
                "GPU work was stopped for manual review."
            )
        return prepare_face_zone(
            root,
            source,
            job_id,
            min_confidence=min_confidence,
            crop_factor=min(4.0, float(crop_factor) * 1.35),
            face_index=face_index,
            zone_expand=zone_expand,
            identity_reference=identity_reference,
            mesh_identity_strength=mesh_identity_strength,
            mesh_geometry_fit_mode=mesh_geometry_fit_mode,
            eye_protection_strength=eye_protection_strength,
            eye_source_mode=eye_source_mode,
            absent_accessories=absent_accessories,
            manual_box=manual_box,
            exclude_boxes=exclude_boxes,
            _crop_attempt=_crop_attempt + 1,
            _crop_shift_y=_crop_shift_y,
        )
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
        protected = np.asarray(hair_exclusion) >= 64
        fringe_mesh = _transform_points(mesh_points, crop_box) if mesh_points is not None else None
        lower_jaw_corridor = np.zeros(hard_before_fringe.shape, dtype=bool)
        if fringe_mesh is not None:
            oval = np.asarray(_feature_mask(fringe_mesh, topology.get("face_oval"), padding=10)) > 127
            lips = np.asarray(_feature_mask(fringe_mesh, topology.get("lips"), padding=2)) > 127
            lip_rows, _ = np.where(lips)
            if len(lip_rows):
                row_grid = np.arange(CANVAS_SIZE, dtype=np.int32)[:, None]
                lower_jaw_corridor = oval & (row_grid >= int(np.percentile(lip_rows, 55)))
        mislabeled_skin_edge = np.isin(semantic_labels, (0, 18)) & lower_jaw_corridor
        skin_edge_fringe = (
            ring
            & (light_delta < 52.0)
            & (chroma_delta < 30.0)
            & (~protected | mislabeled_skin_edge)
        )
        semantic_parser["lower_jaw_skin_fringe_pixels"] = int(
            np.count_nonzero(skin_edge_fringe & protected)
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
    if lock_target_features:
        preserve_feature_mask = Image.fromarray(
            np.uint8(
                np.round(
                    np.asarray(preserve_feature_mask, dtype=np.float32)
                    * eye_protection_strength
                )
            ),
            mode="L",
        )
        protected_color_features = preserve_feature_mask.copy()
    else:
        preserve_feature_mask = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
        protected_color_features = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
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
    graded = hard_array * (1.0 - target_feature_region)
    graded_image = Image.fromarray(np.uint8(np.round(graded * 255)), mode="L")

    identity_seed: Image.Image | None = None
    identity_warp: Image.Image | None = None
    identity_warp_mask: Image.Image | None = None
    identity_mesh: dict | None = None
    identity_beard_mask = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), 0)
    identity_beard_detail: dict = {"applied": False, "pixels": 0}
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
            neck_anchor,
            preserve_feature_mask,
            uncovered_skin_mask,
            identity_reference,
            mesh_identity_strength,
            eye_source_mode,
            mesh_geometry_fit_mode,
        )
        # Carey fills the complete visible head/face/ears/neck skin first; the
        # target's theme material is then explicitly laid back over that seed.
        identity_seed = restore_protected_material(identity_seed, crop, hair_exclusion)
        identity_beard_mask, identity_beard_detail = _identity_beard_detail_mask(
            identity_seed, hard, crop_mesh, topology
        )
        identity_mesh["beard_detail"] = identity_beard_detail
        identity_mesh["target_theme_overlay"] = {
            "order": "after-full-head-identity-mesh-seed",
            "source": "target-crop",
            "mask_artifact": "hair_headwear_exclusion",
            "preserved_classes": ["hair", "headwear", "eyeglasses", "earrings", "necklaces", "clothing"],
        }
        # Soften the nose-region edges in the identity seed so the v3 ControlNet
        # CANNY guidance produces a flat anime nose line instead of a sculpted
        # 3D ridge.  Bilateral filter preserves the broad nose shape while
        # dissolving the high-frequency cel-shading the canny would otherwise
        # read as a hard edge.  Outside the nose mask the seed is untouched.
        identity_seed, nose_soften_report = _soften_identity_seed_nose(
            identity_seed, mesh_points, crop_box, topology,
            target_crop=crop,
        )
        identity_mesh["nose_edge_soften"] = nose_soften_report

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

    upload_analysis = _build_upload_analysis(
        detection_score=detection_score,
        detected_faces=detected_faces,
        crop=crop,
        mesh_points=mesh_points,
        semantic_labels=semantic_labels,
        semantic_parser=semantic_parser,
        hard_mask=hard,
        hair_exclusion=hair_exclusion,
        neck_anchor=neck_anchor,
        identity_mesh=identity_mesh,
    )

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
    semantic_ids_path = output_dir / "semantic_class_ids.png"
    seed_path = output_dir / "identity_mesh_seed.png"
    warp_path = output_dir / "identity_mesh_warp.png"
    warp_mask_path = output_dir / "identity_mesh_warp_mask.png"
    preserve_feature_path = output_dir / "protected_seed_features.png"
    ear_skin_path = output_dir / "ear_skin_tone_zone.png"
    uncovered_skin_path = output_dir / "uncovered_skin_tone_zone.png"
    skin_edge_path = output_dir / "skin_edge_fringe.png"
    protected_color_path = output_dir / "protected_color_features.png"
    identity_beard_path = output_dir / "identity_beard_detail_mask.png"
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
    Image.fromarray(np.uint8(semantic_labels), mode="L").save(
        semantic_ids_path, "PNG", optimize=True
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
        identity_beard_mask.save(identity_beard_path, "PNG", optimize=True)
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
        "upload_analysis": upload_analysis,
        "target_feature_lock": target_feature_lock,
        "crop_preflight": {
            "passed": not expandable_contacts,
            "reroutes": _crop_attempt,
            "factor_used": round(float(crop_factor), 6),
            "vertical_translation_px": int(applied_crop_shift_y),
            "boundary_contacts": boundary_contacts,
            "semantic_skin_boundary_contacts": semantic_skin_boundary_contacts,
            "expandable_contacts": expandable_contacts,
            "rule": "translate upward when exposed head skin is top-clipped and bottom neck clearance is available; otherwise expand and re-analyze before GPU",
        },
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
            "semantic_class_ids": str(semantic_ids_path),
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
                    "identity_beard_detail_mask": str(identity_beard_path),
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

def _harmonize_exposed_skin_after_gpu(
    generated_rgb: np.ndarray,
    hard: np.ndarray,
    protected_color: np.ndarray,
    artifacts: dict,
) -> tuple[np.ndarray, dict]:
    """Unify face, visible ears and neck after diffusion without erasing ink."""
    shape = hard.shape
    masks: dict[str, np.ndarray] = {}
    for name, key in (("ears", "ear_skin_tone_zone"), ("neck", "neck_anchor"), ("edge", "skin_edge_fringe")):
        path = artifacts.get(key)
        if path and Path(path).is_file():
            with Image.open(path) as opened:
                masks[name] = np.asarray(opened.convert("L"), dtype=np.float32) / 255.0
        else:
            masks[name] = np.zeros(shape, dtype=np.float32)

    exposed = hard > 0.5
    ear_or_neck = (masks["ears"] > 0.25) | (masks["neck"] > 0.25)
    face = exposed & ~ear_or_neck & (protected_color < 0.25)
    rgb_u8 = np.uint8(np.clip(generated_rgb, 0, 255))
    lab = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2LAB).astype(np.float32)
    if int(face.sum()) < 128:
        return generated_rgb, {"applied": False, "reason": "face-palette-too-small"}

    face_l = lab[..., 0][face]
    lo, hi = np.percentile(face_l, (36, 76))
    face_fill = face & (lab[..., 0] >= lo) & (lab[..., 0] <= hi)
    if int(face_fill.sum()) < 64:
        return generated_rgb, {"applied": False, "reason": "face-fill-too-small"}
    face_median = np.median(lab[face_fill], axis=0)
    out = lab.copy()
    report: dict = {
        "applied": True,
        "reference": "generated-carey-face-midtones",
        "face_lab_median": [round(float(value), 3) for value in face_median],
        "regions": {},
    }
    for name, mask in masks.items():
        base_mask = mask > 0.12
        if name == "neck":
            base_mask |= cv2.dilate(
                masks["neck"].astype(np.float32),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
                iterations=1,
            ) > 0.06
            base_mask |= masks["edge"] > 0.08
        if name == "ears":
            base_mask |= cv2.dilate(
                masks["ears"].astype(np.float32),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
                iterations=1,
            ) > 0.06
        region = base_mask & exposed & (protected_color < 0.95)
        pixels = int(region.sum())
        if pixels < 16:
            report["regions"][name] = {"applied": False, "pixels": pixels}
            continue
        region_l = lab[..., 0][region]
        cutoff = float(np.percentile(region_l, 24 if name == "neck" else 28))
        fill = region & (lab[..., 0] > cutoff)
        if int(fill.sum()) < 8:
            report["regions"][name] = {"applied": False, "pixels": pixels}
            continue
        before = np.median(lab[fill], axis=0)
        if name == "neck":
            delta = np.clip(
                face_median - before,
                np.asarray((-54.0, -30.0, -30.0), dtype=np.float32),
                np.asarray((54.0, 30.0, 30.0), dtype=np.float32),
            )
        else:
            delta = np.clip(
                face_median - before,
                np.asarray((-44.0, -24.0, -24.0), dtype=np.float32),
                np.asarray((44.0, 24.0, 24.0), dtype=np.float32),
            )
        adjusted = lab + delta[None, None, :]
        alpha = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.0)
        if name == "neck":
            alpha = np.maximum(alpha, cv2.GaussianBlur((region.astype(np.float32)), (0, 0), 1.4))
            alpha = np.maximum(alpha, cv2.GaussianBlur((masks["edge"] > 0.08).astype(np.float32), (0, 0), 1.2))
        ink_weight = np.where(lab[..., 0] <= cutoff, 0.18 if name == "neck" else 0.22, 0.96 if name == "neck" else 0.92)
        alpha = np.clip(alpha * ink_weight * hard, 0.0, 1.0)[..., None]
        out = out * (1.0 - alpha) + adjusted * alpha
        after = np.median(out[fill], axis=0)
        report["regions"][name] = {
            "applied": True,
            "pixels": pixels,
            "lab_before": [round(float(value), 3) for value in before],
            "lab_after": [round(float(value), 3) for value in after],
            "lab_delta": [round(float(value), 3) for value in delta],
        }
    return cv2.cvtColor(
        np.uint8(np.clip(out, 0, 255)), cv2.COLOR_LAB2RGB
    ).astype(np.float32), report


def _attack_residual_target_complexion(
    generated: Image.Image,
    target: Image.Image,
    hard: np.ndarray,
    artifacts: dict,
    semantic_parser: dict,
) -> tuple[Image.Image, dict]:
    """Replace every residual target-complexion pixel with Carey's warped surface."""
    identity_path = artifacts.get("identity_mesh_seed")
    ids_path = artifacts.get("semantic_class_ids")
    if not identity_path or not Path(identity_path).is_file():
        raise RuntimeError("Complexion gate stopped the job: Carey identity surface is unavailable.")
    if not ids_path or not Path(ids_path).is_file():
        raise RuntimeError("Complexion gate stopped the job: semantic class-ID map is unavailable.")

    size = generated.size
    with Image.open(identity_path) as opened:
        identity = opened.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    with Image.open(ids_path) as opened:
        class_ids = np.asarray(opened.convert("L").resize(size, Image.Resampling.NEAREST))
    hard_bool = hard > 0.5
    mode = str(semantic_parser.get("mode") or "unknown")
    if mode == "parsenet-anime-fallback":
        neck_extra = np.zeros(hard_bool.shape, dtype=bool)
        neck_path = artifacts.get("neck_anchor")
        if neck_path and Path(neck_path).is_file():
            with Image.open(neck_path) as opened:
                neck_extra = np.asarray(opened.convert("L").resize(size, Image.Resampling.NEAREST)) > 127
        neck_region = (class_ids == 17) | neck_extra
        region_masks = {
            "face_skin": (class_ids == 1) & ~neck_region,
            "nose": class_ids == 2,
            "left_ear": class_ids == 8,
            "right_ear": class_ids == 9,
            "neck": neck_region,
        }
        semantic_skin = np.isin(class_ids, (1, 2, 8, 9)) | neck_region
    elif mode == "mediapipe-selfie-multiclass":
        region_masks = {"exposed_head_skin": hard_bool}
        semantic_skin = hard_bool.copy()
    else:
        raise RuntimeError(
            f"Complexion gate stopped the job: unsupported semantic parser mode {mode!r}."
        )
    semantic_skin &= hard_bool
    if int(semantic_skin.sum()) < 256:
        raise RuntimeError("Complexion gate stopped the job: exposed-skin coverage is too small.")

    generated_rgb = np.asarray(generated.convert("RGB"), dtype=np.uint8)
    target_rgb = np.asarray(target.convert("RGB").resize(size, Image.Resampling.LANCZOS), dtype=np.uint8)
    identity_rgb = np.asarray(identity, dtype=np.uint8)
    generated_lab = cv2.cvtColor(generated_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    target_lab = cv2.cvtColor(target_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    identity_lab = cv2.cvtColor(identity_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    target_distance = np.linalg.norm(generated_lab - target_lab, axis=2)
    identity_distance = np.linalg.norm(generated_lab - identity_lab, axis=2)
    palette_distance = np.linalg.norm(target_lab - identity_lab, axis=2)
    eligible = semantic_skin & (palette_distance >= 16.0) & (target_lab[..., 0] >= 38.0)
    # Only replace pixels that still look more like the immutable target than
    # the Carey seed.  The former lightness OR-clause also selected legitimate
    # highlights from an IP-Adapter result and pasted a hard block of the mesh
    # seed across the cheek.  Highlights are part of the generated likeness;
    # they are not evidence that target complexion survived.
    residual = eligible & (target_distance + 4.0 < identity_distance)
    before_pixels = int(residual.sum())
    if before_pixels:
        core = cv2.dilate(
            residual.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        ).astype(np.float32)
        alpha = cv2.GaussianBlur(core, (0, 0), 0.75)
        alpha = np.clip(alpha * semantic_skin.astype(np.float32), 0.0, 1.0)[..., None]
        attacked = generated_rgb.astype(np.float32) * (1.0 - alpha) + identity_rgb.astype(np.float32) * alpha
    else:
        attacked = generated_rgb.astype(np.float32)
    attacked_u8 = np.uint8(np.clip(attacked, 0, 255))
    attacked_lab = cv2.cvtColor(attacked_u8, cv2.COLOR_RGB2LAB).astype(np.float32)
    remaining_target_distance = np.linalg.norm(attacked_lab - target_lab, axis=2)
    remaining_identity_distance = np.linalg.norm(attacked_lab - identity_lab, axis=2)
    remaining = eligible & (
        remaining_target_distance + 4.0 < remaining_identity_distance
    )
    remaining_pixels = int(remaining.sum())
    remaining_ratio = float(remaining_pixels / max(1, int(eligible.sum())))
    regions = {}
    for name, region in region_masks.items():
        region = region & hard_bool
        regions[name] = {
            "detected_pixels": int(region.sum()),
            "attacked_pixels": int(np.count_nonzero(residual & region)),
            "remaining_target_complexion_pixels": int(np.count_nonzero(remaining & region)),
        }
    report = {
        "passed": bool(remaining_ratio <= 0.005),
        "mode": "semantic-target-complexion-to-carey-identity-surface",
        "parser": mode,
        "eligible_pixels": int(eligible.sum()),
        "attacked_pixels": before_pixels,
        "remaining_target_complexion_pixels": remaining_pixels,
        "remaining_ratio": round(remaining_ratio, 6),
        "regions": regions,
        "excluded": ["eyes", "eye-sockets", "mouth-cavity", "teeth", "hair", "headwear", "clothing", "dark-linework"],
    }
    return Image.fromarray(attacked_u8, mode="RGB"), report


def _final_reference_target_recheck(
    *,
    zone_file: Path,
    zone: dict,
    original_before: Image.Image,
    final_image: Image.Image,
    target_crop: Image.Image,
    soft_mask: Image.Image,
    protected_color_mask: Image.Image | None,
    identity_seed: Image.Image | None,
    left: int,
    top: int,
    side: int,
) -> dict:
    """Recheck the exported crop against the immutable target and Carey seed.

    The examiner proves the input mask before GPU work. This second look proves
    that the exported image still owns the intended complexion/identity
    surface, preserves locked target features, and did not leak changes beyond
    the saved soft zone. It never performs a second generative pass.
    """
    target = target_crop.resize((side, side), Image.Resampling.LANCZOS).convert("RGB")
    final_crop = final_image.crop((left, top, left + side, top + side)).convert("RGB")
    artifacts = dict(zone.get("artifacts") or {})
    hard_path = artifacts.get("hard_mask")
    if hard_path and Path(hard_path).is_file():
        with Image.open(hard_path) as opened:
            hard = np.asarray(
                opened.convert("L").resize((side, side), Image.Resampling.NEAREST)
            ) > 127
    else:
        hard = np.ones((side, side), dtype=bool)
    if protected_color_mask is not None:
        protected = np.asarray(
            protected_color_mask.resize((side, side), Image.Resampling.NEAREST)
        ) > 127
    else:
        protected = np.zeros((side, side), dtype=bool)

    target_rgb = np.asarray(target, dtype=np.uint8)
    final_rgb = np.asarray(final_crop, dtype=np.uint8)
    target_lab = cv2.cvtColor(target_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    final_lab = cv2.cvtColor(final_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    target_feature_diff = np.abs(final_rgb.astype(np.int16) - target_rgb.astype(np.int16))
    protected_pixels = max(1, int(protected.sum()))
    protected_drift = np.any(target_feature_diff > 3, axis=2) & protected
    protected_drift_ratio = float(protected_drift.sum() / protected_pixels)
    protected_mean_abs = float(target_feature_diff[protected].mean()) if protected.any() else 0.0

    target_like_pixels = None
    identity_closer_pixels = None
    identity_closer_ratio = None
    eligible_pixels = 0
    reference_panel: Image.Image | None = None
    identity_path = artifacts.get("identity_mesh_seed")
    if identity_seed is not None:
        reference_panel = identity_seed.resize((side, side), Image.Resampling.LANCZOS).convert("RGB")
        reference_rgb = np.asarray(reference_panel, dtype=np.uint8)
        reference_lab = cv2.cvtColor(reference_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        target_distance = np.linalg.norm(final_lab - target_lab, axis=2)
        reference_distance = np.linalg.norm(final_lab - reference_lab, axis=2)
        target_reference_palette = np.linalg.norm(target_lab - reference_lab, axis=2)
        target_edges = cv2.Canny(cv2.cvtColor(target_rgb, cv2.COLOR_RGB2GRAY), 38, 112) > 0
        target_edges = cv2.dilate(
            target_edges.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        ).astype(bool)
        # Ignore locked target features and dark anime ink; compare complexion
        # surfaces to the same Carey reference used to seed the GPU crop.
        eligible = (
            hard & ~protected & ~target_edges
            & (target_reference_palette >= 16.0)
            & (target_lab[..., 0] >= 38.0)
        )
        eligible_pixels = int(eligible.sum())
        if eligible_pixels:
            target_like = eligible & (target_distance + 4.0 < reference_distance)
            identity_closer = eligible & (reference_distance + 4.0 < target_distance)
            target_like_pixels = int(target_like.sum())
            identity_closer_pixels = int(identity_closer.sum())
            identity_closer_ratio = float(identity_closer_pixels / eligible_pixels)

    before_rgb = np.asarray(original_before.convert("RGB"), dtype=np.uint8)
    after_rgb = np.asarray(final_image.convert("RGB"), dtype=np.uint8)
    changed = np.any(np.abs(after_rgb.astype(np.int16) - before_rgb.astype(np.int16)) > 0, axis=2)
    authority_mask = soft_mask
    authority_path = artifacts.get("final_export_authority_mask")
    if authority_path and Path(authority_path).is_file():
        with Image.open(authority_path) as opened:
            authority_mask = opened.convert("L")
    authority_side = np.asarray(authority_mask.resize((side, side), Image.Resampling.BILINEAR)) > 0
    authority_full = np.zeros(changed.shape, dtype=bool)
    authority_full[top:top + side, left:left + side] = authority_side
    outside_soft_changed = changed & ~authority_full

    warnings: list[dict] = []
    if int(outside_soft_changed.sum()):
        warnings.append({
            "code": "FINAL_EDIT_OUTSIDE_AUTHORITY_MASK",
            "severity": "error",
            "message": "Exported pixels changed outside the saved final authority mask.",
            "pixels": int(outside_soft_changed.sum()),
        })
    if protected_drift_ratio > 0.02:
        warnings.append({
            "code": "TARGET_FEATURE_DRIFT_AFTER_EXPORT",
            "severity": "warning",
            "message": "Locked target eye/mouth/ear material drifted after the final composite.",
            "pixels": int(protected_drift.sum()),
            "ratio": round(protected_drift_ratio, 6),
        })
    target_like_ratio = None
    if target_like_pixels is not None and eligible_pixels:
        target_like_ratio = float(target_like_pixels / eligible_pixels)
        if target_like_ratio > 0.05:
            warnings.append({
                "code": "FINAL_REFERENCE_IDENTITY_RECHECK_LOW",
                "severity": "warning",
                "message": "The exported complexion remains closer to the target than the Carey reference on part of the editable skin surface.",
                "pixels": target_like_pixels,
                "ratio": round(target_like_ratio, 6),
            })
    if identity_closer_ratio is not None and identity_closer_ratio < 0.35:
        warnings.append({
            "code": "FINAL_REFERENCE_SIGNAL_WEAK",
            "severity": "warning",
            "message": "The exported editable surface has a weak Carey-reference signal; review the recheck panel before approval.",
            "ratio": round(identity_closer_ratio, 6),
        })
    passed = not any(item.get("severity") == "error" for item in warnings) and not any(
        item.get("code") == "FINAL_REFERENCE_IDENTITY_RECHECK_LOW" for item in warnings
    )

    audit_path = zone_file.parent / "reference_target_recheck.png"
    panel_size = (256, 256)
    panels = [
        ("TARGET", ImageOps.fit(target, panel_size, method=Image.Resampling.LANCZOS)),
        ("CAREY REFERENCE", ImageOps.fit(reference_panel or target, panel_size, method=Image.Resampling.LANCZOS)),
        ("EXPORTED", ImageOps.fit(final_crop, panel_size, method=Image.Resampling.LANCZOS)),
        ("EDIT MASK", ImageOps.fit(authority_mask.convert("L").convert("RGB"), panel_size, method=Image.Resampling.NEAREST)),
    ]
    audit = Image.new("RGB", (panel_size[0] * len(panels), panel_size[1] + 24), (24, 24, 24))
    draw = ImageDraw.Draw(audit)
    for index, (label, panel) in enumerate(panels):
        x = index * panel_size[0]
        audit.paste(panel, (x, 24))
        draw.text((x + 6, 6), label, fill=(255, 255, 255))
    audit.save(audit_path, "PNG", optimize=True)

    return {
        "version": 1,
        "passed": bool(passed),
        "review_required": bool(warnings),
        "reference_source": str(identity_path) if identity_path else None,
        "target_source": str(artifacts.get("face_crop") or ""),
        "audit_artifact": str(audit_path),
        "editable_surface_pixels": int(np.count_nonzero(hard & ~protected)),
        "eligible_complexion_pixels": int(eligible_pixels),
        "target_like_complexion_pixels": target_like_pixels,
        "target_like_complexion_ratio": round(target_like_ratio, 6) if target_like_ratio is not None else None,
        "identity_closer_pixels": identity_closer_pixels,
        "identity_closer_ratio": round(identity_closer_ratio, 6) if identity_closer_ratio is not None else None,
        "locked_target_feature_pixels": int(protected.sum()),
        "locked_target_feature_drift_pixels": int(protected_drift.sum()),
        "locked_target_feature_drift_ratio": round(protected_drift_ratio, 6),
        "locked_target_feature_mean_abs_delta": round(protected_mean_abs, 4),
        "outside_soft_mask_changed_pixels": int(outside_soft_changed.sum()),
        "final_authority_mask": str(authority_path) if authority_path else None,
        "warnings": warnings,
        "rule": "recheck immutable target and Carey reference after final CPU composite; no second generative pass",
    }


def _fix_face_zone_seam(
    original: Image.Image,
    left: int,
    top: int,
    side: int,
    soft_mask_resized: Image.Image,
    hair_mask_resized: Image.Image,
) -> dict:
    """Dissolve visible seams at the face-zone boundary and hair overlay edge.

    Two seams are common after the soft-mask composite and hair overlay:
      1. Seam at the soft face-zone boundary (x≈309 for this target) — where the
         brown face skin transitions to the untouched original.  The soft mask
         feather is only ~3px; the contrast between face and original background
         creates a visible edge.
      2. Seam at the hair/headwear overlay boundary (x≈115) — where the hair
         overlay ends and the face skin begins.  The blur radius 1.5 → 6.0 helps,
         but a contrast-line can still remain where dark skin meets the blurred
         edge of the white bandage.

    This pass detects both boundaries, finds pixels with high local lightness
    contrast, and blends them with a Gaussian-weighted LAB neighborhood.
    A 12 px corridor around each boundary is scanned; pixels >1.5 sigma above
    the local mean are smoothed.  Nothing changes pixels inside the confirmed-face
    zone or far outside it.
    """
    try:
        # Work on a local crop so we don't disturb the rest of the image
        crop = original.crop((left, top, left + side, top + side))
        crop_rgb = np.asarray(crop.convert("RGB"), dtype=np.uint8)
        crop_lab = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)

        soft_arr = np.asarray(soft_mask_resized.convert("L")) > 63
        hair_arr = np.asarray(hair_mask_resized.convert("L")) > 48

        # Boundary corridors (12 px wide around each seam)
        seam_width = 12
        rows, cols = np.indices((side, side))
        corridor1 = _seam_boundary_corridor(soft_arr, seam_width, rows, cols)
        corridor2 = _seam_boundary_corridor(hair_arr, seam_width, rows, cols)
        seam_corridor = corridor1 | corridor2

        # Local mean LAB in a 9-pixel radius Gaussian window
        blurred_l = cv2.GaussianBlur(crop_lab[..., 0], (0, 0), sigmaX=2.5)
        blurred_a = cv2.GaussianBlur(crop_lab[..., 1], (0, 0), sigmaX=2.5)
        blurred_b = cv2.GaussianBlur(crop_lab[..., 2], (0, 0), sigmaX=2.5)
        local_mean = np.stack([blurred_l, blurred_a, blurred_b], axis=2)

        # Lightness delta from local mean
        delta_l = np.abs(crop_lab[..., 0] - local_mean[..., 0])
        sigma_l = max(1.0, float(np.std(delta_l[seam_corridor])))
        seam_pixels = seam_corridor & (delta_l > 1.6 * sigma_l)
        seam_count = int(seam_pixels.sum())

        if seam_count < 16:
            return {
                "applied": False,
                "reason": "insufficient-seam-pixels",
                "seam_pixels": seam_count,
            }

        # Gaussian-weighted blend toward local mean (sigma=2.5 → ~6 px radius)
        weight = cv2.GaussianBlur(
            seam_pixels.astype(np.float32), (0, 0), sigmaX=2.5
        )
        weight = np.clip(weight * 1.5, 0.0, 1.0)[..., None]
        repaired_lab = crop_lab.copy()
        repaired_lab[seam_pixels] = (
            crop_lab[seam_pixels] * (1.0 - weight[seam_pixels])
            + local_mean[seam_pixels] * weight[seam_pixels]
        )
        repaired_rgb = cv2.cvtColor(
            np.uint8(np.clip(repaired_lab, 0, 255)), cv2.COLOR_LAB2RGB
        )

        # Paste back into original
        repaired = Image.fromarray(repaired_rgb, mode="RGB")
        original.paste(repaired, (left, top))

        return {
            "applied": True,
            "seam_pixels": seam_count,
            "sigma_l": round(sigma_l, 3),
            "corridor1_pixels": int(corridor1.sum()),
            "corridor2_pixels": int(corridor2.sum()),
            "rule": "Gaussian LAB neighborhood blend at soft-zone and hair-boundary corridors",
        }
    except Exception as exc:
        return {"applied": False, "reason": str(exc), "seam_pixels": 0}


def _seam_boundary_corridor(
    mask: np.ndarray, width: int, rows: np.ndarray, cols: np.ndarray
) -> np.ndarray:
    """Return a bool array of pixels within `width` px of the mask boundary."""
    boundary = mask & ~cv2.erode(
        mask.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    ).astype(bool)
    if not boundary.any():
        return boundary
    boundary_dilated = cv2.dilate(
        boundary.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (width, width)),
        iterations=1,
    ).astype(bool)
    corridor = boundary_dilated & ~cv2.erode(
        boundary_dilated.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (width, width)),
        iterations=1,
    ).astype(bool)
    return corridor


def _composite_preserved_target_features(
    zone_file: Path,
    zone: dict,
    original: Image.Image,
    target_crop: Image.Image,
    hard: np.ndarray,
    output: Path,
    crop_only: bool = False,
) -> Path:
    """Keep target facial geometry/ink exactly; transfer only Carey skin fill."""
    artifacts = zone["artifacts"]
    box = zone["crop_box"]
    side = int(box["width"])
    left, top = int(box["x"]), int(box["y"])
    target = target_crop.resize((side, side), Image.Resampling.LANCZOS).convert("RGB")
    target_rgb = np.asarray(target, dtype=np.uint8)
    target_lab = cv2.cvtColor(target_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    with Image.open(artifacts["semantic_class_ids"]) as opened:
        class_ids = np.asarray(
            opened.convert("L").resize((side, side), Image.Resampling.NEAREST)
        )
    hard_side = np.asarray(
        Image.fromarray(np.uint8(np.clip(hard * 255.0, 0, 255)), mode="L").resize(
            (side, side), Image.Resampling.NEAREST
        )
    ) > 127
    # ParseNet classes: skin, nose, ears, neck. Eyes, brows, lips/mouth,
    # hair/headwear, clothing, and accessories are deliberately absent.
    skin = np.isin(class_ids, (1, 2, 8, 9, 17)) & hard_side
    if int(np.count_nonzero(skin)) < 256:
        raise RuntimeError("Complexion-only lane found too little parser-confirmed skin.")
    initial_l = target_lab[..., 0][skin]
    initial_sample = skin & (target_lab[..., 0] >= np.percentile(initial_l, 42))
    initial_target_median = np.median(target_lab[initial_sample], axis=0)
    skin_y, skin_x = np.where(skin)
    skin_corridor = np.zeros_like(skin)
    skin_corridor[
        max(0, int(skin_y.min()) - 96):min(side, int(skin_y.max()) + 97),
        max(0, int(skin_x.min()) - 72):min(side, int(skin_x.max()) + 73),
    ] = True
    target_skin_distance = np.linalg.norm(
        target_lab - initial_target_median[None, None, :], axis=2
    )
    protected_feature_classes = np.isin(class_ids, (3, 4, 5, 10, 11, 12, 15, 16, 18))
    color_recovered_skin = (
        skin_corridor & ~protected_feature_classes
        & (target_lab[..., 0] > 100.0)
        & (target_skin_distance < 30.0)
    )
    color_recovered_pixels = int(np.count_nonzero(color_recovered_skin & ~skin))
    skin |= color_recovered_skin
    identity_path = artifacts.get("identity_mesh_seed")
    if not identity_path or not Path(identity_path).is_file():
        raise RuntimeError("Complexion-only lane needs the audited Carey palette seed.")
    with Image.open(identity_path) as opened:
        identity_rgb = np.asarray(
            opened.convert("RGB").resize((side, side), Image.Resampling.LANCZOS),
            dtype=np.uint8,
        )
    identity_lab = cv2.cvtColor(identity_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    target_l = target_lab[..., 0][skin]
    identity_l = identity_lab[..., 0][skin]
    target_sample = skin & (target_lab[..., 0] >= np.percentile(target_l, 42))
    identity_lo, identity_hi = np.percentile(identity_l, (18, 52))
    identity_sample = (
        skin
        & (identity_lab[..., 0] >= max(42.0, float(identity_lo)))
        & (identity_lab[..., 0] <= float(identity_hi))
    )
    if int(np.count_nonzero(target_sample)) < 64 or int(np.count_nonzero(identity_sample)) < 64:
        raise RuntimeError("Complexion-only lane could not establish safe skin palettes.")
    target_median = np.median(target_lab[target_sample], axis=0)
    carey_median = np.median(identity_lab[identity_sample], axis=0)
    delta = np.clip(
        carey_median - target_median,
        np.asarray((-100.0, -10.0, -8.0), dtype=np.float32),
        np.asarray((18.0, 10.0, 4.0), dtype=np.float32),
    )
    adjusted_lab = target_lab.copy()
    adjusted_lab[..., 0] += delta[0]
    adjusted_lab[..., 1] += delta[1]
    adjusted_lab[..., 2] += delta[2]
    adjusted_rgb = cv2.cvtColor(
        np.uint8(np.clip(adjusted_lab, 0, 255)), cv2.COLOR_LAB2RGB
    ).astype(np.float32)
    # Preserve every dark target outline. Only flat/light skin fill receives
    # full complexion transfer; antialiased ink gets a proportional blend.
    ink_floor = float(np.percentile(target_l, 12))
    fill_floor = float(np.percentile(target_l, 38))
    ink_weight = np.clip(
        (target_lab[..., 0] - ink_floor) / max(1.0, fill_floor - ink_floor),
        0.0,
        1.0,
    )
    alpha = np.clip(skin.astype(np.float32) * ink_weight, 0.0, 1.0)[..., None]
    recolored = target_rgb.astype(np.float32) * (1.0 - alpha) + adjusted_rgb * alpha
    recolored_u8 = np.uint8(np.clip(recolored, 0, 255))
    report = {
        "applied": True,
        "skin_pixels": int(np.count_nonzero(skin)),
        "color_recovered_skin_pixels": color_recovered_pixels,
        "target_skin_lab_median": [round(float(v), 3) for v in target_median],
        "carey_skin_lab_median": [round(float(v), 3) for v in carey_median],
        "lab_delta": [round(float(v), 3) for v in delta],
        "preserved_classes": [
            "eyebrows", "eyes", "nose ink", "ear ink", "mouth", "lips",
            "hair", "headwear", "clothing", "background",
        ],
        "rule": "change parser-confirmed and color-connected skin fill only; target facial outlines remain the mold",
    }
    if crop_only:
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(recolored_u8, mode="RGB").save(output, "PNG", optimize=True)
        zone["gpu_complexion_precondition"] = report
        zone.setdefault("artifacts", {})["complexion_preconditioned_crop"] = str(output)
        zone_file.write_text(json.dumps(zone, indent=2) + "\n", encoding="utf-8")
        return output
    result = original.copy()
    result.paste(Image.fromarray(recolored_u8, mode="RGB"), (left, top))
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, "PNG", optimize=True)
    authority = Image.fromarray(np.uint8(skin) * 255, mode="L")
    authority_path = zone_file.parent / "final_export_authority_mask.png"
    authority.save(authority_path, "PNG", optimize=True)
    zone.setdefault("artifacts", {})["final_export_authority_mask"] = str(authority_path)
    zone["preserved_target_feature_complexion_transfer"] = report
    zone["status"] = "target facial features preserved; Carey complexion transferred"
    zone_file.write_text(json.dumps(zone, indent=2) + "\n", encoding="utf-8")
    return output


def composite_generated(zone_file: Path, generated_crop: Path, output: Path) -> Path:
    zone = json.loads(zone_file.read_text(encoding="utf-8-sig"))
    artifacts = zone["artifacts"]
    with Image.open(artifacts["original"]) as opened:
        original = opened.convert("RGB")
    original_before = original.copy()
    with Image.open(generated_crop) as opened:
        generated = opened.convert("RGB")
    with Image.open(artifacts["soft_mask"]) as opened:
        soft = opened.convert("L")
    with Image.open(artifacts["face_crop"]) as opened:
        target_crop = opened.convert("RGB")
    with Image.open(artifacts["hard_mask"]) as opened:
        hard = np.asarray(opened.convert("L"), dtype=np.float32) / 255.0
    if zone.get("preserve_target_features_complexion_only"):
        return _composite_preserved_target_features(
            zone_file, zone, original, target_crop, hard, output
        )
    protected_color = np.zeros(hard.shape, dtype=np.float32)
    protected_color_mask: Image.Image | None = None
    protected_color_path = artifacts.get("protected_color_features")
    if protected_color_path and Path(protected_color_path).is_file():
        with Image.open(protected_color_path) as opened:
            protected_color_mask = opened.convert("L").copy()
            protected_color = np.asarray(protected_color_mask, dtype=np.float32) / 255.0
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
        generated_array = adjusted
    # v3 ControlNet already produces anime-cel-shaded output; the post-GPU
    # harmonization and complexion attack were designed for the photoreal
    # v1 output and would smooth the anime shading the v3 GPU just paid for.
    # Allow recipes to opt out of these passes when the GPU output is already
    # in the right style envelope.
    skip_post_gpu_skin = bool(zone.get("skip_post_gpu_skin", False))
    if skip_post_gpu_skin:
        skin_harmonization = {
            "applied": False,
            "skipped": True,
            "reason": "recipe requests skip_post_gpu_skin (v3 ControlNet outputs native anime cel-shading)",
        }
        complexion_report = {
            "applied": False,
            "skipped": True,
            "passed": True,
            "mode": "skipped-for-anime-cel-shaded-output",
            "eligible_pixels": 0,
            "attacked_pixels": 0,
            "remaining_target_complexion_pixels": 0,
            "remaining_ratio": 0.0,
            "regions": {},
            "excluded": [],
        }
        zone["post_gpu_exposed_skin_harmonization"] = skin_harmonization
    else:
        generated_array, skin_harmonization = _harmonize_exposed_skin_after_gpu(
            generated_array, hard, protected_color, artifacts
        )
        generated = Image.fromarray(np.uint8(np.clip(generated_array, 0, 255)), mode="RGB")
        zone["post_gpu_exposed_skin_harmonization"] = skin_harmonization
        generated, complexion_report = _attack_residual_target_complexion(
            generated,
            target_crop,
            hard,
            artifacts,
            dict(zone.get("semantic_parser") or {}),
    )
    zone["post_gpu_complexion_attack"] = complexion_report
    if not complexion_report["passed"]:
        raise RuntimeError(
            "Complexion gate stopped the job: residual target complexion remains "
            f"({complexion_report['remaining_target_complexion_pixels']} pixels, "
            f"ratio {complexion_report['remaining_ratio']})."
        )

    beard_path = artifacts.get("identity_beard_detail_mask")
    seed_path = artifacts.get("identity_mesh_seed")
    beard_report: dict = {"applied": False, "reason": "beard-artifact-unavailable"}
    box = zone["crop_box"]
    side = int(box["width"])
    left, top = int(box["x"]), int(box["y"])
    target_region = original.crop((left, top, left + side, top + side))
    generated = generated.resize((side, side), Image.Resampling.LANCZOS)
    soft = soft.resize((side, side), Image.Resampling.BILINEAR)
    if protected_color_mask is not None:
        protected_material = protected_color_mask.resize(
            (side, side), Image.Resampling.NEAREST
        )
        generated = restore_protected_material(
            generated, target_region, protected_material
        )
    # CPU final authority: Carey jawline beard/goatee is asserted after every
    # GPU and target-material operation. Only target hair/headwear may overlay it.
    if beard_path and seed_path and Path(beard_path).is_file() and Path(seed_path).is_file():
        with Image.open(beard_path) as opened:
            beard_mask = opened.convert("L").resize((side, side), Image.Resampling.BILINEAR)
        with Image.open(seed_path) as opened:
            beard_source = opened.convert("RGB").resize((side, side), Image.Resampling.LANCZOS)
        beard_alpha = beard_mask.point(lambda value: int(value * 0.78))
        generated = Image.composite(beard_source, generated, beard_alpha)
        beard_report = {
            "applied": True,
            "source": str(seed_path),
            "mask": str(beard_path),
            "strength": 0.78,
            "order": "last CPU identity layer before target hair/headwear",
            "rule": "Carey jawline beard/goatee cannot be overwritten by target skin or GPU cleanup",
        }
    zone["post_gpu_identity_detail_lock"] = beard_report
    # Remove only dark warp fragments that protrude into skin immediately to
    # the outside of the semantic mouth.  The lip/mustache core, nostril, and
    # the target's real outer-face ink are explicitly excluded.
    mouth_cleanup_pixels = 0
    class_ids_path = artifacts.get("semantic_class_ids")
    if class_ids_path and Path(class_ids_path).is_file():
        with Image.open(class_ids_path) as opened:
            class_ids = np.asarray(
                opened.convert("L").resize((side, side), Image.Resampling.NEAREST)
            )
        mouth_core = np.isin(class_ids, (10, 11, 12))
        mouth_y, mouth_x = np.where(mouth_core)
        if len(mouth_x) >= 24:
            corridor = np.zeros((side, side), dtype=bool)
            x0 = max(0, int(mouth_x.min()) - 52)
            x1 = min(side, int(mouth_x.min()) + 7)
            y0 = max(0, int(mouth_y.min()) - 20)
            y1 = min(side, int(mouth_y.max()) + 17)
            corridor[y0:y1, x0:x1] = True
            generated_rgb = np.asarray(generated.convert("RGB"), dtype=np.uint8)
            target_rgb = np.asarray(target_region.convert("RGB"), dtype=np.uint8)
            generated_lab = cv2.cvtColor(generated_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
            target_lab = cv2.cvtColor(target_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
            protected_features = cv2.dilate(
                (mouth_core | (class_ids == 2)).astype(np.uint8),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
                iterations=1,
            ).astype(bool)
            hard_side = np.asarray(
                Image.open(artifacts["hard_mask"]).convert("L").resize(
                    (side, side), Image.Resampling.NEAREST
                )
            ) > 127
            artifact = (
                corridor & hard_side & ~protected_features
                & (generated_lab[..., 0] < 58.0)
                & (target_lab[..., 0] > 96.0)
            )
            artifact = cv2.morphologyEx(
                artifact.astype(np.uint8),
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)),
            ).astype(bool)
            mouth_cleanup_pixels = int(np.count_nonzero(artifact))
            if mouth_cleanup_pixels:
                skin_sample = corridor & hard_side & (generated_lab[..., 0] >= 76.0)
                if int(np.count_nonzero(skin_sample)) >= 32:
                    skin_median = np.median(generated_lab[skin_sample], axis=0)
                    repaired_lab = generated_lab.copy()
                    repaired_lab[..., 0][artifact] = skin_median[0]
                    repaired_lab[..., 1][artifact] = skin_median[1]
                    repaired_lab[..., 2][artifact] = skin_median[2]
                    repaired_rgb = cv2.cvtColor(
                        np.uint8(np.clip(repaired_lab, 0, 255)), cv2.COLOR_LAB2RGB
                    )
                    alpha = cv2.GaussianBlur(artifact.astype(np.float32), (0, 0), 0.75)[..., None]
                    cleaned = generated_rgb.astype(np.float32) * (1.0 - alpha) + repaired_rgb.astype(np.float32) * alpha
                    generated = Image.fromarray(np.uint8(np.clip(cleaned, 0, 255)), mode="RGB")
            # Reassert the target's single clean outer-face ink stroke where
            # both images agree a dark boundary belongs.  This replaces the
            # cluster of warped black fragments without importing target skin
            # or the target mouth interior.
            current_rgb = np.asarray(generated.convert("RGB"), dtype=np.uint8)
            current_lab = cv2.cvtColor(current_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
            clean_target_ink = (
                corridor & ~protected_features
                & (target_lab[..., 0] < 66.0)
                & (current_lab[..., 0] < 92.0)
            )
            if clean_target_ink.any():
                ink_alpha = cv2.GaussianBlur(
                    clean_target_ink.astype(np.float32), (0, 0), 0.45
                )[..., None]
                cleaned = current_rgb.astype(np.float32) * (1.0 - ink_alpha) + target_rgb.astype(np.float32) * ink_alpha
                generated = Image.fromarray(np.uint8(np.clip(cleaned, 0, 255)), mode="RGB")
                mouth_cleanup_pixels += int(np.count_nonzero(clean_target_ink))
    zone["final_mouth_warp_cleanup_pixels"] = mouth_cleanup_pixels
    original.paste(generated, (left, top), soft)
    # Founder rule: the target's hair is outlined and imported directly OVER the
    # likeness. Re-assert the original hair/headwear pixels on top of the pasted
    # face so a dilated zone boundary can never eat into the hairline â€” strands
    # that overlap the face win against the generated skin.
    hair_path = artifacts.get("hair_headwear_exclusion")
    if hair_path and Path(hair_path).is_file():
        with Image.open(hair_path) as opened:
            hair = opened.convert("L").resize((side, side), Image.Resampling.BILINEAR)
        hair_arr = np.asarray(hair, dtype=np.uint8)
        target_rgb = np.asarray(target_region.convert("RGB"), dtype=np.uint8)
        visible_rgb = np.asarray(
            original.crop((left, top, left + side, top + side)).convert("RGB"),
            dtype=np.uint8,
        )
        target_lab = cv2.cvtColor(target_rgb, cv2.COLOR_RGB2LAB)
        near_headwear = cv2.dilate(
            (hair_arr > 96).astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)),
            iterations=1,
        ).astype(bool)
        rows_local = np.arange(side, dtype=np.int32)[:, None]
        neutral_target_material = (
            (target_lab[..., 0] > 176)
            & (np.abs(target_lab[..., 1].astype(np.int16) - 128) < 18)
            & (np.abs(target_lab[..., 2].astype(np.int16) - 128) < 20)
        )
        leaked_skin_on_headwear = (
            near_headwear
            & neutral_target_material
            & (rows_local < int(side * 0.32))
            & (np.max(np.abs(visible_rgb.astype(np.int16) - target_rgb.astype(np.int16)), axis=2) > 18)
        )
        if leaked_skin_on_headwear.any():
            hair_arr = np.maximum(hair_arr, np.uint8(leaked_skin_on_headwear) * 255)
            hair = Image.fromarray(hair_arr, mode="L")
        zone["final_headwear_leak_restored_pixels"] = int(np.count_nonzero(leaked_skin_on_headwear))
        hair = hair.filter(ImageFilter.GaussianBlur(6.0))  # wider feather at boundary → no seam
        original.paste(target_region, (left, top), hair)

        # Fix the two visible seam lines: (1) soft-face-boundary contrast,
        # (2) hair-overlay edge.  Both are dissolved by a Gaussian LAB neighborhood
        # blend in a 12 px corridor around each boundary.
        seam_fix = _fix_face_zone_seam(
            original, left, top, side,
            soft,  # already resized to (side, side) at line ~3284
            hair,
        )
        zone["final_seam_fix"] = seam_fix
    # Final complexion authority runs after target hair/headwear restoration.
    # A parser mistake in that overlay must never reintroduce white target
    # pigment on pixels explicitly classified as face, nose, ear, or neck.
    final_white_skin_pixels = 0
    semantic_ids_path = artifacts.get("semantic_class_ids")
    if zone.get("attack_all_white_skin_after_overlay") and semantic_ids_path and Path(semantic_ids_path).is_file():
        with Image.open(semantic_ids_path) as opened:
            semantic_ids = np.asarray(
                opened.convert("L").resize((side, side), Image.Resampling.NEAREST)
            )
        with Image.open(artifacts["hard_mask"]) as opened:
            hard_side = np.asarray(
                opened.convert("L").resize((side, side), Image.Resampling.NEAREST)
            ) > 127
        semantic_skin = np.isin(semantic_ids, (1, 2, 8, 9, 17)) & hard_side
        visible_region = original.crop((left, top, left + side, top + side)).convert("RGB")
        visible_rgb = np.asarray(visible_region, dtype=np.uint8)
        visible_lab = cv2.cvtColor(visible_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        usable_skin = semantic_skin & (visible_lab[..., 0] > 44.0)
        if int(np.count_nonzero(usable_skin)) >= 128:
            skin_l = visible_lab[..., 0][usable_skin]
            sample_ceiling = float(np.percentile(skin_l, 62))
            skin_sample = usable_skin & (visible_lab[..., 0] <= sample_ceiling)
            if int(np.count_nonzero(skin_sample)) >= 64:
                skin_median = np.median(visible_lab[skin_sample], axis=0)
                white_skin = (
                    semantic_skin
                    & (visible_lab[..., 0] > max(150.0, float(skin_median[0] + 32.0)))
                )
                final_white_skin_pixels = int(np.count_nonzero(white_skin))
                if final_white_skin_pixels:
                    local_lab = cv2.GaussianBlur(visible_lab, (0, 0), 4.0)
                    repaired_lab = visible_lab.copy()
                    repaired_lab[..., 0][white_skin] = np.clip(
                        local_lab[..., 0][white_skin],
                        skin_median[0] - 12.0,
                        skin_median[0] + 18.0,
                    )
                    repaired_lab[..., 1][white_skin] = (
                        local_lab[..., 1][white_skin] * 0.20 + skin_median[1] * 0.80
                    )
                    repaired_lab[..., 2][white_skin] = (
                        local_lab[..., 2][white_skin] * 0.20 + skin_median[2] * 0.80
                    )
                    repaired_rgb = cv2.cvtColor(
                        np.uint8(np.clip(repaired_lab, 0, 255)), cv2.COLOR_LAB2RGB
                    )
                    alpha = cv2.GaussianBlur(
                        white_skin.astype(np.float32), (0, 0), 0.8
                    )[..., None]
                    swept = visible_rgb.astype(np.float32) * (1.0 - alpha) + repaired_rgb.astype(np.float32) * alpha
                    original.paste(
                        Image.fromarray(np.uint8(np.clip(swept, 0, 255)), mode="RGB"),
                        (left, top),
                    )
    zone["final_white_skin_pigment_attack_pixels"] = final_white_skin_pixels
    final_neck_path = artifacts.get("neck_anchor")
    final_skin_edge_path = artifacts.get("skin_edge_fringe")
    neck_authority_mask: Image.Image | None = None
    if final_neck_path and Path(final_neck_path).is_file():
        with Image.open(final_neck_path) as opened:
            neck_mask = opened.convert("L").resize((side, side), Image.Resampling.BILINEAR)
        if final_skin_edge_path and Path(final_skin_edge_path).is_file():
            with Image.open(final_skin_edge_path) as opened:
                neck_mask = ImageChops.lighter(
                    neck_mask,
                    opened.convert("L").resize((side, side), Image.Resampling.BILINEAR),
                )
        neck_source = generated.resize((side, side), Image.Resampling.LANCZOS)
        # Final visual authority: after hair/headwear is restored, the neck gets
        # a Carey-tone fill sampled from the generated face. Do not repaint the
        # broad lower jaw here; the beard/detail lock already owns identity.
        try:
            hard_local = Image.open(artifacts["hard_mask"]).convert("L").resize((side, side), Image.Resampling.NEAREST)
            hard_arr = np.asarray(hard_local) > 127
            neck_arr = np.asarray(neck_mask) > 63
            generated_rgb = np.asarray(neck_source.convert("RGB"), dtype=np.uint8)
            generated_lab = cv2.cvtColor(generated_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
            face_sample = hard_arr & ~cv2.dilate(
                neck_arr.astype(np.uint8),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)),
                iterations=1,
            ).astype(bool)
            face_sample &= generated_lab[..., 0] < np.percentile(generated_lab[..., 0][hard_arr], 82)
            if int(face_sample.sum()) >= 64:
                neck_lab = generated_lab.copy()
                face_median = np.median(generated_lab[face_sample], axis=0)
                rows = np.arange(side, dtype=np.int32)[:, None]
                cols = np.arange(side, dtype=np.int32)[None, :]
                visible_rgb = np.asarray(
                    original.crop((left, top, left + side, top + side)).convert("RGB"),
                    dtype=np.uint8,
                )
                visible_lab = cv2.cvtColor(visible_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
                neutral_visible = (
                    (np.abs(visible_lab[..., 1] - 128.0) < 20.0)
                    & (np.abs(visible_lab[..., 2] - 128.0) < 22.0)
                )
                right_neck_corridor = (
                    (rows >= int(side * 0.34))
                    & (rows <= int(side * 0.74))
                    & (cols >= int(side * 0.54))
                    & (cols <= int(side * 0.88))
                    & (visible_lab[..., 0] > face_median[0] + 22.0)
                    & neutral_visible
                )
                # The parser can label the narrow strip behind an ear as
                # headwear/background, so the broad right corridor alone is
                # not a reliable authority mask.  Build a small ring around
                # semantic ears/neck and remove only bright, palette-mismatched
                # pixels in that ring.  Ear interiors stay target-authored.
                seam_corridor = np.zeros_like(hard_arr)
                seam_support = np.zeros_like(hard_arr)
                outer_ear_background = np.zeros_like(hard_arr)
                outer_ear_shift = np.zeros_like(hard_arr, dtype=np.int16)
                ear_core = np.zeros_like(hard_arr)
                class_ids_path = artifacts.get("semantic_class_ids")
                head_envelope_path = artifacts.get("head_envelope")
                if class_ids_path and Path(class_ids_path).is_file():
                    with Image.open(class_ids_path) as opened:
                        class_ids = np.asarray(
                            opened.convert("L").resize((side, side), Image.Resampling.NEAREST)
                        )
                    ear_core = np.isin(class_ids, (8, 9))
                    ear_neck = ear_core | (class_ids == 17) | neck_arr
                    seam_support = cv2.dilate(
                        ear_neck.astype(np.uint8),
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (55, 55)),
                        iterations=1,
                    ).astype(bool)
                    seam_support &= ~ear_core
                    outer_ear_corridor = np.zeros_like(hard_arr)
                    for ear_class in (8, 9):
                        ear_y_values, ear_x_values = np.where(class_ids == ear_class)
                        if len(ear_x_values) < 24:
                            continue
                        ear_x0, ear_x1 = int(ear_x_values.min()), int(ear_x_values.max()) + 1
                        ear_y0, ear_y1 = int(ear_y_values.min()), int(ear_y_values.max()) + 1
                        ear_w, ear_h = ear_x1 - ear_x0, ear_y1 - ear_y0
                        y0 = max(0, ear_y0)
                        y1 = min(side, int(ear_y1 + max(10, ear_h * 0.55)))
                        if ear_x0 + ear_w / 2.0 >= side / 2.0:
                            x0 = max(0, ear_x1 - 4)
                            x1 = min(side, ear_x1 + 26)
                        else:
                            x0 = max(0, ear_x0 - 26)
                            x1 = min(side, ear_x0 + 4)
                        outer_ear_corridor[y0:y1, x0:x1] = True
                        outer_ear_background[y0:ear_y1, x0:x1] = True
                        outer_ear_shift[y0:ear_y1, x0:x1] = 32 if ear_x0 + ear_w / 2.0 >= side / 2.0 else -32
                    seam_support &= outer_ear_corridor
                    # Do not intersect this support with the head envelope:
                    # the defect we are correcting is specifically the bright
                    # one-pixel-to-few-pixel strip that the parser left just
                    # outside that envelope.  The brightness and palette gates
                    # below prevent ordinary dark/blue background from entering.
                    palette_distance = np.linalg.norm(
                        visible_lab - face_median[None, None, :], axis=2
                    )
                    seam_corridor = (
                        seam_support
                        & (rows >= int(side * 0.30))
                        & (rows <= int(side * 0.76))
                        & (visible_lab[..., 0] > face_median[0] + 14.0)
                        & (palette_distance > 32.0)
                        & neutral_visible
                    )
                    seam_corridor = cv2.morphologyEx(
                        seam_corridor.astype(np.uint8),
                        cv2.MORPH_CLOSE,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 11)),
                    ).astype(bool)
                # Never allow the legacy geometric corridor to extend across
                # the cheek.  It may only act next to the detected neck or the
                # semantic ear/neck seam support built above.
                neck_support = cv2.dilate(
                    neck_arr.astype(np.uint8),
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 31)),
                    iterations=1,
                ).astype(bool)
                right_neck_corridor &= neck_support | seam_support
                right_neck_corridor = cv2.morphologyEx(
                    right_neck_corridor.astype(np.uint8),
                    cv2.MORPH_CLOSE,
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 13)),
                ).astype(bool)
                neck_arr |= right_neck_corridor | seam_corridor
                neck_mask = Image.fromarray(np.uint8(neck_arr) * 255, mode="L")
                neck_fill = right_neck_corridor | seam_corridor
                neck_fill &= ~cv2.dilate(
                    ear_core.astype(np.uint8),
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
                    iterations=1,
                ).astype(bool)
                # Preserve local cel shading instead of painting a flat brown
                # patch.  A blurred neighborhood supplies light/shadow detail;
                # only its range and chroma are pulled toward Carey's palette.
                inpaint_mask = np.uint8(neck_fill) * 255
                local_neck_rgb = cv2.inpaint(
                    generated_rgb, inpaint_mask, 7.0, cv2.INPAINT_TELEA
                )
                local_neck_lab = cv2.cvtColor(local_neck_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
                background_fill = neck_fill & outer_ear_background
                skin_fill = neck_fill & ~background_fill
                neck_lab[..., 0][skin_fill] = np.clip(
                    local_neck_lab[..., 0][skin_fill],
                    face_median[0] - 18.0,
                    face_median[0] + 14.0,
                )
                neck_lab[..., 1][skin_fill] = (
                    local_neck_lab[..., 1][skin_fill] * 0.25 + face_median[1] * 0.75
                )
                neck_lab[..., 2][skin_fill] = (
                    local_neck_lab[..., 2][skin_fill] * 0.25 + face_median[2] * 0.75
                )
                if background_fill.any():
                    bg_y, bg_x = np.where(background_fill)
                    source_x = np.clip(
                        bg_x + outer_ear_shift[background_fill], 0, side - 1
                    )
                    sampled_background_rgb = visible_rgb[bg_y, source_x]
                    sampled_background_lab = cv2.cvtColor(
                        sampled_background_rgb.reshape((-1, 1, 3)),
                        cv2.COLOR_RGB2LAB,
                    ).reshape((-1, 3)).astype(np.float32)
                    neck_lab[bg_y, bg_x] = sampled_background_lab
                left_boundary = np.zeros_like(hard_arr)
                hard_rows = np.where(hard_arr.any(axis=1))[0]
                for row in hard_rows:
                    xs = np.where(hard_arr[row])[0]
                    if len(xs):
                        edge = int(xs.min())
                        left_boundary[row, edge:min(side, edge + 16)] = True
                jaw_seam = (
                    left_boundary
                    & (rows >= int(side * 0.36))
                    & (rows <= int(side * 0.82))
                    & (visible_lab[..., 0] < face_median[0] - 18.0)
                )
                jaw_seam = cv2.dilate(
                    jaw_seam.astype(np.uint8),
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 5)),
                    iterations=1,
                ).astype(bool)
                neck_lab[..., 0][jaw_seam] = face_median[0]
                neck_lab[..., 1][jaw_seam] = face_median[1]
                neck_lab[..., 2][jaw_seam] = face_median[2]
                neck_source = Image.fromarray(
                    cv2.cvtColor(np.uint8(np.clip(neck_lab, 0, 255)), cv2.COLOR_LAB2RGB),
                    mode="RGB",
                )
                zone["final_chin_neck_touchup_bright_neck_pixels"] = int(np.count_nonzero(right_neck_corridor))
                zone["final_ear_neck_seam_touchup_pixels"] = int(np.count_nonzero(seam_corridor))
                zone["final_chin_neck_touchup_jaw_seam_pixels"] = int(np.count_nonzero(jaw_seam))
        except Exception as exc:
            zone.setdefault("warnings", []).append({"final_chin_neck_touchup": str(exc)})
        neck_alpha = neck_mask.filter(ImageFilter.GaussianBlur(1.8)).point(
            lambda value: min(255, int(value * 1.0))
        )
        neck_authority_mask = neck_alpha
        original_region = original.crop((left, top, left + side, top + side))
        original_region = Image.composite(neck_source, original_region, neck_alpha)
        original.paste(original_region, (left, top))
        zone["final_chin_neck_touchup"] = {
            "applied": True,
            "jaw_source": "identity-detail-lock-only-no-broad-final-jaw-repaint",
            "neck_source": "carey-tone-fill-sampled-from-generated-face",
            "neck_mask": str(final_neck_path),
            "skin_edge_mask": str(final_skin_edge_path) if final_skin_edge_path else None,
            "neck_alpha_strength": 1.0,
            "jaw_alpha_strength": 0.0,
            "rule": "last exported-image pass recolors neck without broad lower-jaw repaint",
        }
    authority_array = np.asarray(soft.resize((side, side), Image.Resampling.NEAREST), dtype=np.uint8)
    if final_neck_path and Path(final_neck_path).is_file():
        authority_array = np.maximum(
            authority_array,
            np.asarray((neck_authority_mask or neck_mask).resize((side, side), Image.Resampling.NEAREST), dtype=np.uint8),
        )
    authority_mask = Image.fromarray(authority_array, mode="L")
    authority_path = zone_file.parent / "final_export_authority_mask.png"
    authority_mask.save(authority_path, "PNG", optimize=True)
    zone.setdefault("artifacts", {})["final_export_authority_mask"] = str(authority_path)
    identity_seed_for_recheck: Image.Image | None = None
    identity_seed_path = artifacts.get("identity_mesh_seed")
    if identity_seed_path and Path(identity_seed_path).is_file():
        with Image.open(identity_seed_path) as opened:
            identity_seed_for_recheck = opened.convert("RGB")
    zone["final_reference_target_recheck"] = _final_reference_target_recheck(
        zone_file=zone_file,
        zone=zone,
        original_before=original_before,
        final_image=original,
        target_crop=target_crop,
        soft_mask=soft,
        protected_color_mask=protected_color_mask,
        identity_seed=identity_seed_for_recheck,
        left=left,
        top=top,
        side=side,
    )
    if zone["final_reference_target_recheck"].get("warnings"):
        zone.setdefault("warnings", []).extend(
            zone["final_reference_target_recheck"]["warnings"]
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    original.save(output, "PNG", optimize=True)
    zone_file.write_text(json.dumps(zone, indent=2) + "\n", encoding="utf-8")
    return output


def precondition_complexion_crop(zone_file: Path, output: Path) -> Path:
    """Create the Carey-complexion target mold used as the GPU seed."""
    zone = json.loads(zone_file.read_text(encoding="utf-8-sig"))
    artifacts = zone["artifacts"]
    with Image.open(artifacts["original"]) as opened:
        original = opened.convert("RGB")
    with Image.open(artifacts["face_crop"]) as opened:
        target_crop = opened.convert("RGB")
    with Image.open(artifacts["hard_mask"]) as opened:
        hard = np.asarray(opened.convert("L"), dtype=np.float32) / 255.0
    return _composite_preserved_target_features(
        zone_file, zone, original, target_crop, hard, output, crop_only=True
    )


# â”€â”€ The examiner (founder contract 2026-07-15): before ANY edit, the system
# must fully understand where it can and can't operate on THIS image. For every
# face it reports an operability verdict, risk flags, and a per-feature plan â€”
# which features get generated with the founder's likeness and which keep the
# target's logic/shape/theme. Geometry-only v1 (landmarker, no parser) so it is
# fast, deterministic, and runs in any GPU mode; semantic enrichment is the
# staged next rung (docs/IMAGE_GENERATION_STATE.md).

# MediaPipe canonical landmark indices used for the cheap geometry reads.
_LM_NOSE_TIP = 1
_LM_FACE_LEFT = 234
_LM_FACE_RIGHT = 454
_LM_MOUTH_LEFT = 61
_LM_MOUTH_RIGHT = 291
_LM_LIP_UPPER_INNER = 13
_LM_LIP_LOWER_INNER = 14

# The feature contract: likeness where identity lives, target logic everywhere
# else. Presets/eye_protection can override per target; this is the default law.
FEATURE_PLAN_DEFAULT = {
    "skin_complexion": "generate-likeness",
    "brow": "generate-likeness-in-target-form",
    "nose": "generate-likeness-in-target-form",
    "mouth": "generate-likeness-in-target-form",
    "jawline": "generate-likeness-in-target-form",
    "forehead": "generate-likeness-if-exposed-else-keep-headwear",
    "eyes": "keep-target (eye_protection default)",
    "ears": "generate-if-visible",
    "hair_headwear": "keep-target, composited OVER the likeness",
    "expression_pose_theme": "keep-target (drives prompt_context)",
}


def _face_geometry_reads(points: np.ndarray) -> dict:
    """Cheap, deterministic reads off the 478-point mesh: profile yaw proxy and
    mouth-openness (the Luffy-grin stressor for the triangle warp)."""
    nose = points[_LM_NOSE_TIP]
    left = points[_LM_FACE_LEFT]
    right = points[_LM_FACE_RIGHT]
    d_left = float(np.linalg.norm(nose - left))
    d_right = float(np.linalg.norm(nose - right))
    yaw_asymmetry = abs(d_left - d_right) / max(1.0, d_left + d_right)  # 0 frontal â†’ ~0.5 profile
    mouth_w = float(np.linalg.norm(points[_LM_MOUTH_LEFT] - points[_LM_MOUTH_RIGHT]))
    mouth_open = float(np.linalg.norm(points[_LM_LIP_UPPER_INNER] - points[_LM_LIP_LOWER_INNER]))
    return {
        "yaw_asymmetry": round(yaw_asymmetry, 4),
        "mouth_open_ratio": round(mouth_open / max(1.0, mouth_w), 4),
    }


def _thorough_face_checks(root: Path, image: Image.Image, face_entry: dict) -> dict:
    """The founder's deep-scrutiny pass: re-detect the face at 2x scale and
    measure landmark agreement (is the geometry STABLE, or did the detector
    guess?), then ask the semantic parser for occlusion truth over the eye
    line (the Gojo-blindfold case). Effort over speed â€” this runs before any
    edit so the system provably understood the face it is about to work on."""
    checks: dict = {}
    x1, y1, x2, y2 = face_entry["box"]
    side = max(x2 - x1, y2 - y1)
    pad = int(side * 0.35)
    crop_box = (max(0, x1 - pad), max(0, y1 - pad),
                min(image.width, x2 + pad), min(image.height, y2 + pad))
    crop = image.crop(crop_box)
    # 1. geometry stability: detect again on a 2x upscale of the face crop and
    # compare normalized landmark positions â€” big drift = unstable geometry.
    try:
        big = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
        face_a, _, _, _ = _detect_face(root, crop, 0.2, 0)
        face_b, _, _, _ = _detect_face(root, big, 0.2, 0)
        pa = np.asarray(face_a["landmarks_xy"], dtype=np.float32) / max(1, crop.width)
        pb = np.asarray(face_b["landmarks_xy"], dtype=np.float32) / max(1, big.width)
        drift = float(np.mean(np.linalg.norm(pa - pb, axis=1)))
        stability = max(0.0, 1.0 - drift * 20.0)  # ~0.01 normalized drift â†’ 0.8
        checks["geometry_stability"] = round(stability, 3)
        if stability < 0.6:
            checks["geometry_warning"] = ("landmarks disagree across scales â€” the "
                                          "detector is guessing; prefer the zone route "
                                          "with a reviewed mask")
    except Exception as exc:
        checks["geometry_stability"] = None
        checks["geometry_warning"] = f"rescale re-detect failed: {exc}"
    # 2. occlusion truth from the semantic parser (real photos; anime falls
    # back to the eval-only parser inside prepare â€” here we only report).
    try:
        crop512 = crop.resize((512, 512), Image.Resampling.LANCZOS)
        labels, _, parse_meta = _run_selfie_multiclass(root, crop512)
        hair_like = np.isin(labels, (1,))  # selfie multiclass: 1 = hair
        upper = hair_like[: labels.shape[0] // 2, :]
        checks["upper_face_hair_coverage"] = round(float(upper.mean()), 3)
        if float(upper.mean()) > 0.35:
            checks["occlusion_note"] = ("heavy hair/headwear over the upper face â€” "
                                        "forehead stays target-authentic; expect the "
                                        "plan's keep-headwear branch")
        checks["parser"] = parse_meta.get("model", "selfie_multiclass")
    except Exception as exc:
        checks["parser"] = f"unavailable ({exc})"
    return checks


def _recommend_lane(face_entry: dict) -> str:
    """Map the verdict + flags to the lane ladder (docs/FACE_OPS.md)."""
    flags = " ".join(face_entry.get("flags", []))
    if face_entry["verdict"] == "refuse":
        return "none â€” fix the refusal reason first (upscale / different image)"
    if "extreme_expression" in flags:
        return "quality lane v2 multipass, CPU-seed finish, low mesh strength; review closely"
    if "strong_profile" in flags:
        return "quality lane v2 with eye_source=target; zone route as backup"
    if "small_face" in flags:
        return "upscale the target first (image.refine), then quality lane or zone route"
    return "quality lane (v2 proven / v3 guided when hardware-approved); auto route for quick drafts"


def analyze_image(root: Path, image_path: Path, min_confidence: float = 0.35,
                  min_face_px: int = 64, thorough: bool = False) -> dict:
    """Examine an upload: every face, where the belt can and can't operate, and
    the per-face feature plan. Never edits anything. thorough=True adds the
    founder's deep-scrutiny pass (scale-stability + occlusion truth + lane
    recommendation) â€” effort spent BEFORE the edit, recorded with timing."""
    started = time.monotonic()
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    faces = []
    try:
        _, _, _, total = _detect_face(root, image, min_confidence, 0)
    except RuntimeError as exc:
        return {
            "image": str(image_path), "size": list(image.size), "faces": [],
            "operable_faces": 0,
            "verdict": "refuse",
            "reason": f"no face found at confidence {min_confidence}: {exc}",
            "feature_plan_law": FEATURE_PLAN_DEFAULT,
        }
    for index in range(total):
        face, _, _, _ = _detect_face(root, image, min_confidence, index)
        points = np.asarray(face["landmarks_xy"], dtype=np.float32)
        x1, y1, x2, y2 = [float(v) for v in face["bbox_xyxy"]]
        side = max(x2 - x1, y2 - y1)
        reads = _face_geometry_reads(points)
        flags = []
        if side < min_face_px:
            verdict = "refuse"
            flags.append(f"too_small ({side:.0f}px < {min_face_px}px) â€” upscale first or zone route")
        else:
            verdict = "operable"
            if side < min_face_px * 1.5:
                verdict = "operable_with_care"
                flags.append("small_face â€” expect soft detail; consider upscaling the target first")
            if reads["yaw_asymmetry"] > 0.28:
                verdict = "operable_with_care"
                flags.append("strong_profile â€” mesh warp strains; keep eye_source=target")
            if reads["mouth_open_ratio"] > 0.55:
                verdict = "operable_with_care"
                flags.append("extreme_expression â€” the Luffy-grin case: lower "
                             "mesh_identity_strength, use the multipass lane, review closely")
        plan = dict(FEATURE_PLAN_DEFAULT)
        if verdict == "refuse":
            plan = {"all": "do-not-operate (see flags)"}
        faces.append({
            "index": index,
            "box": [round(x1), round(y1), round(x2), round(y2)],
            "side_px": round(side),
            "confidence_floor": min_confidence,
            **reads,
            "verdict": verdict,
            "flags": flags,
            "feature_plan": plan,
        })
    operable = [f for f in faces if f["verdict"] in ("operable", "operable_with_care")]
    if thorough:
        for face_entry in faces:
            if face_entry["verdict"] != "refuse":
                face_entry["thorough"] = _thorough_face_checks(root, image, face_entry)
            face_entry["recommended_lane"] = _recommend_lane(face_entry)
    return {
        "image": str(image_path), "size": list(image.size),
        "faces": faces, "operable_faces": len(operable),
        "verdict": ("operable" if any(f["verdict"] == "operable" for f in faces)
                    else "operable_with_care" if operable else "refuse"),
        **({} if operable else {"reason": "every detected face is below the operable bar"}),
        "feature_plan_law": FEATURE_PLAN_DEFAULT,
        "thorough": bool(thorough),
        "analysis_seconds": round(time.monotonic() - started, 2),
    }


def render_report_overview(image_path: Path, report: dict, output: Path) -> Path:
    """One clean overview: numbered boxes, green/yellow/red â€” no mesh spaghetti,
    no infrared parse map. The audit files stay in the zone folder; this is the
    picture a founder can approve at a glance."""
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    colors = {"operable": (52, 211, 153), "operable_with_care": (251, 191, 36),
              "refuse": (248, 113, 113)}
    for face in report.get("faces", []):
        color = colors.get(face["verdict"], (200, 200, 200))
        x1, y1, x2, y2 = face["box"]
        width = max(2, round(max(x2 - x1, y2 - y1) * 0.012))
        draw.rectangle([x1, y1, x2, y2], outline=color, width=width)
        draw.text((x1 + width + 2, y1 + width + 2),
                  f"{face['index']}: {face['verdict']}", fill=color)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
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
    prepare.add_argument(
        "--mesh-geometry-fit",
        choices=("semantic-outline", "target-landmarks", "target-landmarks-core"),
        default="semantic-outline",
        help=(
            "semantic-outline expands a small landmark grid toward the audited "
            "jaw; target-landmarks keeps target feature positions while the "
            "semantic mask owns full-head coverage"
        ),
    )
    prepare.add_argument("--eye-protection", type=float, default=0.55)
    prepare.add_argument("--eye-source", choices=("identity", "target"), default="identity")
    prepare.add_argument("--absent-accessory", action="append", default=[])
    prepare.add_argument("--manual-box", type=_parse_box)
    prepare.add_argument("--canvas-size", type=int, default=512, choices=(512, 640, 768),
                         help="working crop resolution â€” picked by the adapter from the "
                              "examiner's face measurement so large faces keep native detail")
    prepare.add_argument("--exclude-box", type=_parse_box, action="append", default=[])
    composite = sub.add_parser("composite", help="Composite a generated 512px crop through the saved soft zone.")
    composite.add_argument("--zone", type=Path, required=True)
    composite.add_argument("--generated-crop", type=Path, required=True)
    composite.add_argument("--output", type=Path, required=True)
    precondition = sub.add_parser(
        "precondition", help="Build a full-size target-face mold with Carey complexion."
    )
    precondition.add_argument("--zone", type=Path, required=True)
    precondition.add_argument("--output", type=Path, required=True)
    analyze = sub.add_parser("analyze", help="Examine an image: every face, operability, feature plan. Edits nothing.")
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--min-confidence", type=float, default=0.35)
    analyze.add_argument("--min-face-px", type=int, default=64)
    analyze.add_argument("--report", type=Path, help="write the JSON report here")
    analyze.add_argument("--overview", type=Path, help="write the clean overview PNG here")
    analyze.add_argument("--thorough", action="store_true",
                         help="deep scrutiny: scale-stability cross-check, occlusion "
                              "truth, lane recommendation (founder default before edits)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        global CANVAS_SIZE
        CANVAS_SIZE = int(args.canvas_size)
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
            mesh_geometry_fit_mode=args.mesh_geometry_fit,
            eye_protection_strength=args.eye_protection,
            eye_source_mode=args.eye_source,
            absent_accessories=args.absent_accessory,
            manual_box=args.manual_box,
            exclude_boxes=args.exclude_box,
        )
        # Also write JSON to the artifacts folder for scripted callers
        zone_path = Path(record["zone_file"])
        zone_path.with_suffix(".record.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        print(json.dumps(record, indent=2))
    elif args.command == "analyze":
        report = analyze_image(args.root, args.input,
                               min_confidence=args.min_confidence,
                               min_face_px=args.min_face_px,
                               thorough=args.thorough)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.overview:
            render_report_overview(args.input, report, args.overview)
        print(json.dumps(report, indent=2))
        return 0 if report["operable_faces"] > 0 else 3
    elif args.command == "precondition":
        output = precondition_complexion_crop(args.zone, args.output)
        print(output)
    else:
        output = composite_generated(args.zone, args.generated_crop, args.output)
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
