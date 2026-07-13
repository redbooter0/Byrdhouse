#!/usr/bin/env python3
"""Patch a ComfyUI API-format export for ByrdHouse Flux2 Klein.

This script is intentionally title-driven. Export the prepared visual workflow with
ComfyUI's "Save (API Format)" command so the `_meta.title` values are preserved.

Supports the real-to-gaming workflow with style presets and intensity profiles.
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

RECIPE_PATH = Path(__file__).resolve().parent.parent.parent / "recipes" / "real_to_gaming.v1.json"

STYLE_SUFFIXES = {
    "AAA": "AAA semi-realistic game rendering, physically-based materials, subsurface scattering on skin, cinematic depth of field, hero key lighting, clean character silhouette separation, Unreal Engine 5 quality.",
    "HERO": "Stylized hero-shooter character rendering, slightly exaggerated proportions, bold material reads, strong rim lighting, saturated color palette, clean character design language, Overwatch-quality presentation.",
    "FANTASY": "High-fantasy RPG character rendering, ornate armor details, enchanted material effects, warm dramatic lighting, rich jewel-tone palette, painterly texture quality, Baldur's Gate 3 character quality.",
    "SCIFI": "Sci-fi operative character rendering, hard-surface armor panels, holographic interface elements, cool blue-teal lighting, matte-and-gloss material contrast, cybernetic detail accents, Mass Effect character quality.",
    "CEL_SHADED": "Cel-shaded game character rendering, clean ink outlines, flat color zones with sharp shadow boundaries, limited color palette, cartoon material reads, bright saturated lighting, Genshin Impact character quality.",
    "GRITTY": "Dark action-game character rendering, worn leather and weathered metal textures, desaturated earth tones, harsh directional lighting, gritty surface detail, visible damage and environmental wear, The Last of Us character quality.",
    "SPLASH_ART": "Promotional splash-art character rendering, dramatic action pose preservation, painterly background, volumetric lighting, heroic composition, saturated key colors, dynamic energy, League of Legends splash art quality.",
}

BASE_PROMPT = (
    "Transform the real subject into a high-quality video-game character. "
    "Preserve recognizable facial identity, face structure, hairstyle, skin tone, "
    "body proportions, pose, and core outfit silhouette. "
    "Use Reference 2 only for gaming style, costume materials, lighting language, and visual genre. "
    "Do not copy the face or body identity from Reference 2. "
    "Render the subject with readable game-character materials, cinematic lighting, "
    "clean silhouette separation, detailed clothing surfaces, and professional "
    "promotional character presentation."
)

INTENSITY_PROFILES = {
    "IDENTITY_LOCK": {
        "guidance": 0.7,
        "ref1_megapixels": 3,
        "ref2_megapixels": 2,
        "prompt_prefix": (
            "Maximally preserve the exact facial identity, precise face proportions, "
            "exact hairstyle, and skin tone of the real subject. "
            "Apply only subtle game-rendering treatment. Keep the original outfit mostly intact. "
        ),
    },
    "BALANCED_GAMING": {
        "guidance": 0.9,
        "ref1_megapixels": 2,
        "ref2_megapixels": 3,
        "prompt_prefix": "",
    },
    "FULL_CHARACTER_REDESIGN": {
        "guidance": 1.1,
        "ref1_megapixels": 2,
        "ref2_megapixels": 4,
        "prompt_prefix": (
            "Transform the subject into a fully redesigned playable game character. "
            "Preserve core facial identity but allow stronger costume redesign, "
            "bolder material choices, and more dramatic game-world presentation. "
        ),
    },
}

QUALITY_TAIL = " High detail, clean edges, no extra limbs, no warped hands, no text, no watermark."


def title_of(node: dict[str, Any]) -> str:
    return str(node.get("_meta", {}).get("title", ""))


def find_one(workflow: dict[str, Any], title: str) -> dict[str, Any]:
    matches = [node for node in workflow.values() if isinstance(node, dict) and title_of(node) == title]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one API node titled {title!r}; found {len(matches)}")
    return matches[0]


def find_by_id(workflow: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    return workflow.get(node_id)


def build_gaming_prompt(style: str, intensity: str, custom_prompt: str | None = None) -> str:
    if custom_prompt:
        return custom_prompt

    profile = INTENSITY_PROFILES.get(intensity, INTENSITY_PROFILES["BALANCED_GAMING"])
    suffix = STYLE_SUFFIXES.get(style, STYLE_SUFFIXES["AAA"])
    return profile["prompt_prefix"] + BASE_PROMPT + " " + suffix + QUALITY_TAIL


def patch(workflow: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    style = getattr(args, "style", "AAA") or "AAA"
    intensity = getattr(args, "intensity", "BALANCED_GAMING") or "BALANCED_GAMING"

    prompt_text = args.prompt if args.prompt else build_gaming_prompt(style, intensity)
    prompt_node = find_one(workflow, PROMPT_TITLE)
    prompt_node.setdefault("inputs", {})["text"] = prompt_text

    ref1 = find_one(workflow, REF1_TITLE)
    ref2 = find_one(workflow, REF2_TITLE)
    ref1.setdefault("inputs", {})["image"] = args.reference_1
    ref2.setdefault("inputs", {})["image"] = args.reference_2

    profile = INTENSITY_PROFILES.get(intensity, INTENSITY_PROFILES["BALANCED_GAMING"])
    guidance_node = find_by_id(workflow, "92:63")
    if guidance_node:
        guidance_node.setdefault("inputs", {})["cfg"] = profile["guidance"]

    ref1_scale = find_by_id(workflow, "92:80")
    if ref1_scale:
        ref1_scale.setdefault("inputs", {})["megapixels"] = profile["ref1_megapixels"]

    ref2_scale = find_by_id(workflow, "92:85")
    if ref2_scale:
        ref2_scale.setdefault("inputs", {})["megapixels"] = profile["ref2_megapixels"]

    if args.seed is not None:
        seed_node = find_by_id(workflow, "113")
        if seed_node:
            seed_node.setdefault("inputs", {})["seed"] = args.seed

    if args.raw_prefix:
        find_one(workflow, RAW_SAVE_TITLE).setdefault("inputs", {})["filename_prefix"] = args.raw_prefix
    if args.upscale_prefix:
        try:
            find_one(workflow, UPSCALE_SAVE_TITLE).setdefault("inputs", {})["filename_prefix"] = args.upscale_prefix
        except ValueError:
            pass

    return workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch ByrdHouse Flux2 Klein API workflow for gaming character generation")
    parser.add_argument("--workflow", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prompt", default=None, help="Full custom prompt (overrides style/intensity)")
    parser.add_argument("--reference-1", required=True, help="Subject photo filename")
    parser.add_argument("--reference-2", required=True, help="Game-style reference filename")
    parser.add_argument("--style", default="AAA", choices=list(STYLE_SUFFIXES.keys()),
                        help="Gaming style preset (default: AAA)")
    parser.add_argument("--intensity", default="BALANCED_GAMING", choices=list(INTENSITY_PROFILES.keys()),
                        help="Transformation intensity (default: BALANCED_GAMING)")
    parser.add_argument("--seed", type=int, default=None, help="Fixed seed (-1 for random)")
    parser.add_argument("--raw-prefix", default="ByrdHouse/Flux2Klein/gaming/ByrdHouse_RealToGame")
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
    if not args.prompt:
        print(f"  Style:     {args.style}")
        print(f"  Intensity: {args.intensity}")


if __name__ == "__main__":
    main()
