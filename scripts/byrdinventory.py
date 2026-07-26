"""
byrdinventory.py — ByrdHouse's memory of what it already has.

The belt kept re-solving problems it had already solved because nothing knew the
full set of assets on the machine: which checkpoints/LoRAs are installed, which
ComfyUI custom nodes exist, which workflows are API-format (POST-able) vs UI
exports (which silently 400 the /prompt endpoint), which recipes/profiles/
reference sets are present, and what's already been generated.

`scan_inventory(root)` walks a host and returns that whole picture, plus FLAGS
for dead weight the 8GB RTX 3070 can't use (fp8 has no Ampere speedup, Flux2/
Klein 9B won't fit) and UI-format workflows that can't run. `write_reports`
drops a human `docs/ASSET_INVENTORY.md` and a machine `artifacts/inventory.json`.
The worker exposes this as an `inventory.scan` belt job so refreshing ByrdHouse's
memory is one click. Stdlib only. Reference *filenames* are never listed (they're
private) — only counts.

CLI:  python byrdinventory.py            # scan this host, write both reports
      python byrdinventory.py --json     # print the inventory JSON to stdout
"""

import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

WEIGHT_EXT = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MODEL_CATS = ["checkpoints", "loras", "vae", "controlnet", "ipadapter",
              "clip", "clip_vision", "unet", "diffusion_models", "upscale_models",
              "embeddings", "insightface", "facerestore_models", "gguf"]


def _human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f}{unit}" if unit == "B" else f"{f:.1f}{unit}"
        f /= 1024
    return f"{f:.1f}TB"


def _dead_weight_flags(name: str, where: str) -> list:
    low = name.lower()
    flags = []
    if "fp8" in low:
        flags.append(f"fp8 weight has no speedup on the Ampere RTX 3070 (no fp8 "
                     f"tensor cores) — prefer GGUF: {where}/{name}")
    if any(k in low for k in ("flux2", "flux-2", "flux_2", "klein")):
        flags.append(f"Flux2/Klein is a 9B stack that will not fit the 8GB 3070 "
                     f"natively — SDXL hero lane instead: {where}/{name}")
    return flags


def _scan_models(root: Path) -> tuple:
    """Weight files under any Generators/**/models/<category>/. Models live on the
    machine (GAMING), so this is empty on a bare repo checkout — that's fine, it
    just reports what THIS host has."""
    found, flags = {}, []
    gen = root / "Generators"
    if not gen.is_dir():
        return found, flags
    for models_dir in sorted(p for p in gen.rglob("models") if p.is_dir()):
        for cat in MODEL_CATS:
            cdir = models_dir / cat
            if not cdir.is_dir():
                continue
            names, total = [], 0
            for f in cdir.rglob("*"):
                if f.is_file() and f.suffix.lower() in WEIGHT_EXT:
                    total += f.stat().st_size
                    names.append(f.name)
                    flags.extend(_dead_weight_flags(f.name, cat))
            if names:
                agg = found.setdefault(cat, {"count": 0, "bytes": 0, "files": []})
                agg["count"] += len(names)
                agg["bytes"] += total
                agg["files"] = sorted(set(agg["files"]) | set(names))
    return found, flags


def _scan_custom_nodes(root: Path) -> list:
    gen = root / "Generators"
    out = set()
    if gen.is_dir():
        for cn in gen.rglob("custom_nodes"):
            if cn.is_dir():
                for d in cn.iterdir():
                    if d.is_dir() and not d.name.startswith((".", "__")):
                        out.add(d.name)
    return sorted(out)


def _scan_workflows(root: Path) -> tuple:
    wdir = root / "workflows"
    out = {"count": 0, "api": [], "ui_format": [], "unreadable": []}
    flags = []
    if not wdir.is_dir():
        return out, flags
    for f in sorted(wdir.rglob("*.json")):
        out["count"] += 1
        rel = str(f.relative_to(root)).replace("\\", "/")
        try:
            g = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            out["unreadable"].append(rel)
            continue
        # ComfyUI UI export = {"nodes":[...], "links":[...]}; the API export the
        # /prompt endpoint needs is {node_id: {class_type, inputs}}.
        if isinstance(g, dict) and isinstance(g.get("nodes"), list) and "links" in g:
            out["ui_format"].append(rel)
            flags.append(f"UI-format workflow cannot POST to ComfyUI /prompt "
                         f"(re-export as API): {rel}")
        else:
            out["api"].append(rel)
        low = rel.lower()  # path, so a flux2_klein/ folder counts, not just filenames
        if any(k in low for k in ("flux2", "flux-2", "flux_2", "klein")):
            flags.append(f"Flux2/Klein workflow targets a 9B stack the 3070 can't "
                         f"run natively (SDXL hero lane instead): {rel}")
    return out, flags


def _scan_recipes(root: Path) -> dict:
    rdir = root / "recipes"
    files = sorted(f.name for f in rdir.glob("*.json")) if rdir.is_dir() else []
    return {"count": len(files), "files": files}


def _scan_profiles(root: Path) -> list:
    """Per-profile reference COUNTS only — filenames are private and never listed."""
    pdir = root / "profiles"
    out = []
    if not pdir.is_dir():
        return out
    for prof in sorted(p for p in pdir.iterdir() if p.is_dir()):
        refs = prof / "references"
        buckets = {}
        total = 0
        if refs.is_dir():
            for sub in sorted(p for p in refs.iterdir() if p.is_dir()):
                n = sum(1 for f in sub.rglob("*")
                        if f.is_file() and f.suffix.lower() in IMAGE_EXT)
                if n:
                    buckets[sub.name] = n
                    total += n
            root_imgs = sum(1 for f in refs.iterdir()
                            if f.is_file() and f.suffix.lower() in IMAGE_EXT)
            if root_imgs:
                buckets["(root)"] = root_imgs
                total += root_imgs
        display = prof.name
        pj = prof / "profile.json"
        if pj.is_file():
            try:
                display = json.loads(pj.read_text(encoding="utf-8-sig")).get(
                    "display_name", prof.name)
            except Exception:
                pass
        out.append({"id": prof.name, "display_name": display,
                    "reference_count": total, "reference_buckets": buckets})
    return out


def _scan_artifacts(root: Path, cap: int = 20000) -> dict:
    adir = root / "artifacts"
    by_kind, by_status, seen = {}, {}, 0
    if adir.is_dir():
        for card in adir.rglob("*.png.json"):
            if seen >= cap:
                break
            seen += 1
            try:
                c = json.loads(card.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            by_kind[c.get("kind", "image")] = by_kind.get(c.get("kind", "image"), 0) + 1
            by_status[c.get("status", "draft")] = by_status.get(c.get("status", "draft"), 0) + 1
    return {"cards_scanned": seen, "by_kind": by_kind, "by_status": by_status}


def scan_inventory(root) -> dict:
    root = Path(root)
    models, model_flags = _scan_models(root)
    workflows, wf_flags = _scan_workflows(root)
    inv = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "root": str(root),
        "models": models,
        "custom_nodes": _scan_custom_nodes(root),
        "workflows": workflows,
        "recipes": _scan_recipes(root),
        "profiles": _scan_profiles(root),
        "artifacts": _scan_artifacts(root),
        "flags": sorted(set(model_flags + wf_flags)),
    }
    return inv


def render_markdown(inv: dict) -> str:
    L = ["# ByrdHouse Asset Inventory",
         "",
         f"_What this host already has. Generated {inv['generated_at']} on "
         f"`{inv['host']}` from `{inv['root']}`. Refresh with the `inventory.scan` "
         "belt job or `python scripts/byrdinventory.py`._",
         ""]

    L += ["## Models (this host)"]
    if inv["models"]:
        L.append("| category | count | size | files |")
        L.append("|---|---:|---:|---|")
        for cat, d in sorted(inv["models"].items()):
            files = ", ".join(d["files"][:12]) + (" …" if len(d["files"]) > 12 else "")
            L.append(f"| {cat} | {d['count']} | {_human(d['bytes'])} | {files} |")
    else:
        L.append("_No model weights found on this host (they live on BYRD-GAMING; "
                 "a bare repo checkout has none)._")
    L.append("")

    cn = inv["custom_nodes"]
    L += ["## ComfyUI custom nodes (this host)",
          (", ".join(f"`{n}`" for n in cn) if cn else "_none found on this host_"), ""]

    wf = inv["workflows"]
    L += ["## Workflows",
          f"- **{len(wf['api'])}** API-format (POST-able) · "
          f"**{len(wf['ui_format'])}** UI-format (cannot run) · "
          f"**{len(wf['unreadable'])}** unreadable · {wf['count']} total"]
    if wf["ui_format"]:
        L.append("- ⚠ UI-format (re-export as API before use): "
                 + ", ".join(f"`{w}`" for w in wf["ui_format"]))
    L.append("")

    rc = inv["recipes"]
    L += ["## Recipes", f"- **{rc['count']}** recipe files", ""]

    L += ["## Identity profiles & reference library (counts only — filenames are private)"]
    if inv["profiles"]:
        L.append("| profile | references | buckets |")
        L.append("|---|---:|---|")
        for p in inv["profiles"]:
            buckets = ", ".join(f"{k}: {v}" for k, v in p["reference_buckets"].items()) or "—"
            L.append(f"| {p['display_name']} (`{p['id']}`) | {p['reference_count']} | {buckets} |")
    else:
        L.append("_no profiles found_")
    L.append("")

    art = inv["artifacts"]
    L += ["## Generated artifacts",
          f"- {art['cards_scanned']} cards scanned",
          f"- by kind: " + (", ".join(f"{k}: {v}" for k, v in sorted(art["by_kind"].items())) or "—"),
          f"- by status: " + (", ".join(f"{k}: {v}" for k, v in sorted(art["by_status"].items())) or "—"),
          ""]

    L += ["## Flags — dead weight & things that can't run on the 8GB RTX 3070"]
    if inv["flags"]:
        L += [f"- ⚠ {f}" for f in inv["flags"]]
        L += ["", "_These are candidates for pruning/replacement — the founder "
              "decides deletions, this only surfaces them._"]
    else:
        L.append("_none detected_")
    L.append("")
    return "\n".join(L)


def write_reports(root, inv: dict) -> tuple:
    root = Path(root)
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    md_path = docs / "ASSET_INVENTORY.md"
    md_path.write_text(render_markdown(inv), encoding="utf-8")
    art_dir = root / "artifacts"
    art_dir.mkdir(exist_ok=True)
    json_path = art_dir / "inventory.json"
    json_path.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    return md_path, json_path


def main():
    root = Path(os.environ.get("BYRDHOUSE_ROOT") or Path(__file__).resolve().parents[1])
    inv = scan_inventory(root)
    if "--json" in sys.argv:
        print(json.dumps(inv, indent=2))
        return
    md_path, json_path = write_reports(root, inv)
    print(f"[inventory] wrote {md_path}")
    print(f"[inventory] wrote {json_path}")
    m = inv["models"]
    print(f"[inventory] {sum(d['count'] for d in m.values())} model weights, "
          f"{len(inv['custom_nodes'])} custom nodes, "
          f"{inv['workflows']['count']} workflows "
          f"({len(inv['workflows']['ui_format'])} UI-format), "
          f"{inv['recipes']['count']} recipes, "
          f"{len(inv['profiles'])} profiles, {len(inv['flags'])} flags")


if __name__ == "__main__":
    main()
