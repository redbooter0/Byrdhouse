#!/usr/bin/env python3
"""Patch a ComfyUI API-format export for ByrdHouse Flux2 Klein.

This script is intentionally title-driven. Export the prepared visual workflow with
ComfyUI's "Save (API Format)" command so the `_meta.title` values are preserved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROMPT_TITLE = "BYRDHOUSE TRANSFORMATION PROMPT"
REF1_TITLE = "REFERENCE 1 — SUBJECT / POSE / COMPOSITION"
REF2_TITLE = "REFERENCE 2 — COSTUME / STYLE / MATERIALS"
RAW_SAVE_TITLE = "SAVE — BYRDHOUSE RAW OUTPUT"
UPSCALE_SAVE_TITLE = "SAVE — BYRDHOUSE 4X UPSCALED OUTPUT"


def title_of(node: dict[str, Any]) -> str:
    return str(node.get("_meta", {}).get("title", ""))


def find_one(workflow: dict[str, Any], title: str) -> dict[str, Any]:
    matches = [node for node in workflow.values() if isinstance(node, dict) and title_of(node) == title]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one API node titled {title!r}; found {len(matches)}")
    return matches[0]


def patch(workflow: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    prompt = find_one(workflow, PROMPT_TITLE)
    ref1 = find_one(workflow, REF1_TITLE)
    ref2 = find_one(workflow, REF2_TITLE)

    prompt.setdefault("inputs", {})["text"] = args.prompt
    ref1.setdefault("inputs", {})["image"] = args.reference_1
    ref2.setdefault("inputs", {})["image"] = args.reference_2

    if args.raw_prefix:
        find_one(workflow, RAW_SAVE_TITLE).setdefault("inputs", {})["filename_prefix"] = args.raw_prefix
    if args.upscale_prefix:
        try:
            find_one(workflow, UPSCALE_SAVE_TITLE).setdefault("inputs", {})["filename_prefix"] = args.upscale_prefix
        except ValueError:
            pass  # SAFE export has no active upscale output.
    return workflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--reference-1", required=True)
    parser.add_argument("--reference-2", required=True)
    parser.add_argument("--raw-prefix", default="ByrdHouse/Flux2Klein/raw/ByrdHouse_Flux2Klein_RAW")
    parser.add_argument("--upscale-prefix", default="ByrdHouse/Flux2Klein/upscaled/ByrdHouse_Flux2Klein_4X")
    args = parser.parse_args()

    try:
        workflow = json.loads(args.workflow.read_text(encoding="utf-8-sig"))
        patched = patch(workflow, args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(patched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Flux2 Klein API adapter failed: {exc}") from exc

    print(f"Prepared API workflow: {args.output}")


if __name__ == "__main__":
    main()
