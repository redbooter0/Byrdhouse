#!/usr/bin/env python3
"""Convert the prepared Flux2 Klein UI graph to ComfyUI API-format JSON.

This keeps the editable UI workflow as the source of truth, omits bypassed nodes,
and carries prepared node titles into `_meta.title` for the ByrdHouse adapter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import urlopen


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def object_info(server: str):
    with urlopen(server.rstrip("/") + "/object_info", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def values_as_list(values):
    if isinstance(values, list):
        return values
    if isinstance(values, dict) or values is None:
        return []
    return [values]


def input_order(info: dict) -> list[str]:
    order = info.get("input_order", {})
    names: list[str] = []
    for group in ("required", "optional"):
        names.extend(order.get(group, []))
    return names


def build_node(ui_node: dict, info: dict) -> dict:
    class_type = ui_node["type"]
    node = {"class_type": class_type, "inputs": {}}
    title = ui_node.get("title")
    if title:
        node["_meta"] = {"title": title}

    links = {}
    for slot in ui_node.get("inputs") or []:
        if not slot:
            continue
        if slot.get("link") is not None:
            links[slot["name"]] = slot["link"]

    values = values_as_list(ui_node.get("widgets_values"))
    widget_names = []
    for slot in ui_node.get("inputs") or []:
        if slot and isinstance(slot.get("widget"), dict):
            widget_names.append(slot["name"])

    value_index = 0
    for name in widget_names:
        if value_index >= len(values):
            break
        if name not in links:
            node["inputs"][name] = values[value_index]
        value_index += 1

    for name in input_order(info):
        if name in widget_names or name in links:
            continue
        if value_index >= len(values):
            break
        node["inputs"][name] = values[value_index]
        value_index += 1

    return node


def convert(ui: dict, info: dict) -> dict:
    active: dict[str, dict] = {}
    ui_by_id = {str(node["id"]): node for node in ui.get("nodes", [])}
    for node in ui.get("nodes", []):
        if int(node.get("mode", 0)) != 0:
            continue
        node_id = str(node["id"])
        class_type = node["type"]
        if class_type not in info:
            # Frontend-only control nodes such as Fast Groups Bypasser do not
            # belong in the executable API graph.
            continue
        active[node_id] = build_node(node, info[class_type])

    for raw_link in ui.get("links", []):
        link = raw_link.get("value", raw_link) if isinstance(raw_link, dict) else raw_link
        link_id, origin_id, origin_slot, target_id, target_slot, _ = link
        origin_id = str(origin_id)
        target_id = str(target_id)
        if origin_id not in active or target_id not in active:
            continue
        target_ui = ui_by_id[target_id]
        target_inputs = [slot for slot in (target_ui.get("inputs") or []) if slot]
        if target_slot >= len(target_inputs):
            continue
        input_name = target_inputs[target_slot]["name"]
        active[target_id]["inputs"][input_name] = [origin_id, origin_slot]

    return active


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    ui = load(args.ui)
    info = object_info(args.server)
    api = convert(ui, info)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(api, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Converted {len(api)} executable nodes to {args.output}")


if __name__ == "__main__":
    main()
