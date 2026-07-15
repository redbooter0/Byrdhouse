from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(r"E:\ByrdHouse")
OUT = ROOT / "Images" / "Workflows" / "byrdhouse_face_swap_social"


API = {
    "1": {
        "class_type": "LoadImage",
        "inputs": {"image": "TARGET_4-Photo-4.jpg"},
        "_meta": {"title": "TARGET IMAGE — IMPORT SOCIAL / GAME PHOTO"},
    },
    "2": {
        "class_type": "ReActorLoadFaceModel",
        "inputs": {"face_model": "byrdhouse_carey_v3.safetensors"},
        "_meta": {"title": "FACE MODEL — CAREY V3 ORIGINAL + CLOUD + SMILE REFS"},
    },
    "4": {
        "class_type": "LoadImage",
        "inputs": {"image": "REFERENCE_1_SUBJECT.jpg"},
        "_meta": {"title": "FACE SOURCE — OPTIONAL LEGACY INPUT"},
    },
    "3": {
        "class_type": "ReActorFaceSwap",
        "inputs": {
            "enabled": True,
            "input_image": ["1", 0],
            "swap_model": "inswapper_128.onnx",
            "facedetection": "retinaface_resnet50",
            "face_restore_model": "GFPGANv1.4.pth",
            "face_restore_visibility": 1.0,
            "codeformer_weight": 0.5,
            "detect_gender_input": "no",
            "detect_gender_source": "no",
            "input_faces_index": "0",
            "source_faces_index": "0",
            "console_log_level": 0,
            "face_model": ["2", 0],
        },
        "_meta": {"title": "FACE SWAP — CAREY V3 MODEL / PRIMARY PERSON"},
    },
    "5": {
        "class_type": "ImageCrop",
        "inputs": {
            "image": ["3", 0],
            "width": 360,
            "height": 650,
            "x": 120,
            "y": 350,
        },
        "_meta": {"title": "CROP — ZOOM PRIMARY PERSON / ADJUST X Y W H"},
    },
    "6": {
        "class_type": "ImageScale",
        "inputs": {
            "image": ["5", 0],
            "upscale_method": "lanczos",
            "width": 768,
            "height": 1387,
            "crop": "disabled",
        },
        "_meta": {"title": "UPSCALE — MAKE CAREY MORE VISIBLE"},
    },
    "7": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "ByrdHouse/FaceSwap/carey_v3_model_zoom",
            "images": ["6", 0],
        },
        "_meta": {"title": "SAVE — CAREY V3 MODEL ZOOMED SOCIAL OUTPUT"},
    },
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "byrdhouse_social_main_head_face_model_v3_zoom_api_v1.json"
    path.write_text(json.dumps(API, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
