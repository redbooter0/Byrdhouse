"""
byrdcaption.py — the CAPTION / DESCRIBE lane (U1).

The belt's answer to ComfyUI-Ollama-Describer, done the ByrdHouse way: instead
of standing up a second LLM server (Ollama) on the one 8GB 3070 — which would
break the exclusive GPU-mode rule and the single-LLM-server rule — this sends
the image to the SAME vision model the judge already uses in LM Studio
(gpu.caption_model, falling back to gpu.judge_model) and gets back a structured
caption + tags. Stdlib only.

Two styles:
  lora     — trigger-anchored, comma-separated training tags (kohya .txt).
             Describes the VARIABLE context (pose, framing, lighting, setting,
             clothing, art style) and leaves the fixed identity to the trigger.
  natural  — one vivid, accurate sentence.

Library use (worker daemon):  caption_image(root, image_path, ...) -> dict
CLI (caption a file or a whole folder — the bulk captioner):
    python byrdcaption.py PATH [--trigger "careybh person"] [--style lora|natural]
                          [--max-words 40] [--recursive] [--write-txt]
                          [--overwrite] [--json]

A caption always writes a sidecar metadata card (<image>.caption.json — no
artifact without a card); --write-txt also writes the kohya <image>.txt.
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import byrdjudge  # noqa: E402  — reuse the vision-model picker + honesty rule

# A caption is only trustworthy from a model that can actually SEE the image, so
# byrdjudge.NoVisionModel is re-exported: no vision model means no caption, never
# an invented one (same rule the judge enforces).
NoVisionModel = byrdjudge.NoVisionModel

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _caption_model(cfg) -> str:
    """The vision model to caption with: a dedicated gpu.caption_model if set,
    otherwise the judge's vision model (one loaded model does both jobs — the
    GPU modes stay exclusive and LM Studio stays the only LLM server)."""
    gpu = cfg.get("gpu", {})
    cm = gpu.get("caption_model", "")
    if cm and not cm.startswith("CHANGE_ME"):
        return cm
    return gpu.get("judge_model", "")


def _with_trigger(trigger: str, caption: str) -> str:
    """Prefix the stable trigger phrase (kohya wants it first) without doubling
    it if the model already opened with it."""
    trigger = (trigger or "").strip().strip(",").strip()
    caption = (caption or "").strip()
    if not trigger:
        return caption
    if caption.lower().startswith(trigger.lower()):
        return caption
    return f"{trigger}, {caption}" if caption else trigger


def _build_prompt(style: str, max_words: int, context: str) -> str:
    context_line = f"\nContext you may rely on: {context}" if context else ""
    if style == "natural":
        return (
            "You are the ByrdHouse image describer. Describe this image in ONE "
            "vivid, accurate sentence — what is actually shown, the mood, and the "
            f"art style. Under {max_words} words. Do not invent names or facts you "
            f"cannot see.{context_line}\n"
            "Reply with ONLY a JSON object: "
            "{\"caption\": \"<one sentence>\", \"tags\": [3-6 short lowercase tags]}"
        )
    # lora (default): training-caption style for a diffusion LoRA dataset
    return (
        "You are the ByrdHouse dataset captioner preparing training captions for a "
        "diffusion LoRA. Describe ONLY what is visibly true about the VARIABLE "
        "context around the subject: pose, expression, shot/framing, camera angle, "
        "lighting, background/setting, clothing, and art style. Use short "
        "comma-separated descriptive phrases (Danbooru/CLIP style), lowercase, no "
        "sentences. Do NOT restate the subject's fixed identity or invent a name — "
        "the training trigger already carries the identity. Do not describe image "
        f"quality or resolution. Keep it under {max_words} words.{context_line}\n"
        "Reply with ONLY a JSON object: "
        "{\"caption\": \"<comma-separated phrases>\", \"tags\": [3-8 short lowercase tags]}"
    )


def _extract_json(content: str) -> dict:
    if not content:
        raise RuntimeError("caption model returned empty content")
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        raise RuntimeError(f"caption returned no JSON: {content[:200]}")
    return json.loads(m.group(0))


def caption_image(root, image_path, *, trigger: str = "", style: str = "lora",
                  max_words: int = 40, context: str = "") -> dict:
    """Describe one image with the LM Studio vision model.

    Returns {"caption", "tags", "model", "trigger", "style"}. The caption is the
    final, trigger-anchored string ready to drop into a kohya .txt. Raises
    NoVisionModel if nothing that can see the image is available."""
    root = Path(root)
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")
    if style not in ("lora", "natural"):
        raise ValueError(f"style must be 'lora' or 'natural', got {style!r}")

    cfg = _load(root / "byrdhouse.config.json")
    lms = cfg["services"]["lmstudio"].rstrip("/")
    model = byrdjudge._pick_judge_model(lms, _caption_model(cfg), label="caption")

    b64 = base64.b64encode(image_path.read_bytes()).decode()
    prompt = _build_prompt(style, max_words, context)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    req = urllib.request.Request(
        f"{lms}/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"LM Studio caption request failed: HTTP {e.code} {body[:1000]}") from e

    verdict = _extract_json(content)
    raw_caption = str(verdict.get("caption", "")).strip()
    caption = _with_trigger(trigger, raw_caption) if style == "lora" else raw_caption
    if style == "natural" and trigger:
        caption = _with_trigger(trigger, caption)
    tags = [str(t).strip() for t in verdict.get("tags", []) if str(t).strip()][:8]
    return {"caption": caption, "tags": tags, "model": model,
            "trigger": trigger, "style": style}


def write_sidecars(image_path, result: dict, *, write_txt: bool = False) -> dict:
    """Persist the caption next to the image: always a .caption.json card, and
    optionally the kohya .txt. Returns the paths written."""
    image_path = Path(image_path)
    card = {
        "source": image_path.name,
        "caption": result["caption"],
        "tags": result["tags"],
        "trigger": result.get("trigger", ""),
        "style": result.get("style", "lora"),
        "caption_model": result.get("model", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    json_path = image_path.with_suffix(image_path.suffix + ".caption.json")
    json_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    written = {"json": str(json_path)}
    if write_txt:
        txt_path = image_path.with_suffix(".txt")
        txt_path.write_text(result["caption"] + "\n", encoding="utf-8")
        written["txt"] = str(txt_path)
    return written


def _iter_images(path: Path, recursive: bool):
    if path.is_file():
        yield path
        return
    walker = path.rglob("*") if recursive else path.iterdir()
    for p in sorted(walker):
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
            yield p


def main():
    ap = argparse.ArgumentParser(description="Describe/caption images with the "
                                             "LM Studio vision model.")
    ap.add_argument("path", help="an image file or a folder of images")
    ap.add_argument("--trigger", default="",
                    help="trigger phrase to anchor captions (e.g. 'careybh person')")
    ap.add_argument("--style", choices=("lora", "natural"), default="lora")
    ap.add_argument("--max-words", type=int, default=40)
    ap.add_argument("--context", default="",
                    help="optional hint passed to the model (e.g. the game/subject)")
    ap.add_argument("--recursive", action="store_true",
                    help="descend into subfolders when PATH is a directory")
    ap.add_argument("--write-txt", action="store_true",
                    help="also write kohya <image>.txt training caption files")
    ap.add_argument("--overwrite", action="store_true",
                    help="re-caption images that already have a .caption.json")
    ap.add_argument("--json", action="store_true",
                    help="print one JSON line per image instead of text")
    args = ap.parse_args()

    root = Path(os.environ.get("BYRDHOUSE_ROOT") or Path(__file__).resolve().parents[1])
    target = Path(args.path)
    if not target.exists():
        sys.exit(f"not found: {target}")

    done = failed = skipped = 0
    for img in _iter_images(target, args.recursive):
        card_path = img.with_suffix(img.suffix + ".caption.json")
        if card_path.exists() and not args.overwrite:
            skipped += 1
            continue
        try:
            result = caption_image(root, img, trigger=args.trigger, style=args.style,
                                   max_words=args.max_words, context=args.context)
        except NoVisionModel as e:
            sys.exit(f"[caption] {e}\nLoad a vision model in LM Studio "
                     "(gpu.caption_model / gpu.judge_model) and retry.")
        except Exception as e:  # noqa: BLE001 — one bad image shouldn't kill a batch
            print(f"[caption] FAILED {img.name}: {e}", file=sys.stderr)
            failed += 1
            continue
        write_sidecars(img, result, write_txt=args.write_txt)
        done += 1
        if args.json:
            print(json.dumps({"image": str(img), **result}))
        else:
            print(f"[caption] {img.name}\n    {result['caption']}\n    tags: {result['tags']}")
    if target.is_dir():
        print(f"[caption] captioned {done}, skipped {skipped}, failed {failed}")
    if failed and not done:
        sys.exit(1)


if __name__ == "__main__":
    main()
