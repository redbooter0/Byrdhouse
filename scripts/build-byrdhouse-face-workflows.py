from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(r"E:\ByrdHouse")
OUTPUT = ROOT / "Images" / "Workflows" / "byrdhouse_face_swap_social"
INPUT = ROOT / "Generators" / "ComfyUI" / "input"


def api_workflow(spec: dict) -> dict:
    title = spec["title"]
    target = spec["target"]
    restore = spec["restore"]
    target_indices = spec["target_indices"]
    detector = spec["detector"]
    prefix = spec["prefix"]

    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": target},
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
                "facedetection": detector,
                "face_restore_model": restore,
                "face_restore_visibility": 1.0,
                "codeformer_weight": 0.5,
                "detect_gender_input": "no",
                "detect_gender_source": "no",
                "input_faces_index": target_indices,
                "source_faces_index": "0",
                "console_log_level": 0,
                "source_image": ["2", 0],
            },
            "_meta": {"title": title},
        },
        "4": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": prefix,
                "images": ["3", 0],
            },
            "_meta": {"title": "SAVE — BYRDHOUSE LOCAL SOCIAL OUTPUT"},
        },
    }


def ui_node(node_id, node_type, title, pos, inputs, outputs, widgets_values, order, size):
    return {
        "id": node_id,
        "type": node_type,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "title": title,
        "properties": {"Node name for S&R": node_type},
        "widgets_values": widgets_values,
    }


def ui_workflow(spec: dict) -> dict:
    title = spec["title"]
    target = spec["target"]
    restore = spec["restore"]
    target_indices = spec["target_indices"]
    detector = spec["detector"]
    prefix = spec["prefix"]
    links = [
        [1, 1, 0, 3, 1, "IMAGE"],
        [2, 2, 0, 3, 12, "IMAGE"],
        [3, 3, 0, 4, 0, "IMAGE"],
    ]
    nodes = [
        ui_node(
            1,
            "LoadImage",
            "TARGET IMAGE — IMPORT SOCIAL / GAME PHOTO",
            [40, 120],
            [],
            [
                {"name": "IMAGE", "type": "IMAGE", "links": [1]},
                {"name": "MASK", "type": "MASK", "links": None},
            ],
            [target, "image"],
            0,
            [282.8, 314],
        ),
        ui_node(
            2,
            "LoadImage",
            "FACE SOURCE — CAREY REFERENCE",
            [40, 480],
            [],
            [
                {"name": "IMAGE", "type": "IMAGE", "links": [2]},
                {"name": "MASK", "type": "MASK", "links": None},
            ],
            ["REFERENCE_1_SUBJECT.jpg", "image"],
            1,
            [282.8, 314],
        ),
        ui_node(
            3,
            "ReActorFaceSwap",
            title,
            [470, 190],
            [
                {"name": "input_image", "type": "IMAGE", "link": 1},
                {"name": "source_image", "type": "IMAGE", "link": 2},
            ],
            [
                {"name": "SWAPPED_IMAGE", "type": "IMAGE", "links": [3]},
                {"name": "FACE_MODEL", "type": "FACE_MODEL", "links": None},
                {"name": "ORIGINAL_IMAGE", "type": "IMAGE", "links": None},
            ],
            [
                True,
                "inswapper_128.onnx",
                detector,
                restore,
                1.0,
                0.5,
                "no",
                "no",
                target_indices,
                "0",
                0,
            ],
            2,
            [420, 430],
        ),
        ui_node(
            4,
            "SaveImage",
            "SAVE — BYRDHOUSE LOCAL SOCIAL OUTPUT",
            [970, 220],
            [{"name": "images", "type": "IMAGE", "link": 3}],
            [{"name": "images", "type": "IMAGE", "links": None}],
            [prefix],
            3,
            [300, 58],
        ),
    ]
    return {
        "last_node_id": 4,
        "last_link_id": 3,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {
            "byrdhouse": {
                "workflow_version": "1.0.0",
                "purpose": "LOCAL_SOCIAL_FACE_INSERTION",
                "model_class": "LIGHTWEIGHT_FACE_SWAP",
                "face_mode": "ALL_HEADS" if "," in target_indices else "PRIMARY_HEAD_ONLY",
                "subject_reference": r"E:\ByrdHouse\profiles\me\references",
                "target_folder": r"E:\ByrdHouse\Images\Targets",
                "active_face_input": "REFERENCE_1_SUBJECT.jpg",
                "target_face_indices": target_indices,
                "notes": "Use only with your own face or faces you have permission to edit.",
            }
        },
        "version": 0.4,
    }


SPECS = [
    {
        "slug": "social_main_head_fast",
        "title": "BYRDHOUSE — SOCIAL MAIN HEAD / FAST",
        "target": "TARGET_1-Photo-1.jpg",
        "restore": "none",
        "detector": "retinaface_mobile0.25",
        "target_indices": "0",
        "prefix": "ByrdHouse/FaceSwap/social_main_head_fast",
    },
    {
        "slug": "social_main_head_polished",
        "title": "BYRDHOUSE — SOCIAL MAIN HEAD / POLISHED",
        "target": "TARGET_2-Photo-2.jpg",
        "restore": "GFPGANv1.4.pth",
        "detector": "retinaface_resnet50",
        "target_indices": "0",
        "prefix": "ByrdHouse/FaceSwap/social_main_head_polished",
    },
    {
        "slug": "social_group_main_only",
        "title": "BYRDHOUSE — GROUP PHOTO / MAIN PERSON ONLY",
        "target": "TARGET_4-Photo-4.jpg",
        "restore": "GFPGANv1.4.pth",
        "detector": "retinaface_resnet50",
        "target_indices": "0",
        "prefix": "ByrdHouse/FaceSwap/group_main_only",
    },
    {
        "slug": "social_group_all_heads_same_face",
        "title": "BYRDHOUSE — GROUP PHOTO / ALL HEADS SAME FACE",
        "target": "TARGET_3-Photo-3.jpg",
        "restore": "GFPGANv1.4.pth",
        "detector": "retinaface_resnet50",
        "target_indices": "0,1,2,3",
        "prefix": "ByrdHouse/FaceSwap/group_all_heads_same_face",
    },
    {
        "slug": "game_character_main_head",
        "title": "BYRDHOUSE — GAME CHARACTER / MAIN HEAD",
        "target": "TARGET_GAME_STYLE.png",
        "restore": "none",
        "detector": "retinaface_mobile0.25",
        "target_indices": "0",
        "prefix": "ByrdHouse/FaceSwap/game_character_main_head",
    },
]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        api_path = OUTPUT / f"byrdhouse_{spec['slug']}_api_v1.json"
        ui_path = OUTPUT / f"byrdhouse_{spec['slug']}_ui_v1.json"
        api_path.write_text(json.dumps(api_workflow(spec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ui_path.write_text(json.dumps(ui_workflow(spec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    catalog = {
        "workflow_family": "BYRDHOUSE LIGHTWEIGHT SOCIAL FACE INSERTION",
        "version": "1.0.0",
        "comfyui_root": r"E:\ByrdHouse\Generators\ComfyUI",
        "reference_folder": r"E:\ByrdHouse\profiles\me\references",
        "target_folder": r"E:\ByrdHouse\Images\Targets",
        "input_folder": r"E:\ByrdHouse\Generators\ComfyUI\input",
        "model": "inswapper_128.onnx",
        "workflows": [
            {
                "slug": spec["slug"],
                "description": spec["title"],
                "face_mode": "ALL_HEADS" if "," in spec["target_indices"] else "PRIMARY_HEAD_ONLY",
                "api": f"byrdhouse_{spec['slug']}_api_v1.json",
                "ui": f"byrdhouse_{spec['slug']}_ui_v1.json",
            }
            for spec in SPECS
        ],
        "operator_notes": [
            "Put any target social or game image in the ComfyUI input folder.",
            "Set TARGET IMAGE to that filename in the target LoadImage node.",
            "Use target face index 0 for the main detected face.",
            "Use comma-separated indices such as 0,1,2 to apply the same source face to multiple heads.",
            "The all-heads preset is intentionally separate and opt-in.",
        ],
    }
    (OUTPUT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(SPECS)} API workflows and {len(SPECS)} UI workflows to {OUTPUT}")


if __name__ == "__main__":
    main()
