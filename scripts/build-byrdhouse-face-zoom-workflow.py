from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(r"E:\ByrdHouse")
OUT = ROOT / "Images" / "Workflows" / "byrdhouse_face_swap_social"


def api_graph() -> dict:
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": "TARGET_4-Photo-4.jpg"},
            "_meta": {"title": "TARGET IMAGE — IMPORT SOCIAL / GAME PHOTO"},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": "REFERENCE_1_SUBJECT.jpg"},
            "_meta": {"title": "FACE SOURCE — CAREY REFERENCE"},
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
                "source_image": ["2", 0],
            },
            "_meta": {"title": "FACE SWAP — PRIMARY PERSON"},
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
            "_meta": {"title": "UPSCALE — MAKE FACE MORE VISIBLE"},
        },
        "4": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ByrdHouse/FaceSwap/social_primary_zoom",
                "images": ["6", 0],
            },
            "_meta": {"title": "SAVE — BYRDHOUSE ZOOMED SOCIAL OUTPUT"},
        },
    }


def ui_graph() -> dict:
    nodes = [
        {
            "id": 1,
            "type": "LoadImage",
            "pos": [40, 80],
            "size": [282.8, 314],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [],
            "outputs": [
                {"name": "IMAGE", "type": "IMAGE", "links": [1]},
                {"name": "MASK", "type": "MASK", "links": None},
            ],
            "title": "TARGET IMAGE — IMPORT SOCIAL / GAME PHOTO",
            "properties": {"Node name for S&R": "LoadImage"},
            "widgets_values": ["TARGET_4-Photo-4.jpg", "image"],
        },
        {
            "id": 2,
            "type": "LoadImage",
            "pos": [40, 440],
            "size": [282.8, 314],
            "flags": {},
            "order": 1,
            "mode": 0,
            "inputs": [],
            "outputs": [
                {"name": "IMAGE", "type": "IMAGE", "links": [2]},
                {"name": "MASK", "type": "MASK", "links": None},
            ],
            "title": "FACE SOURCE — CAREY REFERENCE",
            "properties": {"Node name for S&R": "LoadImage"},
            "widgets_values": ["REFERENCE_1_SUBJECT.jpg", "image"],
        },
        {
            "id": 3,
            "type": "ReActorFaceSwap",
            "pos": [470, 160],
            "size": [420, 430],
            "flags": {},
            "order": 2,
            "mode": 0,
            "inputs": [
                {"name": "input_image", "type": "IMAGE", "link": 1},
                {"name": "source_image", "type": "IMAGE", "link": 2},
            ],
            "outputs": [
                {"name": "SWAPPED_IMAGE", "type": "IMAGE", "links": [4]},
                {"name": "FACE_MODEL", "type": "FACE_MODEL", "links": None},
                {"name": "ORIGINAL_IMAGE", "type": "IMAGE", "links": None},
            ],
            "title": "FACE SWAP — PRIMARY PERSON",
            "properties": {"Node name for S&R": "ReActorFaceSwap"},
            "widgets_values": [
                True,
                "inswapper_128.onnx",
                "retinaface_resnet50",
                "GFPGANv1.4.pth",
                1.0,
                0.5,
                "no",
                "no",
                "0",
                "0",
                0,
            ],
        },
        {
            "id": 5,
            "type": "ImageCrop",
            "pos": [960, 160],
            "size": [270, 154],
            "flags": {},
            "order": 3,
            "mode": 0,
            "inputs": [{"name": "image", "type": "IMAGE", "link": 4}],
            "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [5]}],
            "title": "CROP — ZOOM PRIMARY PERSON / ADJUST X Y W H",
            "properties": {"Node name for S&R": "ImageCrop"},
            "widgets_values": [360, 650, 120, 350],
        },
        {
            "id": 6,
            "type": "ImageScale",
            "pos": [1300, 160],
            "size": [270, 154],
            "flags": {},
            "order": 4,
            "mode": 0,
            "inputs": [{"name": "image", "type": "IMAGE", "link": 5}],
            "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [6]}],
            "title": "UPSCALE — MAKE FACE MORE VISIBLE",
            "properties": {"Node name for S&R": "ImageScale"},
            "widgets_values": ["lanczos", 768, 1387, "disabled"],
        },
        {
            "id": 4,
            "type": "SaveImage",
            "pos": [1640, 210],
            "size": [300, 58],
            "flags": {},
            "order": 5,
            "mode": 0,
            "inputs": [{"name": "images", "type": "IMAGE", "link": 6}],
            "outputs": [{"name": "images", "type": "IMAGE", "links": None}],
            "title": "SAVE — BYRDHOUSE ZOOMED SOCIAL OUTPUT",
            "properties": {"Node name for S&R": "SaveImage"},
            "widgets_values": ["ByrdHouse/FaceSwap/social_primary_zoom"],
        },
    ]
    return {
        "last_node_id": 6,
        "last_link_id": 6,
        "nodes": nodes,
        "links": [
            [1, 1, 0, 3, 0, "IMAGE"],
            [2, 2, 0, 3, 1, "IMAGE"],
            [4, 3, 0, 5, 0, "IMAGE"],
            [5, 5, 0, 6, 0, "IMAGE"],
            [6, 6, 0, 4, 0, "IMAGE"],
        ],
        "groups": [],
        "config": {},
        "extra": {
            "byrdhouse": {
                "workflow_version": "1.0.0",
                "purpose": "PRIMARY_FACE_SWAP_WITH_MANUAL_COMFY_CROP_ZOOM",
                "crop_controls": {"x": 120, "y": 350, "width": 360, "height": 650},
                "face_index": "0",
                "notes": "Adjust the crop node around the intended person before running a new target image.",
            }
        },
        "version": 0.4,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "byrdhouse_social_main_head_zoom_manual_api_v1.json").write_text(
        json.dumps(api_graph(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "byrdhouse_social_main_head_zoom_manual_ui_v1.json").write_text(
        json.dumps(ui_graph(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote manual face zoom API and UI workflows")


if __name__ == "__main__":
    main()
