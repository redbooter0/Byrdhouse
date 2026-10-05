"""Create a tight, aligned Carey face reference from an original photo."""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from insightface.app import FaceAnalysis
from insightface.utils import face_align


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--insightface-root", type=Path, required=True)
    args = parser.parse_args()
    image = cv2.imread(str(args.input), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(args.input)
    analysis = FaceAnalysis(
        name="buffalo_l",
        root=str(args.insightface_root),
        providers=["CPUExecutionProvider"],
    )
    analysis.prepare(ctx_id=0, det_size=(640, 640))
    faces = analysis.get(image)
    if not faces:
        raise RuntimeError("No face detected in the original photo.")
    face = max(faces, key=lambda item: float((item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1])))
    crop = face_align.norm_crop(image, landmark=face.kps, image_size=512)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), crop):
        raise RuntimeError(f"Could not write {args.output}")
    print(args.output)


if __name__ == "__main__":
    main()
