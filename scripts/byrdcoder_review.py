#!/usr/bin/env python3
"""ByrdCoder two-agent review loop, reviewer side (docs/BYRDCODER_LOCAL.md
Phase 6). Model B reviews Model A's patch and returns a verdict.

Input:  --task (file with the original task), --diff (proposed unified diff),
        --tests (test output file, optional), --context (relevant source
        files, repeatable), --model (LM Studio model id for the reviewer).
Output: a review card JSON under logs/byrdcoder/reviews/ and an exit code:
        0 = approve, 1 = request_changes, 2 = block.

Fail-closed: if the reviewer's output cannot be parsed as a verdict after one
retry, the result is BLOCK — an unreviewable patch is never treated as
approved. A blocked patch must never be promoted automatically; promotion is
a founder Tier 4 action.

Stdlib only. The LM Studio URL comes from byrdhouse.config.json
services.lmstudio (zero hardcoded hosts). The reviewer system prompt is the
byrd-review profile prompt, so TUI reviews and scripted reviews judge by the
same rules.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERDICTS = ("approve", "request_changes", "block")
MAX_SECTION = 24000  # chars per section keeps total prompt inside small contexts


def read_text(path, limit=MAX_SECTION):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        text = text[:limit] + f"\n[... truncated at {limit} chars ...]"
    return text


def chat(base, model, messages, timeout):
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "messages": messages,
                         "temperature": 0.1, "stream": False}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def parse_verdict(text):
    """Find the last JSON object containing a valid verdict."""
    for match in reversed(re.findall(r"\{[^{}]*\}", text, re.DOTALL)):
        try:
            obj = json.loads(match)
        except ValueError:
            continue
        if str(obj.get("verdict", "")).lower() in VERDICTS:
            obj["verdict"] = obj["verdict"].lower()
            obj.setdefault("reasons", [])
            obj.setdefault("risks", [])
            return obj
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--diff", required=True)
    ap.add_argument("--tests")
    ap.add_argument("--context", action="append", default=[])
    ap.add_argument("--model", required=True)
    ap.add_argument("--root", default=os.environ.get("BYRDHOUSE_ROOT", "."))
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    root = Path(args.root)
    cfg = json.loads((root / "byrdhouse.config.json").read_text(encoding="utf-8"))
    base = cfg["services"]["lmstudio"]
    system = read_text(root / "configs" / "byrdcoder" / "prompts" / "byrd-review.md")

    parts = ["## Original task\n" + read_text(args.task),
             "## Proposed diff\n```diff\n" + read_text(args.diff) + "\n```"]
    if args.tests:
        parts.append("## Test output\n```\n" + read_text(args.tests) + "\n```")
    for cpath in args.context:
        parts.append(f"## Context: {cpath}\n```\n" + read_text(cpath) + "\n```")
    parts.append("Return your verdict JSON now.")
    user = "\n\n".join(parts)

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    verdict = None
    raw = ""
    try:
        raw = chat(base, args.model, messages, args.timeout)
        verdict = parse_verdict(raw)
        if verdict is None:  # one retry, then fail closed
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             'Unparseable. Reply with ONLY the JSON object: '
                             '{"verdict": "approve|request_changes|block", '
                             '"reasons": [], "risks": []}'})
            raw = chat(base, args.model, messages, args.timeout)
            verdict = parse_verdict(raw)
    except Exception as e:  # noqa: BLE001 — any transport failure fails closed
        raw = f"(reviewer call failed: {e})"

    if verdict is None:
        verdict = {"verdict": "block",
                   "reasons": ["reviewer output unparseable or reviewer "
                               "unreachable — fail closed, founder must review"],
                   "risks": []}

    card = {"tool": "byrdcoder_review", "version": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reviewer_model": args.model, "lmstudio": base,
            "task_file": args.task, "diff_file": args.diff,
            "tests_file": args.tests, "context_files": args.context,
            "verdict": verdict["verdict"], "reasons": verdict["reasons"],
            "risks": verdict["risks"], "raw_reply_tail": raw[-2000:]}
    out_dir = root / "logs" / "byrdcoder" / "reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"review_{stamp}.json"
    out_file.write_text(json.dumps(card, indent=2), encoding="utf-8")

    print(f"verdict: {verdict['verdict']}")
    for reason in verdict["reasons"]:
        print(f"  - {reason}")
    print(f"card: {out_file}")
    return {"approve": 0, "request_changes": 1, "block": 2}[verdict["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
