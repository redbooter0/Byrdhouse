#!/usr/bin/env python3
"""byrdswap_replay.py — golden-run archaeology: find the outputs that WORKED,
recover their exact parameters, and show what drifted since.

The founder's best results (the d28/m40 Gojo, the near-perfect Vegeta) exist
on disk with sidecar cards recording everything: seed, checkpoint, LoRA and
strengths, workflow, gpu passes/denoise, mesh strength, preset, target. But
the recipes have since been reconstructed/re-locked (d0.38 defaults), so new
runs stopped matching the good ones. This tool closes that gap locally, free:

    python scripts/byrdswap_replay.py --pattern d28_m40
    python scripts/byrdswap_replay.py --pattern <anything in the filename>

For every matching artifact it prints:
  1. the golden parameters recovered from its card (+ zone file when present)
  2. a DRIFT report — every value where today's recipe/config differs
  3. the exact rerun command that reproduces the run

Nothing is modified. Pure functions are suite-tested; the scan runs on the
machine where the artifacts live.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

GOLDEN_KEYS = ("recipe", "seed", "checkpoint", "lora", "workflow",
               "identity_model_strength", "identity_clip_strength",
               "target_preset", "target", "gpu_passes", "engine")


def extract_golden_params(card: dict) -> dict:
    """Pull the reproduction-relevant fields out of a sidecar card.
    Cards written after 2026-07-16 carry a complete 'reproduce' block — use
    it as the source of truth; older cards fall back to field scraping."""
    if isinstance(card.get("reproduce"), dict):
        block = card["reproduce"]
        golden = {k: v for k, v in block.items() if v is not None}
        passes = block.get("gpu_passes") or []
        if isinstance(passes, list):
            golden["denoise_per_pass"] = {p.get("id", f"pass_{i}"): p.get("denoise")
                                          for i, p in enumerate(passes)}
        return golden
    golden = {k: card.get(k) for k in GOLDEN_KEYS if card.get(k) is not None}
    passes = card.get("gpu_passes") or []
    if isinstance(passes, list):
        golden["denoise_per_pass"] = {p.get("id", f"pass_{i}"): p.get("denoise")
                                      for i, p in enumerate(passes)}
    mesh = ((card.get("face_zone") or {}).get("identity_mesh") or {})
    if mesh.get("mesh_identity_strength") is not None:
        golden["mesh_identity_strength"] = mesh["mesh_identity_strength"]
    if mesh.get("eye_source_mode"):
        golden["eye_source"] = mesh["eye_source_mode"]
    if mesh.get("reference"):
        golden["identity_reference"] = mesh["reference"]
    return golden


def diff_vs_recipe(golden: dict, recipe: dict) -> list:
    """Name every way today's recipe would run DIFFERENTLY from the golden
    card — this list is exactly 'why I can't reproduce it anymore'."""
    drift = []
    defaults = recipe.get("defaults") or {}
    today_passes = defaults.get("gpu_passes") or {}
    for pass_id, golden_denoise in (golden.get("denoise_per_pass") or {}).items():
        today = (today_passes.get(pass_id) or {}).get("denoise")
        if golden_denoise is not None and today is not None and today != golden_denoise:
            drift.append(f"gpu pass '{pass_id}' denoise: golden {golden_denoise} "
                         f"vs recipe today {today}")
    if defaults.get("skip_gpu_cleanup") and golden.get("denoise_per_pass"):
        drift.append("recipe today SKIPS gpu cleanup; the golden run used GPU passes")
    identity = recipe.get("identity") or {}
    if golden.get("lora") and identity.get("lora") != golden["lora"]:
        drift.append(f"identity LoRA: golden '{golden['lora']}' vs recipe today "
                     f"'{identity.get('lora')}' — pass it with -Lora")
    for key, label in (("identity_model_strength", "strength"),
                       ("identity_clip_strength", "clip_strength")):
        if golden.get(key) is not None and identity.get(label) is not None \
                and identity.get(label) != golden[key]:
            drift.append(f"identity {label}: golden {golden[key]} vs recipe today "
                         f"{identity.get(label)}")
    if golden.get("workflow") and recipe.get("workflow") \
            and recipe["workflow"] != golden["workflow"]:
        drift.append(f"workflow: golden {golden['workflow']} vs recipe today "
                     f"{recipe['workflow']}")
    return drift


def rerun_command(golden: dict) -> str:
    """The exact one-liner that reproduces the golden run's parameters."""
    parts = ["facelab.ps1 quality",
             f"-Image \"{golden.get('target', '<target>')}\""]
    if golden.get("target_preset") and golden["target_preset"] != "auto":
        parts.append(f"-Preset {golden['target_preset']}")
    if golden.get("lora"):
        parts.append(f"-Lora \"{golden['lora']}\"")
    if golden.get("workflow"):
        parts.append(f"-Workflow \"{golden['workflow']}\"")
    note = []
    if golden.get("denoise_per_pass"):
        note.append("gpu_passes " + json.dumps(golden["denoise_per_pass"]))
    if golden.get("mesh_identity_strength") is not None:
        note.append(f"mesh_identity_strength {golden['mesh_identity_strength']}")
    if golden.get("seed") is not None:
        note.append(f"seed {golden['seed']}")
    cmd = " ".join(parts)
    if note:
        cmd += "\n    # engine overrides used by the golden run: " + "; ".join(note)
        cmd += "\n    # (byrdswap.py's gojo avenue applies d0.28/m0.40 automatically: facelab.ps1 run ... )"
    return cmd


def scan(root: Path, pattern: str) -> list:
    """Find artifact cards whose filename or card mentions the pattern."""
    hits = []
    art_root = root / "artifacts"
    if not art_root.is_dir():
        return hits
    for card_file in art_root.rglob("*.json"):
        name = card_file.name.lower()
        if pattern in name:
            hits.append(card_file)
            continue
        if card_file.stat().st_size < 400_000 and pattern not in name:
            try:
                text = card_file.read_text(encoding="utf-8", errors="replace")
                if pattern in text.lower() and '"recipe"' in text:
                    hits.append(card_file)
            except OSError:
                continue
    return sorted(set(hits))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", default="d28_m40",
                    help="substring of the golden output's filename/card")
    ap.add_argument("--root", default=os.environ.get("BYRDHOUSE_ROOT", "."))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    pattern = args.pattern.lower()
    hits = scan(root, pattern)
    if not hits:
        print(f"[replay] no artifact cards matching '{pattern}' under {root/'artifacts'}")
        print("[replay] try the exact filename fragment from the good output, e.g. "
              "--pattern fullidentity_fill or --pattern 19f694590e77xbmy5")
        return 1
    report = {"pattern": pattern, "found": len(hits), "runs": []}
    for card_file in hits:
        try:
            card = json.loads(card_file.read_text(encoding="utf-8-sig"))
        except ValueError:
            continue
        golden = extract_golden_params(card)
        recipe_name = str(card.get("recipe", "")).split("@")[0]
        drift = []
        recipe_file = None
        for cand in sorted((root / "recipes").glob(f"{recipe_name}*.json"), reverse=True):
            recipe_file = cand
            break
        if recipe_file:
            drift = diff_vs_recipe(golden, json.loads(recipe_file.read_text(encoding="utf-8-sig")))
        entry = {"card": str(card_file), "golden": golden,
                 "drift_vs_today": drift, "rerun": rerun_command(golden)}
        report["runs"].append(entry)
        print(f"\n=== GOLDEN RUN: {card_file.name} ===")
        print(json.dumps(golden, indent=2)[:1200])
        if drift:
            print("DRIFT since it worked (why new runs differ):")
            for d in drift:
                print(f"  - {d}")
        else:
            print("no recipe drift detected — the difference is seed/target/LoRA choice")
        print("rerun:\n    " + entry["rerun"])
    out = root / "logs" / "byrdswap"
    out.mkdir(parents=True, exist_ok=True)
    out_file = out / f"golden_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[replay] report: {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
