#!/usr/bin/env python3
"""Run ByrdHouse real-to-gaming workflows on the local ComfyUI instance.

The fast engine is the default iteration lane for an RTX 3070. Flux2 is kept
available as the slower final-quality lane.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GAMES = {
    "SHONEN_ANIME": "high-quality shonen-anime character illustration: clean hand-drawn linework, cel-shaded color planes, expressive but anatomically coherent features, dynamic cinematic framing, and a face that remains fully illustrated rather than photoreal pasted onto the artwork.",
    "POKEMON": "Pokémon trainer adventure game: colorful creature-companion world, practical trainer clothing, bright readable shapes, cinematic exploration atmosphere.",
    "CALL_OF_DUTY": "military shooter operator: grounded tactical clothing, believable nylon and plate-carrier materials, restrained equipment, dramatic field lighting.",
    "FORTNITE": "stylized action game hero: bold readable silhouette, playful polished materials, energetic color blocking, clean high-contrast key art.",
    "RAINBOW_SIX_SIEGE": "tactical operator: functional counter-terror gear, believable load-bearing equipment, controlled palette, realistic squad-shooter lighting.",
    "NBA_2K": "basketball sports-game player: accurate athletic proportions, premium arena lighting, realistic apparel, confident player-poster composition.",
    "ZELDA": "fantasy adventure hero: green adventurer tunic language, leather straps, sword-and-ruins storytelling, painterly fantasy color, handcrafted materials.",
    "PALWORLD": "creature-survival explorer: rugged utility clothing, colorful wilderness, readable creature-adventure atmosphere, polished semi-realistic key art.",
}


def http_json(url: str, payload: dict | None = None, timeout: int = 30) -> dict:
    if payload is None:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_reference(value: str, root: Path, input_dir: Path, tag: str, run_id: str) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        if (input_dir / candidate).is_file():
            return candidate.as_posix()
        if (root / candidate).is_file():
            candidate = root / candidate
        else:
            raise FileNotFoundError(f"Reference not found: {value}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Reference not found: {candidate}")
    destination = input_dir / f"codex_{tag}_{run_id}{candidate.suffix.lower()}"
    shutil.copy2(candidate, destination)
    return destination.name


def patch_fast(graph: dict, ref1: str, prompt: str, negative: str, seed: int, steps: int, cfg: float, denoise: float, prefix: str) -> dict:
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        title = node.get("_meta", {}).get("title", "")
        inputs = node.setdefault("inputs", {})
        if node.get("class_type") == "LoadImage":
            inputs["image"] = ref1
        elif node.get("class_type") == "CLIPTextEncode":
            inputs["text"] = negative if "NEGATIVE" in title or "QUALITY" in title else prompt
        elif node.get("class_type") == "KSampler":
            inputs.update(seed=seed, steps=steps, cfg=cfg, denoise=denoise)
        elif node.get("class_type") == "SaveImage":
            inputs["filename_prefix"] = prefix
    return graph


def patch_flux(graph: dict, root: Path, ref1: str, ref2: str, prompt: str, seed: int, style: str | None, intensity: str, game: str, prefix: str) -> dict:
    sys.path.insert(0, str(root / "workflows" / "flux2_klein"))
    import api_adapter  # type: ignore

    args = SimpleNamespace(
        prompt=prompt,
        reference_1=ref1,
        reference_2=ref2,
        raw_prefix=prefix,
        upscale_prefix="",
        style_mode=style,
        intensity=intensity,
        game_mode=game,
        seed=seed,
    )
    return api_adapter.patch(graph, args)


def output_paths(result: dict, comfy_root: Path) -> list[Path]:
    paths: list[Path] = []
    for node_output in result.get("outputs", {}).values():
        for image in node_output.get("images", []):
            if image.get("type", "output") != "output":
                continue
            paths.append(comfy_root / "output" / image.get("subfolder", "") / image["filename"])
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(r"E:\ByrdHouse"))
    parser.add_argument("--engine", choices=("fast", "flux2"), default="fast")
    parser.add_argument("--lite", action="store_true", help="Use the lower-step/lower-resolution Flux2 Lite graph.")
    parser.add_argument("--game", choices=sorted(GAMES), default="ZELDA")
    parser.add_argument("--style", default=None)
    parser.add_argument("--intensity", default="BALANCED_GAMING")
    parser.add_argument("--reference-1", default="REFERENCE_1_SUBJECT.jpg")
    parser.add_argument("--reference-2", default=None, help="Male game/style reference for a male target; required for Flux2 except Zelda, which defaults to the supplied Link reference.")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--negative", default="different person, changed skin tone, changed ethnicity, generic face, plastic skin, waxy skin, blurry face, bad anatomy, extra fingers, extra limbs, text, logo, watermark, screenshot UI")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--cfg", type=float, default=None)
    parser.add_argument("--denoise", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    root = args.root.resolve()
    config = json.loads((root / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
    comfy_url = config["services"]["comfyui"].rstrip("/")
    comfy_root = root / "Generators" / "ComfyUI"
    input_dir = comfy_root / "input"
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    seed = args.seed if args.seed is not None else int(time.time() * 1000) & ((1 << 63) - 1)

    if args.engine == "fast":
        ref1 = resolve_reference(args.reference_1, root, input_dir, "subject", run_id)
        workflow_path = root / "Images" / "Workflows" / "byrdhouse_sdxl_fast_real_to_gaming_api_v1.json"
        prompt = args.prompt or (
            "realistic high-quality game character transformation, preserve the person's recognizable face, facial proportions, "
            "natural deep-brown skin tone, age, hairstyle, body identity, and pose from the subject reference; "
            f"{GAMES[args.game]} detailed costume materials, believable anatomy, clear unobstructed face, polished promotional game rendering"
        )
        graph = patch_fast(
            json.loads(workflow_path.read_text(encoding="utf-8-sig")),
            ref1,
            prompt,
            args.negative,
            seed,
            args.steps or 16,
            args.cfg or 5.5,
            args.denoise if args.denoise is not None else 0.45,
            f"ByrdHouse/RealToGaming/fast_{args.game.lower()}_{run_id}",
        )
    else:
        ref1 = resolve_reference(args.reference_1, root, input_dir, "subject", run_id)
        reference_2 = args.reference_2
        if not reference_2:
            if args.game == "ZELDA":
                reference_2 = "REFERENCE_2_ZELDA_TWILIGHT.jpg"
            else:
                raise SystemExit("Flux2 requires a gender-matched Reference 2. Supply --reference-2 with a male game/style reference.")
        ref2 = resolve_reference(reference_2, root, input_dir, "style", run_id)
        workflow_name = "byrdhouse_flux2_klein_lite_real_to_gaming_api_v1.json" if args.lite else "byrdhouse_flux2_klein_real_to_gaming_api_v1.json"
        workflow_path = root / "Images" / "Workflows" / workflow_name
        prompt = args.prompt or (
            "Transform the real subject into a recognizable game character. Preserve Reference 1 facial identity, natural skin tone, "
            f"hair, age, body identity, pose, and silhouette. Use Reference 2 only for costume and visual language. {GAMES[args.game]} "
            "Keep the face unobstructed, anatomy correct, skin natural, and output free of text or watermarks."
        )
        graph = patch_flux(
            json.loads(workflow_path.read_text(encoding="utf-8-sig")),
            root,
            ref1,
            ref2,
            prompt,
            seed,
            args.style,
            args.intensity,
            args.game,
            f"ByrdHouse/RealToGaming/flux2_{args.game.lower()}_{run_id}",
        )

    prepared = root / "Outputs" / "RealToGaming" / f"prepared_{args.engine}_{args.game.lower()}_{run_id}.json"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"prepared={prepared}")
    print(f"engine={args.engine} game={args.game} seed={seed}")
    if args.dry_run:
        return 0

    try:
        stats = http_json(f"{comfy_url}/system_stats")
    except (HTTPError, URLError) as exc:
        raise SystemExit(f"ComfyUI is not reachable at {comfy_url}: {exc}") from exc
    device = next((d for d in stats.get("devices", []) if d.get("type") == "cuda"), None)
    if device and int(device.get("vram_free", 0)) < 700 * 1024 * 1024:
        raise SystemExit("Not enough free VRAM to start safely; free the GPU and retry.")

    queued = http_json(f"{comfy_url}/prompt", {"prompt": graph, "client_id": f"byrdhouse-{args.engine}-{run_id}"})
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise SystemExit(f"ComfyUI rejected the workflow: {json.dumps(queued)}")
    print(f"prompt_id={prompt_id}")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            history = http_json(f"{comfy_url}/history/{prompt_id}", timeout=15)
        except (HTTPError, URLError):
            time.sleep(3)
            continue
        result = history.get(prompt_id)
        if result:
            status = result.get("status", {})
            if status.get("status_str") in {"error", "failed"}:
                print(json.dumps(result, indent=2))
                return 1
            if status.get("completed") or result.get("outputs"):
                print("completed=true")
                for path in output_paths(result, comfy_root):
                    print(f"output={path}")
                return 0
        time.sleep(3)
    raise SystemExit(f"Timed out after {args.timeout}s waiting for prompt {prompt_id}")


if __name__ == "__main__":
    raise SystemExit(main())
