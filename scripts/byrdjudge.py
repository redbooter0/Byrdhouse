"""
byrdjudge.py — the JUDGE loop (Blueprint v2 §7.1 step 7, U1).

Sends an archived image to the vision model in LM Studio (gpu.judge_model)
and gets back a score, tags, and a caption — scored against the recipe's own
rubric so scores are comparable across recipe versions. Stdlib only.

Library use (worker daemon):   judge_card(root, card, image_path) -> dict
CLI (judge any unscored cards under artifacts/):
    python byrdjudge.py            # judge every card with score null
    python byrdjudge.py --limit 3
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _find_recipe_spec(root: Path, recipe_tag: str):
    m = re.fullmatch(r"([\w-]+)@(\d+)", recipe_tag or "")
    if not m:
        return None
    p = root / "recipes" / f"{m.group(1)}.v{m.group(2)}.json"
    return _load(p) if p.exists() else None


class NoVisionModel(RuntimeError):
    """No vision-capable model is available to judge — leave the artifact
    unjudged rather than inventing a score from a text-only model."""


# Distinctive fragments of vision/multimodal model ids. A judge score is only
# trustworthy from a model that can actually see the image, so a text model may
# NOT stand in just because it happens to be loaded.
VISION_HINTS = ("vl", "vision", "llava", "pixtral", "internvl", "minicpm-v",
                "moondream", "cogvlm", "gemma-3", "gemma3", "smolvlm", "-v-")


def _looks_vision(model_id: str) -> bool:
    m = model_id.lower()
    return any(h in m for h in VISION_HINTS)


def _pick_judge_model(lms: str, preferred: str) -> str:
    """Judging REQUIRES a vision-capable model. Preferred judge_model wins when
    loaded; a genuinely vision-capable loaded model may stand in; otherwise
    (nothing loaded) JIT-load the configured judge. If none of those hold —
    a non-vision model is loaded and no vision judge is configured/available —
    raise NoVisionModel so the artifact stays honestly unjudged."""
    try:
        with urllib.request.urlopen(f"{lms}/models", timeout=8) as r:
            loaded = [m["id"] for m in json.loads(r.read().decode()).get("data", [])]
    except Exception:
        loaded = []
    preferred_ok = preferred and not preferred.startswith("CHANGE_ME")
    if preferred_ok and preferred in loaded:
        return preferred
    vision_loaded = [m for m in loaded if _looks_vision(m)]
    if vision_loaded:
        if preferred_ok:
            print(f"[judge] '{preferred}' not loaded — using vision model '{vision_loaded[0]}'")
        return vision_loaded[0]
    if preferred_ok and not loaded:
        return preferred  # nothing loaded — let LM Studio JIT-load the configured judge
    raise NoVisionModel(
        f"no vision-capable model available to judge (loaded: {loaded or 'none'}; "
        f"configured judge_model: {preferred or 'unset'})")


def _fetch_references(cfg, card, limit=2):
    """Founder-loved thumbnails from the router's reference library (best-effort).
    Tag priority: the requested game, then the recipe family, then 'general'."""
    router = cfg.get("services", {}).get("router", "").rstrip("/")
    if not router:
        return []
    slots = card.get("slots") or {}
    tags = []
    if slots.get("game"):
        tags.append(re.sub(r"[^\w-]+", "-", slots["game"].strip().lower()))
    m = re.match(r"([\w-]+)@", card.get("recipe") or "")
    if m:
        tags.append(m.group(1))
    tags.append("general")
    out = []
    for tag in tags:
        if len(out) >= limit:
            break
        try:
            with urllib.request.urlopen(f"{router}/references?tag={tag}", timeout=10) as r:
                items = json.loads(r.read().decode())
            for it in items[: limit - len(out)]:
                with urllib.request.urlopen(
                        f"{router}/references/{it['tag']}/{it['name']}/file", timeout=15) as r:
                    out.append(base64.b64encode(r.read()).decode())
        except Exception:
            continue  # references are a bonus, never a blocker
    return out


def judge_card(root, card: dict, image_path) -> dict:
    """Returns {"score": float, "tags": [...], "caption": str}. Raises on failure."""
    root = Path(root)
    cfg = _load(root / "byrdhouse.config.json")
    lms = cfg["services"]["lmstudio"].rstrip("/")
    model = _pick_judge_model(lms, cfg["gpu"].get("judge_model", ""))

    recipe = _find_recipe_spec(root, card.get("recipe", "")) or {}
    rubric = recipe.get("rubric", {"quality": "1-5"})
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    refs = _fetch_references(cfg, card)

    slots = card.get("slots") or {}
    game = slots.get("game", "")
    game_rule = (
        "\nHARD REQUIREMENT: the image must show what was actually requested. If the "
        "main requested subject is missing, unrecognizable, or reduced to a body-part "
        "crop, cap the overall score at 3.0 and say why in the caption."
    )
    if game:
        game_rule += (
            f"\nHARD REQUIREMENT: the founder asked for the video game '{game}'. "
            f"If the image does not clearly evoke {game} (its creatures, environment, "
            f"or art style), set game_reference to 1-2, cap the overall score at 2.4, "
            f"and include the tag \"off-game\". Generic fantasy that could be any game FAILS this."
        )
    ref_rule = ""
    if refs:
        ref_rule = (
            f"\nThe FIRST image is the candidate. The following {len(refs)} image(s) are "
            "REFERENCE thumbnails the founder already loves. Add a rubric key "
            "\"reference_alignment\" (1-5): how close the candidate gets to the "
            "references' energy, composition, and punch. Weigh it heavily in the "
            "overall score — the references are the bar."
        )
    prompt = (
        "You are the ByrdHouse image judge. Score this generated image against its "
        f"recipe rubric: {json.dumps(rubric)}. The image's purpose: "
        f"{card.get('purpose', 'unknown')}. Requested slots: {json.dumps(slots)}. "
        f"Prompt used: {card.get('prompt', '')[:400]}"
        f"{game_rule}{ref_rule}\n"
        "Reply with ONLY a JSON object: {\"score\": <overall 1-5, one decimal>, "
        "\"scores\": {<rubric key>: <1-5>, ...}, \"tags\": [3-6 short lowercase tags], "
        "\"caption\": \"<one vivid sentence>\"}"
    )
    content = [{"type": "text", "text": prompt},
               {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
    content += [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{r}"}}
                for r in refs]
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    req = urllib.request.Request(
        f"{lms}/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio judge request failed: HTTP {e.code} {body[:1000]}") from e

    if not content:
        raise RuntimeError("judge model returned empty content")
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        raise RuntimeError(f"judge returned no JSON: {content[:200]}")
    verdict = json.loads(m.group(0))
    return {
        "score": round(float(verdict.get("score", 0)), 1),
        "scores": verdict.get("scores", {}),
        "tags": [str(t) for t in verdict.get("tags", [])][:8],
        "caption": str(verdict.get("caption", ""))[:300],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max cards to judge (0 = all)")
    args = ap.parse_args()

    root = Path(os.environ.get("BYRDHOUSE_ROOT") or sys.exit("BYRDHOUSE_ROOT not set"))
    done = 0
    for card_path in sorted((root / "artifacts").rglob("*.png.json")):
        card = _load(card_path)
        if card.get("score") is not None:
            continue
        image_path = Path(str(card_path)[: -len(".json")])
        if not image_path.exists():
            continue
        print(f"[judge] {image_path.name} ...")
        verdict = judge_card(root, card, image_path)
        card.update(score=verdict["score"], tags=verdict["tags"], caption=verdict["caption"])
        card["rubric_scores"] = verdict["scores"]
        card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
        print(f"[judge]   score {verdict['score']}  tags {verdict['tags']}")
        done += 1
        if args.limit and done >= args.limit:
            break
    print(f"[judge] judged {done} artifact(s)")


if __name__ == "__main__":
    main()
