from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(r"E:\ByrdHouse")
OUT = ROOT / "Images" / "Workflows" / "byrdhouse_face_swap_social"


API = {
    "1": {
        "class_type": "LoadImage",
        "inputs": {"image": "FACE_REF_01.jpg"},
        "_meta": {"title": "IDENTITY REF 1 — SMILING / DURAG"},
    },
    "2": {
        "class_type": "LoadImage",
        "inputs": {"image": "FACE_REF_02.jpg"},
        "_meta": {"title": "IDENTITY REF 2 — NATURAL / AFRO"},
    },
    "3": {
        "class_type": "LoadImage",
        "inputs": {"image": "FACE_REF_03.jpg"},
        "_meta": {"title": "IDENTITY REF 3 — NATURAL / FRONT"},
    },
    "4": {
        "class_type": "LoadImage",
        "inputs": {"image": "FACE_REF_04.jpg"},
        "_meta": {"title": "IDENTITY REF 4 — DIFFERENT ANGLE"},
    },
    "5": {
        "class_type": "ImageBatch",
        "inputs": {"image1": ["1", 0], "image2": ["2", 0]},
        "_meta": {"title": "BATCH — IDENTITY REFS 1 + 2"},
    },
    "6": {
        "class_type": "ImageBatch",
        "inputs": {"image1": ["5", 0], "image2": ["3", 0]},
        "_meta": {"title": "BATCH — IDENTITY REFS 1–3"},
    },
    "7": {
        "class_type": "ImageBatch",
        "inputs": {"image1": ["6", 0], "image2": ["4", 0]},
        "_meta": {"title": "BATCH — IDENTITY REFS 1–4"},
    },
    "8": {
        "class_type": "ReActorBuildFaceModel",
        "inputs": {
            "save_mode": True,
            "send_only": False,
            "face_model_name": "byrdhouse_carey_v1",
            "compute_method": "Mean",
            "images": ["7", 0],
        },
        "_meta": {"title": "BUILD — BYRDHOUSE CAREY IDENTITY MODEL"},
    },
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "byrdhouse_carey_identity_model_build_api_v1.json"
    path.write_text(json.dumps(API, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
