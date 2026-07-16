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

STYLE_MODES = {
    "AAA": "AAA semi-realistic game character: grounded anatomy, cinematic materials, premium promotional render, restrained stylization.",
    "HERO": "Stylized hero character: iconic silhouette, confident readable shapes, polished hero presentation, controlled exaggeration.",
    "FANTASY": "Fantasy RPG: believable leather, cloth, metal, and crafted fantasy materials; grounded fantasy costume language and adventure lighting.",
    "SCIFI": "Sci-fi operative: tactical fabric, polymer, brushed metal, subtle emissive accents, functional equipment, cool cinematic lighting.",
    "CEL_SHADED": "Cel-shaded game character: clean graphic planes, deliberate contour separation, simplified controlled shading, readable colors.",
    "GRITTY": "Dark action-game character: gritty practical materials, restrained palette, hard directional light, atmospheric tension, realistic wear.",
    "SPLASH_ART": "Promotional splash art: strong hero read, dynamic cinematic lighting, environmental atmosphere, polished marketing key-art finish.",
}

INTENSITY_PROFILES = {
    "IDENTITY_LOCK": "Maximum likeness preservation; subtle game conversion; conservative costume changes; preserve pose and silhouette.",
    "BALANCED_GAMING": "Strong identity retention; obvious game-character conversion; moderate costume and material redesign.",
    "FULL_CHARACTER_REDESIGN": "Identity remains recognizable; stronger costume transformation; stronger stylization; more dramatic game-world presentation.",
}

GAME_MODES = {
    "SHONEN_ANIME": "high-quality shonen-anime character illustration: clean hand-drawn linework, cel-shaded color planes, expressive but anatomically coherent features, dynamic cinematic framing, and a face that remains fully illustrated rather than photoreal pasted onto the artwork.",
    "POKEMON": "Pokémon trainer/adventure game presentation: expressive creature-companion world, bright readable shapes, practical trainer clothing, colorful exploration environment, friendly but cinematic game-poster energy.",
    "CALL_OF_DUTY": "Call of Duty-style military shooter presentation: grounded tactical operator clothing, believable nylon and plate-carrier materials, restrained equipment, dramatic field lighting, realistic action-game key art.",
    "FORTNITE": "Fortnite-style character presentation: bold readable silhouette, playful polished materials, energetic color blocking, stylized action pose, clean high-contrast game key art.",
    "RAINBOW_SIX_SIEGE": "Rainbow Six Siege-style operator presentation: functional counter-terror operator gear, believable load-bearing equipment, controlled tactical palette, realistic squad-based shooter lighting, no excessive armor that hides the face.",
    "NBA_2K": "NBA 2K-style sports game presentation: accurate athletic proportions, premium arena lighting, realistic basketball apparel and materials, confident player-poster composition, natural skin texture.",
    "ZELDA": "The Legend of Zelda-style fantasy adventure presentation: green adventurer tunic language, leather straps, sword-and-ruins storytelling, painterly fantasy color, heroic exploration atmosphere, practical handcrafted materials.",
    "PALWORLD": "Palworld-style creature-survival adventure presentation: rugged explorer clothing, handcrafted utility materials, colorful wilderness, readable creature-adventure atmosphere, polished semi-realistic game key art.",
}


def title_of(node: dict[str, Any]) -> str:
    return str(node.get("_meta", {}).get("title", ""))


def find_one(workflow: dict[str, Any], title: str) -> dict[str, Any]:
    matches = [node for node in workflow.values() if isinstance(node, dict) and title_of(node) == title]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one API node titled {title!r}; found {len(matches)}")
    return matches[0]


def find_class(workflow: dict[str, Any], class_type: str) -> dict[str, Any]:
    matches = [node for node in workflow.values() if isinstance(node, dict) and node.get("class_type") == class_type]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one API node of class_type {class_type!r}; found {len(matches)}")
    return matches[0]


def patch(workflow: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    prompt = find_one(workflow, PROMPT_TITLE)
    ref1 = find_one(workflow, REF1_TITLE)
    ref2 = find_one(workflow, REF2_TITLE)

    prompt_inputs = prompt.setdefault("inputs", {})
    prompt_key = "text" if "text" in prompt_inputs else "prompt"
    prompt_text = args.prompt
    if args.style_mode:
        prompt_text += " STYLE MODE: " + STYLE_MODES[args.style_mode]
    if args.intensity:
        prompt_text += " INTENSITY PROFILE: " + INTENSITY_PROFILES[args.intensity]
    if args.game_mode:
        prompt_text += " GAME MODE: " + GAME_MODES[args.game_mode]
    prompt_inputs[prompt_key] = prompt_text
    ref1.setdefault("inputs", {})["image"] = args.reference_1
    ref2.setdefault("inputs", {})["image"] = args.reference_2

    if args.raw_prefix:
        find_one(workflow, RAW_SAVE_TITLE).setdefault("inputs", {})["filename_prefix"] = args.raw_prefix
    if args.upscale_prefix:
        try:
            find_one(workflow, UPSCALE_SAVE_TITLE).setdefault("inputs", {})["filename_prefix"] = args.upscale_prefix
        except ValueError:
            pass  # SAFE export has no active upscale output.
    if args.seed is not None:
        find_class(workflow, "RandomNoise").setdefault("inputs", {})["noise_seed"] = args.seed
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
    parser.add_argument("--style-mode", choices=sorted(STYLE_MODES), default=None)
    parser.add_argument("--intensity", choices=sorted(INTENSITY_PROFILES), default=None)
    parser.add_argument("--game-mode", choices=sorted(GAME_MODES), default=None)
    parser.add_argument("--seed", type=int, default=None)
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
