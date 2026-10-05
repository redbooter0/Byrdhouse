"""Identity-preserving still belt for ByrdHouse.

The belt deliberately keeps scene generation and identity correction separate:
ComfyUI creates the target still, ReActor swaps only the detected face, and the
ReActor masking helper pastes the corrected face back through a SAM mask.  A
small local InsightFace examiner then scores every candidate and records the
face box, forehead geometry, hairline signal, and embedding score.  The best
candidate is copied to the Studio library with a JSON report beside it.

This module is local-only and is intended for the operator's own face or
consented references.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
import urllib.parse
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

MEASUREMENT_VERSION = 'carey-features-v2-connected-head-hair'


def measurement_binding(config):
    """Freeze examiner code and existing local weights for queued evidence."""
    directory = Path(__file__).resolve().parent
    code = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ('identity_belt.py', 'anime_view_review.py',
                         'anime_continuity.py', 'render_belt_report.py')}
    models = Path(config['comfy_dir']).resolve() / 'models'
    paths = [models / 'face_parsing/model.safetensors', models / 'face_parsing/config.json',
             models / 'face_parsing/preprocessor_config.json',
             models / 'landmarks/fan2_68_landmark.onnx']
    paths.extend(sorted((models / 'insightface/models/buffalo_l').glob('*.onnx')))
    weights = {str(path.relative_to(models)).replace('\\', '/'):
               hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
               for path in paths}
    return {'measurement_version': MEASUREMENT_VERSION, 'code_sha256': code,
            'model_sha256': weights}


class BeltError(RuntimeError):
    """A preflight, ComfyUI, or face-examination failure."""


@dataclass
class FaceRecord:
    path: Path
    image_width: int
    image_height: int
    bbox: tuple[float, float, float, float]
    embedding: object
    metrics: dict

    def public(self) -> dict:
        return {
            "file": str(self.path),
            "image_size": [self.image_width, self.image_height],
            "bbox": [round(float(value), 2) for value in self.bbox],
            "metrics": self.metrics,
        }


class IdentityBelt:
    """Run the proven ReActor + SAM mask lane and choose by measured likeness."""

    def __init__(self, config: dict, client):
        self.config = config
        self.client = client
        self.comfy_dir = Path(config["comfy_dir"]).resolve()
        self.comfy_input = self.comfy_dir / "input"
        self.output_dir = Path(config["output_dir"]).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._examiner = None
        self._face_parser = None
        self._landmark_session = None
        self._lock = __import__("threading").Lock()
        self._inspection_cache = OrderedDict()
        self._inspection_cache_lock = __import__("threading").Lock()

    def _load_examiner(self):
        if self._examiner is not None:
            return self._examiner
        try:
            import cv2
            import insightface
            from insightface.app import FaceAnalysis
        except Exception as exc:  # pragma: no cover - depends on the runtime image stack
            raise BeltError(f"Identity examiner is unavailable: {exc}") from exc
        root = self.comfy_dir / "models" / "insightface"
        if not (root / "models" / "buffalo_l").is_dir():
            raise BeltError(f"InsightFace buffalo_l models are missing under {root}")
        try:
            examiner = FaceAnalysis(
                name="buffalo_l",
                root=str(root),
                providers=["CPUExecutionProvider"],
            )
            examiner.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as exc:
            raise BeltError(f"InsightFace could not initialize: {exc}") from exc
        self._examiner = (examiner, cv2, insightface)
        return self._examiner

    def _load_face_parser(self):
        """Load the local SegFormer face parser once, on CPU.

        The parser is an examiner only; generation stays in ComfyUI on the
        RX 7900 XT. Keeping this model on CPU avoids competing with a live
        diffusion job for VRAM and works with the bundled Windows runtime.
        """
        if self._face_parser is not None:
            return self._face_parser
        model_dir = self.comfy_dir / "models" / "face_parsing"
        if not (model_dir / "model.safetensors").is_file():
            raise BeltError(f"Face parsing model is missing under {model_dir}")
        try:
            from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor
            model = AutoModelForSemanticSegmentation.from_pretrained(str(model_dir))
            model.to("cpu")
            model.eval()
            processor = SegformerImageProcessor.from_pretrained(str(model_dir))
        except Exception as exc:  # pragma: no cover - depends on the local runtime
            raise BeltError(f"Face parser could not initialize: {exc}") from exc
        self._face_parser = (model, processor)
        return self._face_parser

    def _load_landmarks(self):
        """Load the local 68-point landmark model with a CPU provider."""
        if self._landmark_session is not None:
            return self._landmark_session
        model_path = self.comfy_dir / "models" / "landmarks" / "fan2_68_landmark.onnx"
        if not model_path.is_file():
            raise BeltError(f"68-point landmark model is missing: {model_path}")
        try:
            import onnxruntime
            self._landmark_session = onnxruntime.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # pragma: no cover - depends on the local runtime
            raise BeltError(f"Landmark examiner could not initialize: {exc}") from exc
        return self._landmark_session

    @staticmethod
    def _read_image(path: Path, cv2, data=None):
        import numpy as np

        encoded = np.frombuffer(data, dtype=np.uint8) if data is not None else np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise BeltError(f"Cannot read image: {path}")
        return image

    @staticmethod
    def _hairline_metrics(image, bbox, keypoints, cv2):
        """Estimate the visible forehead and hairline without changing pixels."""
        import numpy as np

        height, width = image.shape[:2]
        left, top, right, bottom = [float(x) for x in bbox]
        face_w = max(1.0, right - left)
        face_h = max(1.0, bottom - top)
        kps = np.asarray(keypoints, dtype=np.float32) if keypoints is not None else np.zeros((0, 2), dtype=np.float32)
        if len(kps) >= 2:
            eye_y = float(np.mean(kps[:2, 1]))
            eye_distance = float(np.linalg.norm(kps[1] - kps[0]) / face_w)
        else:
            eye_y = top + face_h * 0.40
            eye_distance = 0.0
        mouth_width = 0.0
        if len(kps) >= 5:
            mouth_width = float(np.linalg.norm(kps[4] - kps[3]) / face_w)
        forehead_ratio = max(0.0, min(1.5, (eye_y - top) / face_h))

        # A broad strip above the eyes captures the dark hairline/afro signal.
        # It is a measurement only; illumination is retained in the report so a
        # reviewer can distinguish a low signal from a changed hairstyle.
        x0 = max(0, int(left - 0.30 * face_w))
        x1 = min(width, int(right + 0.30 * face_w))
        y0 = max(0, int(top - 0.45 * face_h))
        y1 = min(height, int(eye_y + 0.05 * face_h))
        if x1 <= x0 or y1 <= y0:
            hairline_dark_fraction = 0.0
            hairline_mean_luma = 255.0
        else:
            gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
            hairline_dark_fraction = float(np.mean(gray < 82))
            hairline_mean_luma = float(np.mean(gray))

        return {
            "face_area_ratio": round((face_w * face_h) / max(1, width * height), 6),
            "face_aspect_ratio": round(face_w / face_h, 6),
            "eye_distance_ratio": round(eye_distance, 6),
            "mouth_width_ratio": round(mouth_width, 6),
            "forehead_ratio": round(forehead_ratio, 6),
            "hairline_dark_fraction": round(hairline_dark_fraction, 6),
            "hairline_mean_luma": round(hairline_mean_luma, 3),
        }

    def _landmark_metrics(self, image, bbox, cv2):
        """Return a normalized 68-point face outline for pose-tolerant checks."""
        import numpy as np

        session = self._load_landmarks()
        height, width = image.shape[:2]
        left, top, right, bottom = [float(x) for x in bbox]
        face_w = max(1.0, right - left)
        face_h = max(1.0, bottom - top)
        side = max(32.0, max(face_w, face_h) * 1.45)
        center_x = (left + right) * 0.5
        center_y = (top + bottom) * 0.5
        x0 = int(round(center_x - side * 0.5))
        y0 = int(round(center_y - side * 0.5))
        x1 = x0 + int(round(side))
        y1 = y0 + int(round(side))
        pad_left, pad_top = max(0, -x0), max(0, -y0)
        pad_right, pad_bottom = max(0, x1 - width), max(0, y1 - height)
        crop = image[max(0, y0):min(height, y1), max(0, x0):min(width, x1)]
        if crop.size == 0:
            return {}
        if pad_left or pad_top or pad_right or pad_bottom:
            crop = cv2.copyMakeBorder(
                crop, pad_top, pad_bottom, pad_left, pad_right,
                cv2.BORDER_REPLICATE,
            )
        crop = cv2.resize(crop, (256, 256), interpolation=cv2.INTER_AREA)
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        tensor = crop.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        input_name = session.get_inputs()[0].name
        raw = session.run(None, {input_name: tensor})[0][0]
        points_256 = np.asarray(raw[:, :2], dtype=np.float32) * 4.0
        points = points_256 / 256.0 * side + np.array([x0, y0], dtype=np.float32)
        normalized = (points - np.array([left, top], dtype=np.float32)) / np.array([face_w, face_h], dtype=np.float32)
        if not np.isfinite(normalized).all():
            return {}
        jaw = normalized[:17]
        brows = normalized[17:27]
        return {
            "landmark_confidence": round(float(np.mean(raw[:, 2])), 6),
            "landmarks_signature": [round(float(value), 5) for value in normalized.reshape(-1)],
            "face_outline_signature": [round(float(value), 5) for value in jaw.reshape(-1)],
            "jaw_width_ratio": round(float(np.max(jaw[:, 0]) - np.min(jaw[:, 0])), 6),
            "jaw_height_ratio": round(float(np.max(jaw[:, 1]) - np.min(jaw[:, 1])), 6),
            "brow_span_ratio": round(float(np.max(brows[:, 0]) - np.min(brows[:, 0])), 6),
        }

    def _parsing_metrics(self, image, bbox, keypoints, cv2, *, illustrated=False):
        """Measure hair, brows, and forehead regions from the local parser."""
        import numpy as np
        import torch
        from PIL import Image

        model, processor = self._load_face_parser()
        height, width = image.shape[:2]
        left, top, right, bottom = [float(x) for x in bbox]
        face_w = max(1.0, right - left)
        face_h = max(1.0, bottom - top)
        x0 = max(0, int(round(left - 0.65 * face_w)))
        y0 = max(0, int(round(top - 0.95 * face_h)))
        x1 = min(width, int(round(right + 0.65 * face_w)))
        y1 = min(height, int(round(bottom + 0.25 * face_h)))
        if x1 <= x0 or y1 <= y0:
            return {}
        roi = image[y0:y1, x0:x1]
        rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
        inputs = processor(images=Image.fromarray(rgb), return_tensors="pt")
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            logits = torch.nn.functional.interpolate(
                logits, size=(roi.shape[0], roi.shape[1]),
                mode="bilinear", align_corners=False,
            )
            segmentation = logits.argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
        # The upstream jonathandinu parser is trained on photographs.  On the
        # approved cel-shaded Carey anchor it correctly captures the outer afro
        # silhouette, but calls most of it ``hat`` (class 14), leaving the
        # literal ``hair`` class nearly empty.  For a continuity review the
        # relevant cue is the visible head-hair silhouette.  Treat the two
        # labels as one *review-only* silhouette for an explicitly illustrated
        # frame while preserving their separate areas in the report. For a
        # photo, class 14 is still headwear and cannot count as hair.
        literal_hair = segmentation == 13
        parser_headwear = segmentation == 14
        raw_hair = np.logical_or(literal_hair, parser_headwear) if illustrated else literal_hair
        skin = segmentation == 1
        brows = np.logical_or(segmentation == 6, segmentation == 7)
        rel_left, rel_top = left - x0, top - y0
        rel_right, rel_bottom = right - x0, bottom - y0
        kps = np.asarray(keypoints, dtype=np.float32) if keypoints is not None else np.zeros((0, 2), dtype=np.float32)
        eye_y = float(np.mean(kps[:2, 1])) if len(kps) >= 2 else top + face_h * 0.40
        eye_y = max(float(y0), min(float(y1), eye_y)) - y0
        central_l = max(0, int(round(rel_left + 0.12 * face_w)))
        central_r = min(roi.shape[1], int(round(rel_right - 0.12 * face_w)))
        # Reuse OpenCV's semantic connected components. A detached eyebrow
        # patch mislabeled as hair must not become the forehead boundary.
        # Select the component with the strongest contact in the detected
        # forehead cap; never dilate/bridge labels or manufacture a boundary.
        cap_bottom = max(0, min(int(round(eye_y)),
                               int(round(rel_top + 0.05 * face_h))))
        count, component_ids, stats, _ = cv2.connectedComponentsWithStats(
            raw_hair.astype(np.uint8), connectivity=8)
        seed_ids, seed_counts = np.unique(
            component_ids[:cap_bottom, central_l:central_r], return_counts=True)
        eligible = [(int(amount), int(stats[int(index), cv2.CC_STAT_AREA]), int(index))
                    for index, amount in zip(seed_ids, seed_counts)
                    if index and stats[int(index), cv2.CC_STAT_AREA] >= 0.03 * face_w * face_h]
        head_component = max(eligible)[2] if eligible else None
        hair = component_ids == head_component if head_component is not None else np.zeros_like(raw_hair)
        excluded_pixels = int(np.count_nonzero(raw_hair & ~hair))
        upper = hair[:max(1, int(round(eye_y))), central_l:central_r]
        hairline_columns = []
        hairline_points = []
        if upper.size and len(kps) >= 2:
            for column in range(upper.shape[1]):
                # The hairline is the hair-to-skin boundary, not the first
                # (highest) hair pixel. Both arrays use the same ROI origin.
                column_skin = skin[:upper.shape[0], central_l + column]
                ys = np.flatnonzero(upper[:-1, column] & column_skin[1:])
                if len(ys):
                    boundary = float(ys[-1] + 1)
                    hairline_columns.append(boundary)
                    hairline_points.append([central_l + column + x0, round(boundary + y0, 2)])
        if hairline_columns:
            hairline_y = float(np.median(hairline_columns))
            hairline_y_ratio = (hairline_y - rel_top) / face_h
            hairline_coverage = len(hairline_columns) / max(1, upper.shape[1])
        else:
            hairline_y_ratio = None
            hairline_coverage = 0.0
        hair_points = np.argwhere(hair)
        if len(hair_points):
            hair_top, hair_left = hair_points.min(axis=0)
            hair_bottom, hair_right = hair_points.max(axis=0)
            hair_width_ratio = (hair_right - hair_left + 1) / face_w
            hair_height_ratio = (hair_bottom - hair_top + 1) / face_h
            hair_bounds_pixels = [int(hair_left + x0), int(hair_top + y0),
                                  int(hair_right + x0 + 1), int(hair_bottom + y0 + 1)]
        else:
            hair_top = hair_left = hair_bottom = hair_right = 0
            hair_width_ratio = hair_height_ratio = 0.0
            hair_bounds_pixels = None
        forehead_top = max(0, int(round(rel_top - 0.05 * face_h)))
        forehead_bottom = min(roi.shape[0], int(round(eye_y - 0.02 * face_h)))
        forehead = segmentation[forehead_top:max(forehead_top + 1, forehead_bottom),
                                max(0, int(round(rel_left))):min(roi.shape[1], int(round(rel_right)))]
        brow_points = np.argwhere(brows)
        brow_y_ratio = (float(np.median(brow_points[:, 0])) - rel_top) / face_h if len(brow_points) else 0.0
        skin_pixels = rgb[skin]
        if len(skin_pixels) >= 100:
            median_rgb = np.median(skin_pixels, axis=0)
            skin_median_rgb = [int(round(value)) for value in median_rgb]
            skin_median_luma = round(float(np.dot(median_rgb, [0.2126, 0.7152, 0.0722])), 3)
        else:
            skin_median_rgb = None
            skin_median_luma = None
        return {
            'measurement_version': MEASUREMENT_VERSION,
            "parsing_model": "jonathandinu/face-parsing SegFormer",
            "hair_silhouette_mode": ("hair_plus_hat_for_illustrated_review" if illustrated
                                     else "literal_hair_only"),
            "hair_area_ratio": round(float(np.mean(literal_hair)), 6),
            "headwear_area_ratio": round(float(np.mean(parser_headwear)), 6),
            "raw_hair_silhouette_area_ratio": round(float(np.mean(raw_hair)), 6),
            "hair_silhouette_area_ratio": round(float(np.mean(hair)), 6),
            'hair_component_selection': 'semantic_component_touching_detected_forehead_cap',
            'hair_components_excluded': max(0, count - 1 - int(head_component is not None)),
            'hair_pixels_excluded': excluded_pixels,
            "skin_area_ratio": round(float(np.mean(skin)), 6),
            "brow_area_ratio": round(float(np.mean(brows)), 6),
            "hairline_y_ratio": round(float(hairline_y_ratio), 6) if hairline_y_ratio is not None else None,
            "hairline_y_pixels": round(float(hairline_y + y0), 2) if hairline_columns else None,
            "hairline_points": hairline_points,
            "forehead_height_ratio": round((eye_y - hairline_y) / face_h, 6) if hairline_columns else None,
            "hairline_coverage": round(float(hairline_coverage), 6),
            "hair_width_ratio": round(float(hair_width_ratio), 6),
            "hair_height_ratio": round(float(hair_height_ratio), 6),
            "hair_bounds_pixels": hair_bounds_pixels,
            "forehead_skin_fraction": round(float(np.mean(forehead == 1)) if forehead.size else 0.0, 6),
            "skin_median_rgb": skin_median_rgb,
            "skin_median_luma": skin_median_luma,
            "brow_y_ratio": round(float(brow_y_ratio), 6),
        }

    def inspect(self, path: Path, *, illustrated=False) -> FaceRecord:
        examiner, cv2, _ = self._load_examiner()
        path = Path(path).resolve()
        if not path.is_file():
            raise BeltError(f"Image does not exist: {path}")
        # The approved anchor is inspected for every generated still. Cache
        # only an exact file hash under the current examiner instance; changed
        # or replaced images are always re-examined.
        source_bytes = path.read_bytes()
        digest = hashlib.sha256(source_bytes).hexdigest()
        cache_key = (str(path), digest, bool(illustrated), MEASUREMENT_VERSION)
        with self._inspection_cache_lock:
            cached = self._inspection_cache.get(cache_key)
            if cached is not None:
                self._inspection_cache.move_to_end(cache_key)
                return cached
        image = self._read_image(path, cv2, source_bytes)
        faces = examiner.get(image)
        pad_offset = 0
        if not faces:
            # Close-up references can put the hair or chin against the image
            # edge, which makes the detector reject an otherwise usable face.
            # Retry on a replicated border, then map the box/keypoints back to
            # the original pixels for all geometry checks.
            pad_offset = max(64, int(max(image.shape[:2]) * 0.25))
            padded = cv2.copyMakeBorder(image, pad_offset, pad_offset, pad_offset, pad_offset, cv2.BORDER_REPLICATE)
            faces = examiner.get(padded)
        if not faces:
            raise BeltError(f"No face detected in {path.name}")
        face = max(faces, key=lambda item: float((item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1])))
        bbox = tuple(float(value) - pad_offset for value in face.bbox)
        keypoints = getattr(face, "kps", None)
        if keypoints is not None and pad_offset:
            keypoints = keypoints - pad_offset
        metrics = self._hairline_metrics(image, bbox, keypoints, cv2)
        try:
            metrics.update(self._landmark_metrics(image, bbox, cv2))
        except Exception as exc:  # keep the belt usable if an optional examiner is unavailable
            metrics["landmark_metrics_error"] = str(exc)[:240]
        try:
            metrics.update(self._parsing_metrics(image, bbox, keypoints, cv2,
                                                 illustrated=illustrated))
        except Exception as exc:  # keep the belt usable if an optional examiner is unavailable
            metrics["parsing_metrics_error"] = str(exc)[:240]
        metrics["detection_confidence"] = round(float(getattr(face, "det_score", 0.0)), 6)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise BeltError(f"Image changed during identity inspection: {path.name}")
        record = FaceRecord(path, int(image.shape[1]), int(image.shape[0]), bbox, face.normed_embedding, metrics)
        with self._inspection_cache_lock:
            self._inspection_cache[cache_key] = record
            self._inspection_cache.move_to_end(cache_key)
            while len(self._inspection_cache) > 32:
                self._inspection_cache.popitem(last=False)
        return record

    @staticmethod
    def _similarity(reference: FaceRecord, candidate: FaceRecord) -> float:
        import numpy as np

        value = float(np.dot(reference.embedding, candidate.embedding))
        return max(0.0, min(1.0, value))

    @staticmethod
    def _geometry(reference: FaceRecord, candidate: FaceRecord, *, illustrated=False) -> dict:
        keys = (
            "face_area_ratio",
            "face_aspect_ratio",
            "eye_distance_ratio",
            "mouth_width_ratio",
            "forehead_ratio",
            "hairline_dark_fraction",
        )
        delta = {}
        for key in keys:
            if key in reference.metrics and key in candidate.metrics:
                delta[key] = round(abs(float(reference.metrics[key]) - float(candidate.metrics[key])), 6)
        for key in ("hairline_y_ratio", "hairline_coverage", "hair_width_ratio", "hair_height_ratio",
                    "hair_silhouette_area_ratio", "forehead_skin_fraction", "forehead_height_ratio",
                    "brow_y_ratio", "skin_median_luma"):
            if reference.metrics.get(key) is not None and candidate.metrics.get(key) is not None:
                delta[key] = round(abs(float(reference.metrics[key]) - float(candidate.metrics[key])), 6)
        if (reference.metrics.get('skin_median_luma') is not None
                and candidate.metrics.get('skin_median_luma') is not None):
            delta['skin_luma_shift'] = round(
                float(candidate.metrics['skin_median_luma']) -
                float(reference.metrics['skin_median_luma']), 6)
        ref_signature = reference.metrics.get("face_outline_signature")
        candidate_signature = candidate.metrics.get("face_outline_signature")
        if isinstance(ref_signature, list) and isinstance(candidate_signature, list) and len(ref_signature) == len(candidate_signature):
            import numpy as np
            ref_points = np.asarray(ref_signature, dtype=np.float32).reshape(-1, 2)
            candidate_points = np.asarray(candidate_signature, dtype=np.float32).reshape(-1, 2)
            delta["face_outline_error"] = round(float(np.mean(np.linalg.norm(ref_points - candidate_points, axis=1))), 6)
        else:
            delta["face_outline_error"] = None
        # These are conservative review screens, not calibrated identity proof.
        # Missing segmentation/landmarks must not turn into a passing result.
        measurable = all(float(record.metrics.get("hairline_coverage", 0)) >= 0.25
                         for record in (reference, candidate))
        if illustrated:
            # Calibrated only as a conservative same-view review screen from
            # the approved portrait, a faithful local redraw, and a rejected
            # redraw.  A changed head pose is inconclusive, not identity drift.
            comparable = (delta.get("face_aspect_ratio", 99) <= 0.12
                          and delta.get("eye_distance_ratio", 99) <= 0.10)
            delta["review_scope"] = ("same_view_illustrated_continuity"
                                     if comparable else "different_view_requires_visual_review")
            delta['skin_lightening_warning'] = bool(
                comparable and delta.get('skin_luma_shift', 0) > 25)
            delta["forehead_within_gate"] = bool(
                comparable and measurable
                and delta.get("forehead_height_ratio", 99) <= 0.10
                and delta.get("hairline_y_ratio", 99) <= 0.10)
            delta["hair_within_gate"] = bool(
                comparable and measurable
                and delta.get("hair_width_ratio", 99) <= 0.16
                and delta.get("hair_height_ratio", 99) <= 0.16)
            outline_limit = 0.05
        else:
            delta["forehead_within_gate"] = bool(measurable and delta.get("forehead_height_ratio", 99) <= 0.20)
            delta["hair_within_gate"] = bool(measurable and delta.get("hair_width_ratio", 99) <= 0.60)
            outline_limit = 0.24
        delta["outline_within_gate"] = bool(
            (not illustrated or delta["review_scope"] == "same_view_illustrated_continuity")
            and delta["face_outline_error"] is not None and delta["face_outline_error"] <= outline_limit
            and all(float(record.metrics.get("landmark_confidence", 0)) >= 0.5 for record in (reference, candidate)))
        return delta

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
        return cleaned.strip("_")[:64] or "belt"

    def _input_copy(self, run_id: str, target: Path, reference: Path) -> tuple[str, str]:
        folder = Path("ByrdHouse") / "belt" / run_id
        destination = self.comfy_input / folder
        destination.mkdir(parents=True, exist_ok=True)
        target_name = "target" + target.suffix.lower()
        reference_name = "reference" + reference.suffix.lower()
        shutil.copy2(target, destination / target_name)
        shutil.copy2(reference, destination / reference_name)
        return (str(folder / target_name).replace("\\", "/"), str(folder / reference_name).replace("\\", "/"))

    def _graph(self, target_name: str, reference_name: str, run_id: str, include_face_model: bool = True) -> tuple[dict, dict]:
        graph = {
            "target": {"class_type": "LoadImage", "inputs": {"image": target_name}},
            "reference": {"class_type": "LoadImage", "inputs": {"image": reference_name}},
        }
        candidates = {
            "direct": {"restore": "none", "visibility": 1.0, "dilation": 10, "blur": 9, "face_model": False},
            "restored": {"restore": self.config.get("belt_restore_model", "GFPGANv1.4.pth"),
                         "visibility": float(self.config.get("belt_restore_visibility", 0.55)),
                         "dilation": 10, "blur": 9, "face_model": False},
        }
        # The additional blur/mean-face candidates did not improve the tested
        # likeness. Keep them opt-in rather than paying for four passes each time.
        extended = self.config.get("belt_extended_candidates", False)
        if extended:
            candidates["smooth"] = {"restore": "GFPGANv1.4.pth", "visibility": 0.55, "dilation": 0, "blur": 18, "face_model": False}
        if extended and include_face_model and (self.comfy_dir / "models" / "reactor" / "faces" / "carey_belt_mean.safetensors").is_file():
            candidates["multi_reference"] = {"restore": "GFPGANv1.4.pth", "visibility": 0.55, "dilation": 10, "blur": 18, "face_model": True}
        save_nodes = {}
        for index, (label, candidate) in enumerate(candidates.items(), start=1):
            suffix = str(index)
            swap_inputs = {
                "enabled": True,
                "input_image": ["target", 0],
                "swap_model": "inswapper_128.onnx",
                "facedetection": "retinaface_resnet50",
                "face_restore_model": candidate["restore"],
                "face_restore_visibility": candidate["visibility"],
                "codeformer_weight": 0.5,
                "detect_gender_input": "no",
                "detect_gender_source": "no",
                "input_faces_index": "0",
                "source_faces_index": "0",
                "console_log_level": 0,
            }
            if candidate["face_model"]:
                model_id = f"model{suffix}"
                graph[model_id] = {"class_type": "ReActorLoadFaceModel", "inputs": {"face_model": "carey_belt_mean.safetensors"}}
                swap_inputs["face_model"] = [model_id, 0]
            else:
                swap_inputs["source_image"] = ["reference", 0]
            swap_id = f"swap{suffix}"
            mask_id = f"mask{suffix}"
            save_id = f"save{suffix}"
            graph[swap_id] = {"class_type": "ReActorFaceSwap", "inputs": swap_inputs}
            graph[mask_id] = {
                "class_type": "ReActorMaskHelper",
                "inputs": {
                    "image": ["target", 0], "swapped_image": [swap_id, 0],
                    "bbox_model_name": "bbox/face_yolov8m.pt", "bbox_threshold": 0.5,
                    "bbox_dilation": candidate["dilation"], "bbox_crop_factor": 3.0,
                    "bbox_drop_size": 10, "sam_model_name": "sam_vit_b_01ec64.pth",
                    "sam_dilation": 0, "sam_threshold": 0.93, "bbox_expansion": 0,
                    "mask_hint_threshold": 0.7, "mask_hint_use_negative": "False",
                    "morphology_operation": "close", "morphology_distance": 1,
                    "blur_radius": candidate["blur"], "sigma_factor": 1.0,
                },
            }
            graph[save_id] = {
                "class_type": "SaveImage",
                "inputs": {"images": [mask_id, 0], "filename_prefix": f"ByrdHouse/belt/{run_id}/{label}"},
            }
            save_nodes[label] = save_id
        return graph, save_nodes

    @staticmethod
    def _write_submission(path: Path, card: dict):
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(card, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _workflow_sha256(graph: dict) -> str:
        data = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _check_stop(stop):
        if stop is not None and stop.is_set():
            raise BeltError("Studio stopped; inspect the submitted identity belt before retrying.")

    def _run_graph(self, graph: dict, save_nodes: dict, *, resume_prompt_id=None,
                   submitted=None, stop=None, submission_path=None, submission=None) -> dict[str, bytes]:
        self._check_stop(stop)
        prompt_id = resume_prompt_id
        if prompt_id is None:
            if submission_path is not None:
                submission["state"] = "submitting"
                self._write_submission(submission_path, submission)
            response = self.client.request("/prompt", {"prompt": graph, "client_id": "byrdhouse-identity-belt"})
            prompt_id = response.get("prompt_id")
            if not isinstance(prompt_id, str) or not prompt_id or response.get("node_errors"):
                if submission_path is not None:
                    submission["state"] = "rejected"
                    self._write_submission(submission_path, submission)
                raise BeltError(f"ComfyUI rejected the identity belt: {json.dumps(response)[:1500]}")
        elif not isinstance(prompt_id, str) or not prompt_id:
            raise BeltError("Identity belt resume requires an existing prompt ID.")
        # Persist the backend ID before a callback, history wait or output fetch
        # can fail. A restart can reuse this submission even if SQLite was not
        # updated before the process stopped.
        if submission_path is not None:
            submission.update(prompt_id=prompt_id, state="submitted")
            self._write_submission(submission_path, submission)
        if submitted is not None:
            submitted(prompt_id)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            self._check_stop(stop)
            try:
                history = self.client.request("/history/" + urllib.parse.quote(prompt_id, safe=""))
            except Exception as exc:
                # Observation timeouts do not establish that rendering stopped.
                # Keep monitoring the same ID; never submit another graph.
                if not isinstance(exc, TimeoutError) and "timed out" not in str(exc).lower():
                    raise
                if stop is not None:
                    if stop.wait(0.8):
                        self._check_stop(stop)
                else:
                    time.sleep(0.8)
                continue
            record = history.get(prompt_id)
            if record:
                status = record.get("status", {})
                errors = [entry[1] for entry in status.get("messages", [])
                          if isinstance(entry, list) and len(entry) == 2 and entry[0] in ("execution_error", "execution_interrupted")]
                if errors or status.get("status_str") == "error":
                    detail = errors[0].get("exception_message", "Identity belt failed") if errors and isinstance(errors[0], dict) else "Identity belt failed"
                    raise BeltError(str(detail))
                if status.get("completed"):
                    outputs = record.get("outputs", {})
                    result = {}
                    for label, node_id in save_nodes.items():
                        self._check_stop(stop)
                        entries = outputs.get(node_id, {}).get("images", [])
                        if not entries:
                            raise BeltError(f"ComfyUI did not return the {label} belt candidate")
                        item = entries[0]
                        query = urllib.parse.urlencode({key: item.get(key, "") for key in ("filename", "subfolder", "type")})
                        data = self.client.request("/view?" + query, binary=True)
                        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                            raise BeltError(f"ComfyUI returned a non-PNG {label} candidate")
                        result[label] = data
                    return result
            if stop is not None:
                if stop.wait(0.8):
                    self._check_stop(stop)
            else:
                time.sleep(0.8)
        raise BeltError("Identity belt exceeded 20 minutes; check ComfyUI history")

    def run(self, target: Path, reference: Path, label: str = "belt", *, run_id=None,
            resume_prompt_id=None, submitted=None, stop=None) -> dict:
        started = time.monotonic()
        target = Path(target).resolve()
        reference = Path(reference).resolve()
        with self._lock:
            self._check_stop(stop)
            if run_id is None:
                if resume_prompt_id is not None:
                    raise BeltError("Identity belt resume requires its original run ID.")
                run_id = self._safe_name(label) + "-" + secrets.token_hex(5)
            elif (not isinstance(run_id, str) or not run_id
                  or len(run_id) > 64 or self._safe_name(run_id) != run_id):
                raise BeltError("Identity belt run ID must use at most 64 letters, digits, hyphens or underscores.")
            submission_path = self.output_dir / f"belt-{run_id}.submission.json"
            source_hashes = {"target_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                             "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest()}
            submission = None
            if submission_path.is_file():
                try:
                    submission = json.loads(submission_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise BeltError("Cannot read the saved identity belt submission.") from exc
                if (not isinstance(submission, dict)
                        or submission.get("schema") != "byrdhouse.identity-belt.submission.v1"
                        or submission.get("run_id") != run_id):
                    raise BeltError("Saved identity belt submission does not match this run.")
                if any(submission.get(key) != value for key, value in source_hashes.items()):
                    raise BeltError("Identity belt source changed after submission; review the current image before correcting it.")
                saved_prompt_id = submission.get("prompt_id")
                if resume_prompt_id is None:
                    if not isinstance(saved_prompt_id, str) or not saved_prompt_id:
                        raise BeltError("Identity belt submission is ambiguous; inspect ComfyUI before retrying. No prompt was resubmitted.")
                    resume_prompt_id = saved_prompt_id
                elif saved_prompt_id is not None and saved_prompt_id != resume_prompt_id:
                    raise BeltError("Resume prompt ID does not match the saved identity belt submission.")
                graph, save_nodes = submission.get("workflow"), submission.get("save_nodes")
                if (not isinstance(graph, dict) or not graph or not isinstance(save_nodes, dict)
                        or not save_nodes or any(node not in graph for node in save_nodes.values())
                        or submission.get("workflow_sha256") != self._workflow_sha256(graph)
                        or submission.get("save_nodes_sha256") != self._workflow_sha256(save_nodes)):
                    raise BeltError("Saved identity belt workflow is missing or changed; no prompt was resubmitted.")
            elif resume_prompt_id is not None:
                raise BeltError("Saved identity belt workflow is missing; no prompt was resubmitted.")
            reference_face = self.inspect(reference)
            target_face = self.inspect(target)
            self._check_stop(stop)
            if submission is None:
                target_name, reference_name = self._input_copy(run_id, target, reference)
                # Examination may take several seconds. The submitted copies
                # must match the exact sources recorded before it began.
                copies = {"target_sha256": target_name, "reference_sha256": reference_name}
                if any(hashlib.sha256((self.comfy_input / name).read_bytes()).hexdigest() != source_hashes[key]
                       for key, name in copies.items()):
                    raise BeltError("Identity belt source changed during preparation; review it before retrying.")
                graph, save_nodes = self._graph(target_name, reference_name, run_id)
                submission = {"schema": "byrdhouse.identity-belt.submission.v1",
                              "purpose": "Resume or audit this exact local identity correction without duplicate rendering",
                              "run_id": run_id, "target": str(target), "reference": str(reference),
                              **source_hashes, "workflow": graph, "save_nodes": save_nodes,
                              "workflow_sha256": self._workflow_sha256(graph),
                              "save_nodes_sha256": self._workflow_sha256(save_nodes),
                              "prompt_id": None, "state": "prepared"}
                self._write_submission(submission_path, submission)
            candidates = self._run_graph(graph, save_nodes, resume_prompt_id=resume_prompt_id,
                                         submitted=submitted, stop=stop,
                                         submission_path=submission_path, submission=submission)
            reports = []
            best = None
            for name, data in candidates.items():
                self._check_stop(stop)
                candidate_path = self.output_dir / f"belt-{run_id}-{name}.png"
                candidate_path.write_bytes(data)
                candidate_face = self.inspect(candidate_path)
                similarity = self._similarity(reference_face, candidate_face)
                geometry = self._geometry(reference_face, candidate_face)
                outline_penalty = float(geometry.get("face_outline_error") or 0.0)
                hairline_penalty = float(geometry.get("hairline_y_ratio") or 0.0)
                candidate_score = max(0.0, similarity - 0.18 * outline_penalty - 0.04 * hairline_penalty)
                report = {
                    "name": name,
                    "file": candidate_path.name,
                    "similarity": round(similarity, 6),
                    "candidate_score": round(candidate_score, 6),
                    "selection_score": round(candidate_score, 6),
                    "geometry_delta": geometry,
                    "face": candidate_face.public(),
                }
                reports.append(report)
            # Face-swap restoration removes the small eyes/mouth artifacts that can
            # make a raw ReActor composite look uncanny.  The raw embedding score
            # often gives that direct composite a tiny edge, so use a restoration
            # prior only when the candidates are effectively tied.  A meaningful
            # identity advantage must win over cosmetic smoothing.
            if reports:
                top_similarity = max(float(row["similarity"]) for row in reports)
                direct_score = next(
                    (float(row["candidate_score"]) for row in reports if row["name"] == "direct"),
                    None,
                )
                restoration_bonus = {"restored": 0.022, "smooth": 0.020, "multi_reference": 0.018}
                for report in reports:
                    score_gap = (direct_score - float(report["candidate_score"])) if direct_score is not None else 0.0
                    close_enough = (
                        float(report["similarity"]) >= top_similarity - 0.025
                        and score_gap <= 0.015
                    )
                    bonus = restoration_bonus.get(report["name"], 0.0) if close_enough else 0.0
                    report["selection_score"] = round(float(report["candidate_score"]) + bonus, 6)
                    report["selection_prior"] = round(bonus, 6)
                chosen = max(reports, key=lambda row: (row["selection_score"], row["similarity"]))
                best = {**chosen, "path": self.output_dir / chosen["file"]}
            if best is None:
                raise BeltError("Identity belt produced no candidates")
            selected = self.output_dir / f"belt-{run_id}.png"
            shutil.copy2(best["path"], selected)
            accepted = bool(
                best["similarity"] >= 0.65
                and best["geometry_delta"]["forehead_within_gate"]
                and best["geometry_delta"]["outline_within_gate"]
                and best["geometry_delta"]["hair_within_gate"]
            )
            selected_public = {key: value for key, value in best.items() if key != "path"}
            selected_public["file"] = selected.name
            result = {
                "schema": "byrdhouse.identity-belt.v2",
                "purpose": "Local Carey identity correction; measured candidates require visual review",
                "run_id": run_id,
                "prompt_id": submission["prompt_id"],
                "source_sha256": source_hashes,
                "submission": submission_path.name,
                "accepted": accepted,
                "review_required": True,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "selected": selected_public,
                "candidates": reports,
                "reference": reference_face.public(),
                "target": target_face.public(),
                "target_to_reference_similarity": round(self._similarity(reference_face, target_face), 6),
                "workflow": graph,
                "components": {
                    "face_swap": "ComfyUI-ReActor / inswapper_128.onnx",
                    "restoration": self.config.get("belt_restore_model", "GFPGANv1.4.pth"),
                    "mask": "ReActorMaskHelper + face_yolov8m + SAM vit-b",
                    "scorer": "InsightFace buffalo_l CPU examiner",
                    "structure_examiner": "fan2_68_landmark.onnx + jonathandinu face-parsing SegFormer",
                    "generation_device": "ComfyUI ROCm device (AMD RX 7900 XT)",
                },
            }
            report_path = selected.with_suffix(".png.json")
            report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            result["file"] = selected.name
            result["report"] = report_path.name
            from render_belt_report import render
            result["analysis"] = render(report_path).name
            submission.update(state="collected", result_report=report_path.name)
            self._write_submission(submission_path, submission)
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local ByrdHouse identity belt")
    parser.add_argument("--config", type=Path, default=Path(r"D:\ByrdHouse\byrdhouse-local.json"))
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--label", default="belt")
    args = parser.parse_args()
    from server import ComfyClient, load_config

    config = load_config(args.config)
    belt = IdentityBelt(config, ComfyClient(config["comfy_url"]))
    result = belt.run(args.target, args.reference, args.label)
    print(json.dumps(result, indent=2))
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
