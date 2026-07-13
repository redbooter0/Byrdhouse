#!/usr/bin/env python3
"""Convert the ByrdHouse Flux2 Klein UI workflow to API format.

This produces a structural API-format JSON from the editable UI workflow.
The operator should verify by loading in ComfyUI and re-exporting with
Save (API Format) for production use. This script handles Set/Get node
resolution and bypassed-node filtering specific to this workflow.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

WIDGET_MAP: dict[str, list[str]] = {
    "UNETLoader": ["unet_name", "weight_dtype"],
    "CLIPLoader": ["clip_name", "type"],
    "VAELoader": ["vae_name"],
    "LoadImage": ["image"],
    "SaveImage": ["filename_prefix"],
    "CLIPTextEncode": ["text"],
    "CFGGuider": ["cfg"],
    "KSamplerSelect": ["sampler_name"],
    "Flux2Scheduler": ["steps", "width", "height"],
    "EmptyFlux2LatentImage": ["width", "height", "batch_size"],
    "RandomNoise": ["noise_seed"],
    "ImageScaleToTotalPixels": ["upscale_method", "megapixels"],
    "VAEEncode": [],
    "VAEDecode": [],
    "ReferenceLatent": [],
    "ConditioningZeroOut": [],
    "SamplerCustomAdvanced": [],
    "GetImageSize": [],
    "PreviewImage": [],
    "Seed (rgthree)": ["seed"],
    "XIS_INT_Slider": ["value"],
}

SKIP_TYPES = {"GetNode", "SetNode", "Fast Groups Bypasser (rgthree)", "Image Comparer (rgthree)"}


def convert(ui_path: Path) -> dict[str, Any]:
    ui = json.loads(ui_path.read_text(encoding="utf-8-sig"))
    nodes = ui["nodes"]
    links = ui["links"]

    node_map: dict[str, dict] = {}
    for n in nodes:
        node_map[str(n["id"])] = n

    link_map: dict[int, tuple[str, int]] = {}
    for link in links:
        link_id, src_id, src_out, _tgt_id, _tgt_in, _type = link
        link_map[int(link_id)] = (str(src_id), int(src_out))

    set_nodes: dict[str, tuple[str, int]] = {}
    for n in nodes:
        if n["type"] == "SetNode":
            name = n.get("widgets_values", [""])[0]
            inp = n.get("inputs", [])
            if inp and inp[0].get("link") is not None:
                src = link_map.get(int(inp[0]["link"]))
                if src:
                    set_nodes[name] = src

    def resolve_link(link_id: int | None) -> tuple[str, int] | None:
        if link_id is None:
            return None
        src = link_map.get(int(link_id))
        if not src:
            return None
        src_node = node_map.get(src[0])
        if src_node and src_node["type"] == "GetNode":
            get_name = src_node.get("widgets_values", [""])[0]
            if get_name in set_nodes:
                return set_nodes[get_name]
        return src

    api: dict[str, Any] = {}

    for n in nodes:
        ntype = n["type"]
        nid = str(n["id"])
        mode = n.get("mode", 0)

        if mode == 4:
            continue
        if ntype in SKIP_TYPES:
            continue

        widget_names = WIDGET_MAP.get(ntype)
        if widget_names is None:
            continue

        inputs: dict[str, Any] = {}

        widgets = n.get("widgets_values", [])
        for i, wname in enumerate(widget_names):
            if i < len(widgets):
                inputs[wname] = widgets[i]

        for inp in n.get("inputs", []):
            inp_name = inp["name"]
            link_id = inp.get("link")
            if link_id is not None:
                resolved = resolve_link(link_id)
                if resolved:
                    inputs[inp_name] = list(resolved)
                if "widget" in inp and inp_name in inputs and not isinstance(inputs[inp_name], list):
                    pass

        entry: dict[str, Any] = {
            "inputs": inputs,
            "class_type": ntype,
        }

        title = n.get("title", "")
        if title:
            entry["_meta"] = {"title": title}

        api[nid] = entry

    return api


def validate(api: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if "nodes" in api:
        errors.append("API format must not have a top-level 'nodes' array")
    if "links" in api:
        errors.append("API format must not have a top-level 'links' array")

    has_ref1 = False
    has_ref2 = False
    has_prompt = False
    has_raw_save = False
    has_seedvr2 = False

    for nid, node in api.items():
        if not isinstance(node, dict):
            continue
        if "class_type" not in node:
            errors.append(f"Node {nid} missing class_type")

        title = node.get("_meta", {}).get("title", "")
        ctype = node.get("class_type", "")

        if "REFERENCE 1" in title and ctype == "LoadImage":
            has_ref1 = True
            if "image" not in node.get("inputs", {}):
                errors.append("Reference 1 LoadImage missing 'image' input")

        if "REFERENCE 2" in title and ctype == "LoadImage":
            has_ref2 = True
            if "image" not in node.get("inputs", {}):
                errors.append("Reference 2 LoadImage missing 'image' input")

        if "BYRDHOUSE TRANSFORMATION PROMPT" in title:
            has_prompt = True
            if "text" not in node.get("inputs", {}):
                errors.append("Transformation prompt missing 'text' input")

        if "SAVE" in title and "RAW" in title and ctype == "SaveImage":
            has_raw_save = True

        if "SeedVR2" in ctype:
            has_seedvr2 = True

    if not has_ref1:
        errors.append("Missing Reference 1 LoadImage")
    if not has_ref2:
        errors.append("Missing Reference 2 LoadImage")
    if not has_prompt:
        errors.append("Missing BYRDHOUSE TRANSFORMATION PROMPT")
    if not has_raw_save:
        errors.append("Missing raw SaveImage output")
    if has_seedvr2:
        errors.append("SeedVR2 nodes should be excluded (bypassed)")

    return errors


def main() -> None:
    base = Path(__file__).resolve().parent
    ui_path = base / "safe_first_run.json"
    api_path = base / "real_to_gaming_api_v1.json"

    api = convert(ui_path)
    errors = validate(api)

    if errors:
        print("VALIDATION ERRORS:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    api_path.write_text(json.dumps(api, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Generated API format: {api_path}")
    print(f"  Nodes: {len(api)}")
    print(f"  Validation: PASSED")

    for nid, node in sorted(api.items(), key=lambda x: x[0]):
        title = node.get("_meta", {}).get("title", node.get("class_type", ""))
        print(f"    {nid:>12s}: {title}")


if __name__ == "__main__":
    main()
