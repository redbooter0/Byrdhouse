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


def judge_card(root, card: dict, image_path) -> dict:
    """Returns {"score": float, "tags": [...], "caption": str}. Raises on failure."""
    root = Path(root)
    cfg = _load(root / "byrdhouse.config.json")
    model = cfg["gpu"].get("judge_model", "")
    if not model or model.startswith("CHANGE_ME"):
        raise RuntimeError("gpu.judge_model not set in byrdhouse.config.json")
    lms = cfg["services"]["lmstudio"].rstrip("/")

    recipe = _find_recipe_spec(root, card.get("recipe", "")) or {}
    rubric = recipe.get("rubric", {"quality": "1-5"})
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode()

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
    prompt = (
        "You are the ByrdHouse image judge. Score this generated image against its "
        f"recipe rubric: {json.dumps(rubric)}. The image's purpose: "
        f"{card.get('purpose', 'unknown')}. Requested slots: {json.dumps(slots)}. "
        f"Prompt used: {card.get('prompt', '')[:400]}"
        f"{game_rule}\n"
        "Reply with ONLY a JSON object: {\"score\": <overall 1-5, one decimal>, "
        "\"scores\": {<rubric key>: <1-5>, ...}, \"tags\": [3-6 short lowercase tags], "
        "\"caption\": \"<one vivid sentence>\"}"
    )
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
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
