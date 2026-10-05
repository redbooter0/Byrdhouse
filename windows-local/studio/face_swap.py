"""Apply a verified Carey face identity to a generated still.

This is a post-process identity pass for local candidate generation. It keeps
the generated scene, pose, clothing, and hair while replacing the detected
face with the approved source identity. It is deliberately separate from the
image-generation worker so every result remains reviewable.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from insightface.app import FaceAnalysis
from insightface.model_zoo import get_model


def largest_face(faces):
    if not faces:
        raise RuntimeError("No face detected in the supplied image.")
    return max(faces, key=lambda face: float((face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1])))


def swap(source_path: Path, target_path: Path, output_path: Path, model_path: Path, insightface_root: Path):
    source = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    target = cv2.imread(str(target_path), cv2.IMREAD_COLOR)
    if source is None:
        raise FileNotFoundError(source_path)
    if target is None:
        raise FileNotFoundError(target_path)
    analysis = FaceAnalysis(
        name="buffalo_l",
        root=str(insightface_root),
        providers=["CPUExecutionProvider"],
    )
    analysis.prepare(ctx_id=0, det_size=(640, 640))
    source_face = largest_face(analysis.get(source))
    target_face = largest_face(analysis.get(target))
    swapper = get_model(str(model_path), providers=["CPUExecutionProvider"])
    result = swapper.get(target, target_face, source_face, paste_back=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), result):
        raise RuntimeError(f"Could not write {output_path}")
    print(output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--insightface-root", type=Path, required=True)
    args = parser.parse_args()
    swap(args.source, args.target, args.output, args.model, args.insightface_root)


if __name__ == "__main__":
    main()
