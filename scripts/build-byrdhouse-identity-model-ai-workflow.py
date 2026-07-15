from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(r"E:\ByrdHouse")
OUT = ROOT / "Images" / "Workflows" / "byrdhouse_face_swap_social"


IDENTITY_REFS = [
    ("FACE_REF_01.jpg", "ORIGINAL REF 1 — SMILING / DURAG"),
    ("FACE_REF_02.jpg", "ORIGINAL REF 2 — NATURAL / AFRO"),
    ("FACE_REF_03.jpg", "ORIGINAL REF 3 — NATURAL / FRONT"),
    ("FACE_REF_04.jpg", "ORIGINAL REF 4 — DIFFERENT ANGLE"),
    ("AI_FACE_REF_01_FRONT.png", "CLOUD REF 1 — CLEAN FRONT"),
    ("AI_FACE_REF_02_3Q_LEFT.png", "CLOUD REF 2 — THREE-QUARTER LEFT"),
    ("AI_FACE_REF_03_3Q_RIGHT.png", "CLOUD REF 3 — THREE-QUARTER RIGHT"),
    ("AI_FACE_REF_04_PROFILE.png", "CLOUD REF 4 — PROFILE"),
    ("AI_FACE_REF_05_SMILE_FRONT.png", "CLOUD REF 5 — SMILING FRONT / TEETH"),
    ("AI_FACE_REF_06_SMILE_3Q_LEFT.png", "CLOUD REF 6 — SMILING THREE-QUARTER / TEETH"),
]


def build_api() -> dict[str, dict]:
    api: dict[str, dict] = {}
    for index, (filename, title) in enumerate(IDENTITY_REFS, start=1):
        api[str(index)] = {
            "class_type": "LoadImage",
            "inputs": {"image": filename},
            "_meta": {"title": title},
        }

    batch_id = len(IDENTITY_REFS) + 1
    left = ["1", 0]
    for ref_index in range(2, len(IDENTITY_REFS) + 1):
        api[str(batch_id)] = {
            "class_type": "ImageBatch",
            "inputs": {"image1": left, "image2": [str(ref_index), 0]},
            "_meta": {"title": f"BATCH — IDENTITY REFS 1–{ref_index}"},
        }
        left = [str(batch_id), 0]
        batch_id += 1

    api[str(batch_id)] = {
        "class_type": "ReActorBuildFaceModel",
        "inputs": {
            "save_mode": True,
            "send_only": False,
            "face_model_name": "byrdhouse_carey_v3",
            "compute_method": "Mean",
            "images": left,
        },
        "_meta": {
            "title": "BUILD — BYRDHOUSE CAREY V3 (ORIGINAL + CLOUD POSE + SMILE COVERAGE)"
        },
    }
    return api


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "byrdhouse_carey_identity_model_build_ai_v3_api_v1.json"
    path.write_text(json.dumps(build_api(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
