"""
byrdidentity.py — the identity ACCEPTANCE GATE (handoff 2026-07-25 §4.2, §11.1).

The belt could already *measure* identity (verify_identity.py in the judge). It
still shipped recolors, because measuring without gating just produces a number
next to a bad image. The 2026-07-22 Vegeta runs were reported as "25% / 40% /
55% identity" successes while every one of them was Vegeta's exact facial
geometry with darker skin.

This module turns the measurement into a decision. It is deliberately small and
conservative, and it obeys one rule above all: **fail closed, never fake
success** — but also never reject what it could not actually measure.

    evaluate(card, verdict, cfg) -> {
        "decision": "accept" | "reject" | "review",
        "reasons": [...],           # human-readable, recorded on the card
        "gate": {...},              # the numbers the decision was made from
    }

Authority model (why the backends are NOT treated the same):
  * arcface  — a real face-embedding metric. Authoritative: may accept or reject
               on score alone.
  * clip     — whole-image similarity, NOT an identity metric. Advisory only: it
               may never reject on score alone (a low CLIP score across a
               photo->anime domain gap says nothing about identity).
  * recolor guard — authoritative regardless of backend, because it is
               behavioral, not perceptual: if the output is ~pixel-identical to
               the target (SSIM > threshold) AND identity is at the floor, then
               nothing was transferred but colour. That is the exact failure the
               mesh-seed lane produces by construction, and it is provable.

Thresholds live in byrdhouse.config.json under "identity" so the founder can
tune them without touching code.
"""

# Defaults are conservative: they only fire on results that are clearly bad.
DEFAULTS = {
    # ArcFace cosine on normed embeddings. Same person typically >= 0.4;
    # different people sit near 0.0-0.2. 0.28 rejects only the clearly-not-Carey.
    "arcface_reject_below": 0.28,
    "arcface_accept_at": 0.40,
    # The recolor guard: output nearly identical to the target AND no identity.
    "recolor_target_similarity": 0.92,
    "recolor_identity_ceiling": 0.20,
    # CLIP is advisory; this only flags, never rejects.
    "clip_flag_below": 0.60,
}


def thresholds(cfg: dict) -> dict:
    """Config-driven thresholds with the conservative defaults above."""
    out = dict(DEFAULTS)
    for k, v in (cfg.get("identity") or {}).items():
        if k in out and isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def evaluate(card: dict, verdict: dict, cfg: dict) -> dict:
    """Decide whether an identity output may be accepted.

    'review' means the belt genuinely does not know (no backend installed, or an
    advisory-only signal) — the founder still reviews it by hand. It is never a
    silent pass: the reason is recorded either way."""
    t = thresholds(cfg)
    score = verdict.get("identity_score")
    backend = verdict.get("identity_backend") or "none"
    guess = verdict.get("identity_method_guess")
    target_sim = verdict.get("identity_target_similarity")
    gate = {"identity_score": score, "identity_backend": backend,
            "method_guess": guess, "target_similarity": target_sim,
            "thresholds": t}
    reasons = []

    # 1. Unmeasured — honest 'review'. Do not invent a pass OR a failure.
    if backend == "none" or score is None:
        reasons.append(
            "identity could not be measured (no arcface/clip backend installed) "
            "— left for human review, not auto-approved")
        return {"decision": "review", "reasons": reasons, "gate": gate}

    # 2. The recolor guard — authoritative, behavioral, backend-independent.
    #    This is the Vegeta failure: the target with recoloured skin.
    if target_sim is not None and target_sim > t["recolor_target_similarity"] \
            and score < t["recolor_identity_ceiling"]:
        reasons.append(
            f"RECOLOR-ONLY: output is {target_sim:.1%} identical to the target "
            f"while identity is {score:.3f} — the target's geometry was kept and "
            "only colour changed. This is not a likeness.")
        return {"decision": "reject", "reasons": reasons, "gate": gate}
    if guess == "recolor_only":
        reasons.append(
            "RECOLOR-ONLY: the identity check classified this as a recoloured "
            "target rather than a transferred likeness.")
        return {"decision": "reject", "reasons": reasons, "gate": gate}

    # 3. ArcFace is authoritative on score.
    if backend == "arcface":
        if score < t["arcface_reject_below"]:
            reasons.append(
                f"identity {score:.3f} is below the reject floor "
                f"{t['arcface_reject_below']:.2f} (arcface) — this does not read "
                "as the subject")
            return {"decision": "reject", "reasons": reasons, "gate": gate}
        if score >= t["arcface_accept_at"]:
            reasons.append(
                f"identity {score:.3f} clears the arcface bar "
                f"{t['arcface_accept_at']:.2f}")
            return {"decision": "accept", "reasons": reasons, "gate": gate}
        reasons.append(
            f"identity {score:.3f} sits between the reject floor and the accept "
            "bar — borderline, needs a human look")
        return {"decision": "review", "reasons": reasons, "gate": gate}

    # 4. CLIP (or anything else) is ADVISORY — it may flag, never reject.
    #    Whole-image similarity is not an identity measurement, and saying so is
    #    more useful than a confident wrong number.
    if score < t["clip_flag_below"]:
        reasons.append(
            f"advisory: {backend} similarity {score:.3f} is low "
            f"(<{t['clip_flag_below']:.2f}). {backend} measures whole-image "
            "similarity, not identity, so this flags but cannot reject — install "
            "the arcface backend for an authoritative call.")
    else:
        reasons.append(
            f"advisory: {backend} similarity {score:.3f}; not an identity metric "
            "— human review still decides.")
    return {"decision": "review", "reasons": reasons, "gate": gate}


def summary_line(result: dict) -> str:
    """One line for the worker log / card."""
    g = result.get("gate", {})
    return (f"{result['decision'].upper()} "
            f"(identity={g.get('identity_score')} backend={g.get('identity_backend')})"
            f": {result['reasons'][0] if result.get('reasons') else ''}")
