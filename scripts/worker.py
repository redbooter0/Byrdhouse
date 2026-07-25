"""
worker.py — BYRD-GAMING worker daemon (Blueprint v2 §7: the factory shift).

Pulls jobs from the router (never pushed to), heartbeats, and runs the GPU
mode ritual: batch all IMAGE work, verify VRAM, then switch back to OPERATOR
and judge what was produced. Every artifact is registered with the router;
every image.generate auto-enqueues an image.judge (v2 §7.1 step 5).

Stdlib only. Run:  python scripts/worker.py [--no-gpu] [--once]
  --no-gpu   skip lms/nvidia-smi rituals (dev machines, CI, BYRD-MINI)
  --once     drain the queue once and exit (good for testing)
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import byrdimage  # noqa: E402
import byrdjudge  # noqa: E402
import byrdcaption  # noqa: E402
import byrdidentity  # noqa: E402
import byrdinventory  # noqa: E402
import byrdvideo  # noqa: E402
import compose_thumbnail  # noqa: E402

ROOT = Path(os.environ.get("BYRDHOUSE_ROOT") or sys.exit("BYRDHOUSE_ROOT not set"))
CFG = json.loads((ROOT / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
ROUTER = CFG["services"]["router"].rstrip("/")
TOKEN = CFG["auth"]["admin_token"]
WORKER_ID = f"worker-{socket.gethostname().lower()}"
CAPS = ["comfyui", "lmstudio"]
GPU_ENABLED = True

# Build identity — GAMING reports the exact commit it is running so the router
# (MINI) can flag when the two machines have drifted apart. API_VERSION must
# match the router's constant of the same name; bump both when the wire changes.
API_VERSION = "1"


def repo_build(start=None):
    """Best-effort git build id (short SHA + branch), stdlib-only, no subprocess.
    Reads .git directly so it reflects exactly what git sync left on disk."""
    try:
        p = Path(start or __file__).resolve()
        for d in [p] + list(p.parents):
            gitdir = d / ".git"
            if not gitdir.is_dir():
                continue
            head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
            if not head.startswith("ref:"):
                return {"sha": head[:12], "branch": "detached"}
            ref = head[4:].strip()
            branch = ref.rsplit("/", 1)[-1]
            reffile = gitdir / ref
            if reffile.exists():
                return {"sha": reffile.read_text(encoding="utf-8").strip()[:12], "branch": branch}
            packed = gitdir / "packed-refs"
            if packed.exists():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line and not line.startswith(("#", "^")) and line.endswith(ref):
                        return {"sha": line.split()[0][:12], "branch": branch}
            return {"sha": "unknown", "branch": branch}
    except Exception:
        pass
    return {"sha": "unknown", "branch": "unknown"}


BUILD = repo_build()
GPU_INFO = {"nvidia_smi": None, "available": None}  # filled by Gpu preflight (see below)


def api(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{ROUTER}{path}", data=data, method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}", "X-Actor": WORKER_ID})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _preview_bytes(path, max_side=896):
    """Downscale for the dashboard preview — the phone doesn't need the full
    SDXL PNG; the original stays on this machine's disk untouched."""
    try:
        from PIL import Image
        import io
        im = Image.open(path)
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "PNG", optimize=True)
            return buf.getvalue()
    except Exception:
        pass
    return Path(path).read_bytes()


def upload_preview(artifact_id, path):
    """Push the media bytes to the router so the dashboard can preview it —
    artifact files live on this machine's disk, not the router's. Content type
    follows the file so a video clip is cached (and served back) as video."""
    suffix = Path(path).suffix.lower()
    ctype = {".webm": "video/webm", ".mp4": "video/mp4"}.get(suffix, "image/png")
    data = Path(path).read_bytes() if ctype.startswith("video") else _preview_bytes(path)
    try:
        req = urllib.request.Request(
            f"{ROUTER}/artifacts/{artifact_id}/file", data=data,
            method="POST",
            headers={"Content-Type": ctype,
                     "Authorization": f"Bearer {TOKEN}", "X-Actor": WORKER_ID})
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
    except Exception as e:
        log(f"preview upload failed for {artifact_id}: {e}")  # non-fatal: card still registers


def fetch_artifact_file(artifact_id, dest_dir):
    """Pull an uploaded source image's bytes from the router to local disk so
    the compositor (which runs on this machine) can read the real pixels the
    dashboard sent — the file was saved on the router host, not here."""
    req = urllib.request.Request(
        f"{ROUTER}/artifacts/{artifact_id}/file",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Actor": WORKER_ID})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{artifact_id}.png"
    dest.write_bytes(data)
    return dest


def log(msg):
    print(f"[worker {datetime.now():%H:%M:%S}] {msg}", flush=True)


_GPU = None          # set in main(); lets heartbeat() report the live mode
_drift_warned = False


def heartbeat():
    """One heartbeat with full identity (build_sha/api_version/gpu) so MINI can
    see GAMING's exact commit and GPU health. Returns the router's response, or
    None on a network error (never fatal — the next beat retries). Logs ONCE if
    the router is on a different commit than this worker."""
    global _drift_warned
    mode = _GPU.mode if _GPU is not None else CFG["gpu"].get("default_mode", "OPERATOR")
    try:
        beat = api("/workers/heartbeat", {
            "id": WORKER_ID, "host": socket.gethostname(), "caps": CAPS, "mode": mode,
            "build_sha": BUILD["sha"], "api_version": API_VERSION, "gpu": GPU_INFO})
    except Exception as e:
        log(f"heartbeat failed (will retry): {e}")
        return None
    rsha = beat.get("router_build_sha")
    if rsha and rsha not in ("unknown", BUILD["sha"]) and not _drift_warned:
        log(f"⚠ VERSION DRIFT: this worker is on {BUILD['sha']} but the router "
            f"is on {rsha}. One machine did not git-pull — re-sync before trusting "
            f"the dashboard.")
        _drift_warned = True
    return beat


HEARTBEAT_SEC = 20  # background beat interval; < router WORKER_OFFLINE_SEC/4


def _heartbeat_thread():
    """Daemon: keep GAMING marked online while the main thread is busy inside a
    long generation. Pure liveness — mode-change requests are handled only by the
    main loop so GPU control never happens off the main thread."""
    while True:
        time.sleep(HEARTBEAT_SEC)
        heartbeat()


def _find_nvidia_smi():
    """Locate nvidia-smi even when it isn't on PATH — the exact failure on GAMING
    where a bare 'nvidia-smi' call raised and every IMAGE-mode switch died. Honors
    an optional gpu.nvidia_smi config override, then PATH, then the standard
    Windows install locations the NVIDIA driver uses. Returns a path or None."""
    override = CFG["gpu"].get("nvidia_smi", "")
    if override and not override.startswith("CHANGE_ME") and Path(override).exists():
        return override
    found = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if found:
        return found
    for cand in (r"C:\Windows\System32\nvidia-smi.exe",
                 r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if Path(cand).exists():
            return cand
    return None


def _lms_unload_all():
    if GPU_ENABLED:
        subprocess.run(["lms", "unload", "--all"], timeout=120)


def _lms_load(model: str):
    if GPU_ENABLED and model and not model.startswith("CHANGE_ME"):
        # full GPU offload first (the 3070 should carry the whole model);
        # older lms CLIs without --gpu fall back to a plain load
        r = subprocess.run(["lms", "load", model, "--gpu", "max", "-y"], timeout=600)
        if r.returncode != 0:
            subprocess.run(["lms", "load", model], timeout=600)


class Gpu:
    """The mode ritual (v2 §7.1). With --no-gpu every switch is a no-op."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.mode = CFG["gpu"].get("default_mode", "OPERATOR")
        self.nvidia_smi = _find_nvidia_smi() if enabled else None
        GPU_INFO["nvidia_smi"] = self.nvidia_smi
        if enabled:
            if not self.nvidia_smi:
                GPU_INFO["available"] = False
                log("⚠ GPU: nvidia-smi not found on PATH or standard locations. "
                    "IMAGE mode cannot verify VRAM and will refuse to switch. Set "
                    "gpu.nvidia_smi in byrdhouse.config.json to the full .exe path.")
            else:
                try:
                    used, total = self._vram()
                    GPU_INFO.update(available=True, vram_total_mb=total, vram_used_mb=used)
                    log(f"GPU: nvidia-smi at {self.nvidia_smi} — {total-used}MB free of {total}MB")
                except Exception as e:
                    GPU_INFO["available"] = False
                    log(f"⚠ GPU: nvidia-smi found but VRAM read failed: {e}")

    def _vram(self):
        exe = self.nvidia_smi or "nvidia-smi"
        out = subprocess.run(
            [exe, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout
        used, total = out.strip().splitlines()[0].split(",")
        return int(used.strip()), int(total.strip())

    def switch(self, target: str):
        if target == self.mode:
            return
        log(f"mode {self.mode} -> {target}")
        if self.enabled:
            # VIDEO needs the whole card exactly like IMAGE does (handoff §6:
            # unload LM Studio and image models before LTX/Wan loads), so it runs
            # the same verified-VRAM ritual rather than a second half-copy of it.
            if target in ("IMAGE", "VIDEO"):
                # Hard rule (v2 §7.1): a mode switch must VERIFY VRAM, never assume.
                # If nvidia-smi is missing we cannot verify, so we refuse loudly
                # rather than blindly loading ComfyUI onto an 8GB card that may
                # still hold the LLM.
                if not self.nvidia_smi:
                    raise RuntimeError(
                        f"cannot switch to {target}: nvidia-smi not found (set "
                        "gpu.nvidia_smi in byrdhouse.config.json). VRAM cannot be "
                        "verified.")
                subprocess.run(["lms", "unload", "--all"], timeout=120)
                threshold = int(CFG["gpu"].get("vram_free_threshold_mb", 1024))
                # A healthy SDXL run on the 3070 wants most of the 8GB free after
                # the LLM unloads; warn (don't block) when the configured gate is
                # met but headroom is still thin, so a future OOM isn't a mystery.
                sdxl_floor = int(CFG["gpu"].get("vram_image_healthy_mb", 5000))
                deadline = time.time() + 180
                while time.time() < deadline:
                    used, total = self._vram()
                    free = total - used
                    GPU_INFO.update(vram_total_mb=total, vram_used_mb=used)
                    if free >= threshold:
                        if free < sdxl_floor:
                            log(f"  ⚠ only {free}MB free (< {sdxl_floor}MB healthy for "
                                f"SDXL) — proceeding, but watch for OOM")
                        break
                    log(f"  waiting for VRAM: {free}MB free ({used}MB used)")
                    time.sleep(5)
                else:
                    raise RuntimeError("VRAM did not free — aborting mode switch")
            elif target == "OPERATOR":
                # Don't thrash LM Studio: OPERATOR just needs SOME text-capable
                # model up. If one is already loaded (e.g. the VL judge model,
                # which does text fine), use it — forcing a swap to a different
                # operator_model drops LM Studio's server/CORS state and makes
                # the next request fail. Only load when nothing is loaded.
                if not _loaded_models():
                    _lms_load(CFG["gpu"].get("operator_model", ""))
                else:
                    log("OPERATOR: a model is already loaded — using it (no reload)")
        self.mode = target
        heartbeat()  # report the new mode immediately (full identity payload)


def register_cards(job, cards):
    """One path for every generated image: register the cards, upload preview
    bytes for the dashboard, auto-enqueue the judge pass (v2 §7.1 step 5)."""
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": cards})
    for card in cards:
        upload_preview(card["artifact_id"], card["path"])
        api("/jobs", {"type": "image.judge", "project": card["project"],
                      "required_mode": "OPERATOR", "required_caps": ["lmstudio"],
                      "payload": {"artifact_id": card["artifact_id"],
                                  "path": card["path"]}})


def sync_profile_references(profile_id):
    """Profiles created/photo-uploaded through the dashboard live on the ROUTER
    host — but generation runs on THIS machine. Pull any reference photo this
    machine is missing (by artifact id) into the local profile dir, creating the
    profile skeleton if needed, and merge the router's ground-truth list into the
    local profile.json. Best-effort and additive: a hand-built local profile
    (like 'me' on GAMING) is never overwritten, only extended."""
    try:
        entry = next((p for p in api("/profiles") if p.get("id") == profile_id), None)
    except Exception as e:
        log(f"profile sync skipped ({e})")
        return
    if not entry:
        return
    ra = entry.get("reference_artifacts") or {}
    pdir = ROOT / "profiles" / profile_id
    refs_dir = pdir / "references"
    pfile = pdir / "profile.json"
    if not ra and pfile.exists():
        return  # nothing routable to fetch; local profile is the truth
    refs_dir.mkdir(parents=True, exist_ok=True)
    if pfile.exists():
        profile = json.loads(pfile.read_text(encoding="utf-8-sig"))
    else:
        profile = {"id": profile_id,
                   "display_name": entry.get("display_name", profile_id),
                   "references": {"ground_truth": [], "default_set": [],
                                  "available": []},
                   "identity_packs": entry.get("identity_packs", {})}
    refs = profile.setdefault("references", {})
    fetched = 0
    for name, aid in ra.items():
        dest = refs_dir / name
        if not dest.exists():
            try:
                fetch_artifact_file(aid, refs_dir).rename(dest)
                fetched += 1
            except Exception as e:
                log(f"profile '{profile_id}': fetch of {name} failed ({e})")
                continue
        for key, names in (("available", [name]),
                           ("ground_truth",
                            [name] if name in entry.get("ground_truth_names", [])
                            else [])):
            lst = refs.setdefault(key, [])
            for n in names:
                if n not in lst:
                    lst.append(n)
    pfile.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    if fetched:
        log(f"profile '{profile_id}': synced {fetched} reference photo(s) from the router")


def _profile_identity_pack(profile_id, family):
    """The subject's model pack for an engine family (profile.json
    identity_packs.<family>), but only if the LoRA is actually installed on THIS
    machine — a pack that exists on paper but not on disk must mean 'FaceID-only
    run', never a dead job. Returns the pack dict or None."""
    if not family:
        return None
    pfile = ROOT / "profiles" / str(profile_id) / "profile.json"
    if not pfile.exists():
        return None
    try:
        pack = json.loads(pfile.read_text(encoding="utf-8-sig")) \
            .get("identity_packs", {}).get(family)
    except Exception:
        return None
    if not pack or not pack.get("lora"):
        return None
    try:
        byrdimage.resolve_lora(ROOT, pack["lora"])
    except SystemExit:
        log(f"profile '{profile_id}' {family} pack '{pack['lora']}' not installed "
            f"on this machine — running on reference conditioning only")
        return None
    return pack


def resolve_profile_reference(root, profile_id, ground_truth_only=False):
    """Find the face reference photo for a subject profile.

    Handoff §5.1: camera photographs define identity geometry; generated/anime
    images are labelled SUPPORT and can never be ground truth. Identity
    conditioning (IP-Adapter FaceID) must therefore prefer `references.
    ground_truth` — conditioning identity on a synthetic face compounds drift,
    which is one reason the likeness kept slipping."""
    pdir = root / "profiles" / profile_id
    pfile = pdir / "profile.json"
    if not pfile.exists():
        log(f"profile '{profile_id}' not found at {pdir}")
        return None
    profile = json.loads(pfile.read_text(encoding="utf-8"))
    refs = profile.get("references", {})
    ground_truth = refs.get("ground_truth", [])
    for name in ground_truth:
        ref = pdir / "references" / name
        if ref.exists():
            log(f"profile '{profile_id}' ground-truth reference: {ref.name}")
            return str(ref)
    if ground_truth_only:
        log(f"profile '{profile_id}': no ground-truth (real photo) reference "
            f"available — refusing to condition identity on generated support "
            f"material")
        return None
    default_set = refs.get("default_set", [])
    for name in default_set:
        ref = pdir / "references" / name
        if ref.exists():
            log(f"profile '{profile_id}' reference: {ref.name}")
            return str(ref)
    refs_dir = pdir / "references"
    if refs_dir.is_dir():
        photos = [f for f in refs_dir.iterdir()
                  if f.suffix.lower() in (".jpg", ".jpeg", ".png") and f.name != ".gitkeep"]
        if photos:
            pick = sorted(photos)[0]
            log(f"profile '{profile_id}' fallback reference: {pick.name}")
            return str(pick)
    log(f"profile '{profile_id}' has no reference photos in {refs_dir}")
    return None


def run_generate(job) -> None:
    p = json.loads(job["payload"])
    recipe_path = byrdimage.find_recipe(ROOT, p["recipe"])
    recipe_data = byrdimage.load_json(recipe_path)

    # Uploaded face-zone edits are outlined on CPU before ComfyUI touches the
    # image. The saved mesh/masks make the edit boundary auditable, while only
    # the final skin-matched composite is registered as the job result.
    if recipe_data.get("runner") == "face_zone_identity_edit":
        target_artifact = p.get("target_artifact")
        if not target_artifact:
            raise RuntimeError("face-zone identity edit needs target_artifact from the Create upload")
        target = fetch_artifact_file(target_artifact, ROOT / "artifacts" / "_sources")
        profile_id = p.get("subject_profile") or recipe_data.get("subject_profile")
        _, saved = byrdimage.edit_face_zone(
            ROOT, p["recipe"], target, p.get("project", "sandbox"),
            p.get("purpose", "CPU outlined face-zone identity edit"),
            slots=p.get("slots", {}), checkpoint=p.get("checkpoint"),
            identity_lora=p.get("identity_lora") or p.get("lora"),
            identity_strength=p.get("identity_strength") or p.get("lora_strength"),
            target_preset=p.get("target_preset"), subject_profile=profile_id,
            seed=p.get("seed"), engine=p.get("engine"), job_id=job["id"])
        cards = []
        for png, card in saved:
            card["path"] = str(png)
            cards.append(card)
        register_cards(job, cards)
        return

    # Compact target identity edits stay inside the ordinary image.generate
    # contract: router -> GAMING pull worker -> Comfy -> card/preview/judge.
    # They need two independently addressed images (the target plus the stored
    # identity LoRA), so they cannot use the one-reference generic generator.
    if recipe_data.get("runner") == "target_identity_edit":
        target_artifact = p.get("target_artifact")
        if not target_artifact:
            raise RuntimeError("target identity edit needs target_artifact from the Create upload")
        target = fetch_artifact_file(target_artifact, ROOT / "artifacts" / "_sources")
        profile_id = p.get("subject_profile") or recipe_data.get("subject_profile")
        _, saved = byrdimage.edit_target_identity(
            ROOT, p["recipe"], target, p.get("project", "sandbox"),
            p.get("purpose", "anime target identity edit"), slots=p.get("slots", {}),
            checkpoint=p.get("checkpoint"), identity_lora=p.get("identity_lora"),
            identity_strength=p.get("identity_strength"),
            target_preset=p.get("target_preset"), target_mask=p.get("target_mask"),
            subject_profile=profile_id, seed=p.get("seed"), engine=p.get("engine"),
            job_id=job["id"])
        cards = []
        for png, card in saved:
            card["path"] = str(png)
            cards.append(card)
        register_cards(job, cards)
        return

    # A reference_artifact (an uploaded real screenshot / key art) steers the
    # generation toward that game's look via IP-Adapter — fetch it to local disk
    # first, exactly like the source-composite path.
    reference = None
    if p.get("reference_artifact"):
        reference = str(fetch_artifact_file(p["reference_artifact"],
                                            ROOT / "artifacts" / "_sources"))

    # Creator V1: if the recipe declares a subject_profile and no explicit
    # reference was given, auto-wire the profile's face reference photo.
    # The profile can come from the payload (dashboard) or the recipe itself.
    profile_id = p.get("subject_profile")
    if not profile_id:
        profile_id = recipe_data.get("subject_profile")
    # An identity recipe may demand camera-photo conditioning only (handoff §5.1).
    # If the profile has no real ground-truth photo we fail loudly rather than
    # quietly conditioning the likeness on generated support material.
    ref_policy = (recipe_data.get("reference_policy") or {}).get("source", "")
    gt_only = ref_policy == "ground_truth"
    if profile_id:
        # Dashboard-created subjects live on the router host first — pull any
        # missing reference photos to this machine before resolving.
        sync_profile_references(profile_id)
        # The subject's own model pack for this engine family (handoff §3: the
        # profile is the identity truth). Explicit payload lora always wins.
        pack = None if p.get("lora") else _profile_identity_pack(
            profile_id, recipe_data.get("model_family"))
        if pack:
            p["lora"] = pack["lora"]
            p["lora_strength"] = pack.get("strength", 0.9)
            log(f"identity pack for '{profile_id}': {pack['lora']} "
                f"@ {p['lora_strength']}")
    if not reference and profile_id:
        reference = resolve_profile_reference(ROOT, profile_id, ground_truth_only=gt_only)
        if gt_only and not reference:
            raise RuntimeError(
                f"recipe '{p['recipe']}' requires a ground-truth (real camera) "
                f"reference photo, but profile '{profile_id}' has none listed in "
                f"references.ground_truth. Add real photos — identity must not be "
                f"conditioned on generated support material.")
    job_id, saved = byrdimage.generate(
        ROOT, p["recipe"], p.get("slots", {}), p.get("project", "sandbox"),
        p.get("purpose", "unspecified"), batch=p.get("batch"),
        checkpoint=p.get("checkpoint"), job_id=job["id"],
        aspect=p.get("aspect"), width=p.get("width"), height=p.get("height"),
        negative_extra=p.get("negative"), lora=p.get("lora"),
        lora_strength=float(p.get("lora_strength", 0.9)), seed=p.get("seed"),
        reference=reference, subject_profile=profile_id, engine=p.get("engine"))
    cards = []
    for png, card in saved:
        card["path"] = str(png)
        cards.append(card)
    register_cards(job, cards)


def run_faceswap(job) -> None:
    """image.faceswap: put a face onto an existing image via ReActor. The face
    defaults to the founder's profile photo (profiles/me/references) exactly like
    the me-recipes; the target arrives as an uploaded artifact (dashboard) or a
    local path (already on this machine). style_blend > 0 adds the low-denoise
    img2img pass that melts the swap into stylized/anime art."""
    p = json.loads(job["payload"])
    dest = ROOT / "artifacts" / "_sources"
    target = p.get("target_path")
    if not target and p.get("target_artifact"):
        target = str(fetch_artifact_file(p["target_artifact"], dest))
    if not target:
        raise RuntimeError("image.faceswap needs target_path or target_artifact")

    # EXAMINE route (the founder contract): the CPU examiner reports every
    # face, where the belt can and can't operate, risk flags, and the
    # per-feature likeness plan — archives a clean overview + verdict, edits
    # nothing. Works in any GPU mode; also runs automatically as the gate
    # inside the quality lane (edit_face_zone).
    if p.get("route") == "examine":
        _, saved = byrdimage.facezone_examine(
            ROOT, target, p.get("project", "sandbox"),
            p.get("purpose", "face report"),
            min_confidence=float(p.get("min_face_confidence", 0.35)),
            thorough=bool(p.get("thorough", True)),
            job_id=job["id"])
        cards = []
        for png, card in saved:
            card["path"] = str(png)
            cards.append(card)
        register_cards(job, cards)
        return

    # PREVIEW route (the CPU pre-step): detection only — archives the zone
    # overlay + soft mask for approval, no checkpoint, no diffusion. The GPU
    # never decides the mask (the founder rule); the approved mask artifact
    # then feeds the zone route below.
    if p.get("route") == "preview":
        _, saved = byrdimage.facezone_preview(
            ROOT, target, p.get("project", "sandbox"),
            p.get("purpose", "zone preview"),
            detector=p.get("detector"), threshold=p.get("threshold"),
            job_id=job["id"])
        cards = []
        for png, card in saved:
            card["path"] = str(png)
            cards.append(card)
        register_cards(job, cards)
        return

    # AUTO route (the daily driver): detector finds the face, masks it, redraws
    # it as the founder (LoRA + prompt) in the target's art style — one step.
    if p.get("route") == "auto" or p.get("auto"):
        _, saved = byrdimage.facezone_auto(
            ROOT, target, p.get("project", "sandbox"),
            p.get("purpose", "auto face zone"),
            prompt=p.get("prompt"), negative=p.get("negative"),
            denoise=p.get("denoise"), checkpoint=p.get("checkpoint"),
            lora=p.get("lora"), lora_strength=float(p.get("lora_strength", 0.9)),
            detector=p.get("detector"), seed=p.get("seed"), job_id=job["id"])
        cards = []
        for png, card in saved:
            card["path"] = str(png)
            cards.append(card)
        register_cards(job, cards)
        return

    # Zone route (the founder lane): a mask means the GPU edits ONLY inside the
    # approved zone — identity comes from the LoRA + prompt, no face photo needed.
    mask = p.get("mask_path")
    if not mask and p.get("mask_artifact"):
        mask = str(fetch_artifact_file(p["mask_artifact"], dest))
    if mask:
        _, saved = byrdimage.faceswap_inpaint(
            ROOT, target, mask, p.get("project", "sandbox"),
            p.get("purpose", "zone edit"),
            prompt=p.get("prompt"), negative=p.get("negative"),
            denoise=p.get("denoise"), checkpoint=p.get("checkpoint"),
            lora=p.get("lora"), lora_strength=float(p.get("lora_strength", 0.9)),
            seed=p.get("seed"), job_id=job["id"])
        cards = []
        for png, card in saved:
            card["path"] = str(png)
            cards.append(card)
        register_cards(job, cards)
        return

    face = p.get("face_path")
    if not face and p.get("face_artifact"):
        face = str(fetch_artifact_file(p["face_artifact"], dest))
    if not face:
        face = resolve_profile_reference(ROOT, p.get("subject_profile") or "me")
    if not face:
        raise RuntimeError("image.faceswap has no face: put photos in "
                           "profiles/me/references/ or pass face_path/face_artifact")
    _, saved = byrdimage.faceswap(
        ROOT, target, face, p.get("project", "sandbox"),
        p.get("purpose", "face swap"),
        style_blend=float(p.get("style_blend", 0) or 0),
        prompt=p.get("prompt"), negative=p.get("negative"),
        checkpoint=p.get("checkpoint"), lora=p.get("lora"),
        lora_strength=float(p.get("lora_strength", 0.9)),
        restore=p.get("restore"), seed=p.get("seed"), job_id=job["id"])
    cards = []
    for png, card in saved:
        card["path"] = str(png)
        cards.append(card)
    register_cards(job, cards)


def run_identity_variation(job) -> None:
    """image.identity_variation: redraw an existing image AS a subject — the
    'make this look like me / them' route. Source pixels set composition and
    pose; the subject profile supplies the face (ground-truth photo via FaceID
    + the profile's identity pack when installed). Fails closed without a real
    photo of the subject: likeness is never conditioned on generated material."""
    p = json.loads(job["payload"])
    recipe = byrdimage.load_json(byrdimage.find_recipe(ROOT, p["recipe"]))
    recipe_tag = f"{recipe['id']}@{recipe['version']}"
    profile_id = p.get("subject_profile") or recipe.get("subject_profile") or "me"
    sync_profile_references(profile_id)
    gt_only = (recipe.get("reference_policy") or {}).get("source") == "ground_truth"
    reference = resolve_profile_reference(ROOT, profile_id, ground_truth_only=gt_only)
    if not reference:
        raise RuntimeError(
            f"identity variation needs a real (ground-truth) photo of "
            f"'{profile_id}' — upload one through People / POST "
            f"/profiles/{profile_id}/references first.")

    source = p.get("source_path")
    if not source and p.get("source_artifact"):
        source = str(fetch_artifact_file(p["source_artifact"],
                                         ROOT / "artifacts" / "_sources"))
    if not source:
        raise RuntimeError("identity variation needs source_path or source_artifact "
                           "(the image to redraw)")

    lora, strength, clip = p.get("lora"), float(p.get("lora_strength", 0.9)), None
    if not lora:
        pack = _profile_identity_pack(profile_id, recipe.get("model_family"))
        if pack:
            lora = pack["lora"]
            strength = float(pack.get("strength", 0.9))
            clip = pack.get("clip_strength")
            log(f"identity pack for '{profile_id}': {lora} @ {strength}")

    defaults = recipe.get("defaults", {})
    _, saved = byrdimage.identity_variation(
        ROOT, source, reference, p.get("project", "sandbox"),
        p.get("purpose", f"identity variation as {profile_id}"),
        recipe.get("workflow", "workflows/sdxl_ipadapter_face_img2img_api.json"),
        recipe_tag, prompt=p.get("prompt"), negative=p.get("negative"),
        denoise=float(p.get("denoise", defaults.get("denoise", 0.5))),
        checkpoint=p.get("checkpoint") or defaults.get("checkpoint"),
        lora=lora, lora_strength=strength, lora_clip_strength=clip,
        batch=int(p.get("batch", defaults.get("batch", 1))),
        seed=p.get("seed"), subject_profile=profile_id, job_id=job["id"])
    cards = []
    for png, card in saved:
        card["path"] = str(png)
        cards.append(card)
    register_cards(job, cards)


def run_content_enhance(job) -> None:
    """OPERATOR-mode pass: the local model rewrites the founder's words into an
    SDXL-engineered prompt, then enqueues the actual generation. Two jobs
    because GPU modes are exclusive — the LLM isn't loaded while ComfyUI runs."""
    p = json.loads(job["payload"])
    original = (p.get("slots") or {}).get("prompt") or ""
    if not original:
        raise RuntimeError("content.enhance needs slots.prompt to rewrite")
    answer = _lms_chat(
        "You are the ByrdHouse prompt engineer for SDXL image generation. Rewrite "
        "the request below into ONE vivid SDXL prompt: subject first, then setting, "
        "composition, art style, lighting, color mood — comma-separated descriptors, "
        "under 60 words, no quotes, no explanations, keep every specific game/brand/"
        "person mentioned.\nRequest: " + original, max_tokens=200).strip()
    enhanced = answer.splitlines()[-1].strip().strip('"') or original
    log(f"enhanced prompt: {enhanced[:120]}")
    gen_payload = dict(p, slots=dict(p.get("slots") or {}, prompt=enhanced),
                       enhanced_from=original)
    gen_payload.pop("enhance", None)
    api("/jobs", {"type": "image.generate", "project": p.get("project", "sandbox"),
                  "required_mode": "IMAGE", "required_caps": ["comfyui"],
                  "payload": gen_payload})


def run_refine(job) -> None:
    """image.refine / image.upscale: img2img over an existing artifact —
    low strength polishes and upscales, higher strength makes variations."""
    p = json.loads(job["payload"])
    _, saved = byrdimage.refine(
        ROOT, p["source_path"], p.get("project", "sandbox"),
        p.get("purpose", "refine"), prompt=p.get("prompt"),
        negative=p.get("negative"), strength=float(p.get("strength", 0.4)),
        scale=float(p.get("scale", 1.6)), checkpoint=p.get("checkpoint"),
        lora=p.get("lora"), batch=int(p.get("batch", 1)), job_id=job["id"])
    cards = []
    for png, card in saved:
        card["path"] = str(png)
        cards.append(card)
    register_cards(job, cards)


def run_judge(job) -> None:
    p = json.loads(job["payload"])
    image_path = Path(p["path"])
    card_path = image_path.with_suffix(image_path.suffix + ".json")
    card = json.loads(card_path.read_text(encoding="utf-8-sig")) if card_path.exists() else dict(p)
    jm = CFG["gpu"].get("judge_model", "")
    if jm and not jm.startswith("CHANGE_ME") and jm not in _loaded_models():
        _lms_unload_all()
        _lms_load(jm)
    # else: judge with whatever vision model is loaded (byrdjudge enforces vision)
    try:
        verdict = byrdjudge.judge_card(ROOT, card, image_path)
    except byrdjudge.NoVisionModel as e:
        # A score is only trustworthy from a model that can see the image.
        # Leave the artifact unjudged (score stays null → the learn loop ignores
        # it, the founder reviews manually) rather than inventing a number.
        log(f"SKIP judge {p['artifact_id']}: {e}")
        api(f"/artifacts/{p['artifact_id']}/review",
            {"action": "unjudged", "reason": str(e)})
        return
    card.update(score=verdict["score"], tags=verdict["tags"], caption=verdict["caption"])
    card["rubric_scores"] = verdict["scores"]
    identity = {k: verdict[k] for k in verdict if k.startswith("identity_")}
    if identity:
        card["identity"] = identity
        log(f"identity {p['artifact_id']}: score={identity.get('identity_score')} "
            f"backend={identity.get('identity_backend')} "
            f"guess={identity.get('identity_method_guess')}")
    if card_path.exists():
        card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    review = {"action": "judge", "score": verdict["score"], "tags": verdict["tags"],
              "caption": verdict["caption"]}
    if identity:
        review["identity"] = identity
    api(f"/artifacts/{p['artifact_id']}/review", review)

    # The ACCEPTANCE GATE (handoff §4.2): measuring identity is not enough — a
    # recolour must not sit in needs_review looking like a candidate. Fail closed
    # on a proven recolor/no-identity result; never auto-reject what we couldn't
    # measure, and never silently auto-approve either.
    if identity:
        decision = byrdidentity.evaluate(card, identity, CFG)
        card["identity_gate"] = decision
        if card_path.exists():
            card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
        log(f"identity gate {p['artifact_id']}: {byrdidentity.summary_line(decision)}")
        if decision["decision"] == "reject":
            api(f"/artifacts/{p['artifact_id']}/review",
                {"action": "reject", "reason": "; ".join(decision["reasons"])})


def run_caption(job) -> None:
    """image.caption: describe an existing artifact with the LM Studio vision
    model (OPERATOR mode, same lane as the judge) and write the caption + tags
    back onto its card. Deliberate dataset/library work — NOT auto-enqueued after
    every generation the way the judge is. No vision model => honestly skip."""
    p = json.loads(job["payload"])
    image_path = Path(p["path"])
    card_path = image_path.with_suffix(image_path.suffix + ".json")
    card = json.loads(card_path.read_text(encoding="utf-8-sig")) if card_path.exists() else dict(p)
    cm = byrdcaption._caption_model(CFG)  # caption_model or judge_model
    if cm and not cm.startswith("CHANGE_ME") and cm not in _loaded_models():
        _lms_unload_all()
        _lms_load(cm)
    # else: caption with whatever vision model is loaded (byrdcaption enforces vision)
    try:
        result = byrdcaption.caption_image(
            ROOT, image_path, trigger=p.get("trigger", ""),
            style=p.get("style", "lora"), max_words=int(p.get("max_words", 40)),
            context=p.get("context", ""))
    except byrdcaption.NoVisionModel as e:
        # A caption is only trustworthy from a model that can see the image —
        # leave the artifact uncaptioned rather than inventing words.
        log(f"SKIP caption {p.get('artifact_id')}: {e}")
        if p.get("artifact_id"):
            api(f"/artifacts/{p['artifact_id']}/review",
                {"action": "uncaptioned", "reason": str(e)})
        return
    card["caption"] = result["caption"]
    if result["tags"]:
        card["tags"] = result["tags"]
    card["caption_model"] = result["model"]
    if card_path.exists():
        card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    if p.get("artifact_id"):
        api(f"/artifacts/{p['artifact_id']}/review",
            {"action": "caption", "caption": result["caption"], "tags": result["tags"]})
    log(f"captioned {p.get('artifact_id') or image_path.name}: {result['caption'][:80]}")


def run_video_i2v(job) -> None:
    """video.i2v: animate ONE APPROVED identity still (handoff §7).

    VIDEO RULE — the first frame must already be an approved identity artifact.
    We do not ask the video model to rediscover the subject: if the source still
    is not approved, this refuses. That keeps drift a video problem instead of an
    identity problem, and stops a rejected recolour from becoming a rejected
    video 20 minutes later."""
    p = json.loads(job["payload"])
    still = p.get("still_path")
    source_artifact = p.get("source_artifact")

    if source_artifact:
        arts = api(f"/artifacts?id={source_artifact}")
        art = arts[0] if arts else None
        if not art:
            raise RuntimeError(f"video.i2v: no such source artifact {source_artifact}")
        if art.get("status") != "approved":
            raise RuntimeError(
                f"video.i2v REFUSED: source still {source_artifact} is "
                f"'{art.get('status')}', not 'approved'. The first frame must be an "
                f"approved identity artifact — approve the still in the Library "
                f"first, or fix the identity before spending VIDEO mode on it.")
        if not still:
            still = art.get("path")
            if not still or not Path(still).exists():
                still = str(fetch_artifact_file(source_artifact, ROOT / "artifacts" / "_sources"))
    elif not p.get("allow_unapproved"):
        raise RuntimeError(
            "video.i2v REFUSED: pass source_artifact (an APPROVED still) so the "
            "clip is traceable to a judged identity. Only an explicit "
            "allow_unapproved=true may animate a loose file, and that clip is "
            "marked as such on its card.")
    if not still:
        raise RuntimeError("video.i2v needs still_path or source_artifact")

    _, saved = byrdvideo.animate(
        ROOT, still, p.get("project", "careyrpg"),
        p.get("purpose", "identity still -> motion"),
        prompt=p.get("prompt", ""), negative=p.get("negative"),
        seed=p.get("seed"), width=p.get("width"), height=p.get("height"),
        length=p.get("length"), fps=p.get("fps"), steps=p.get("steps"),
        cfg_scale=p.get("cfg"), workflow=p.get("workflow"),
        job_id=job["id"], source_artifact=source_artifact)
    cards = []
    for path, card in saved:
        card["path"] = str(path)
        if not source_artifact:
            card["unapproved_source"] = True
        cards.append(card)
    # Video cards register like any artifact, but they are NOT auto-judged: the
    # image judge scores stills. Frame-level drift examination (video.examine,
    # handoff §7.3) is the next rung and lands separately.
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": cards})
    for card in cards:
        # ship the clip bytes to the router so the dashboard can PLAY it —
        # in 2-PC mode the webm lives on this machine, not the router host
        upload_preview(card["artifact_id"], card["path"])
        log(f"video archived {card['artifact_id']} "
            f"({card.get('duration_seconds')}s @ {card.get('fps')}fps)")


def run_inventory(job) -> None:
    """inventory.scan: refresh ByrdHouse's memory of everything on this host —
    models, custom nodes, workflows (API vs UI-format), recipes, profile
    reference counts, artifacts — and flag dead weight the 8GB 3070 can't use.
    Writes docs/ASSET_INVENTORY.md + artifacts/inventory.json and registers the
    report as an approved artifact. Runs in ANY mode (no GPU)."""
    inv = byrdinventory.scan_inventory(ROOT)
    md_path, json_path = byrdinventory.write_reports(ROOT, inv)
    log(f"inventory: {sum(d['count'] for d in inv['models'].values())} weights, "
        f"{len(inv['custom_nodes'])} nodes, {inv['workflows']['count']} workflows, "
        f"{len(inv['flags'])} flags")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": "byrdhouse", "kind": "inventory",
        "path": str(md_path), "purpose": "asset inventory (what ByrdHouse has)",
        "status": "approved", "flags": inv["flags"],
        "created_at": datetime.now(timezone.utc).isoformat()}]})


def run_report(job) -> None:
    report = api("/reports/daily")
    out_dir = ROOT / "artifacts" / "reports" / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"daily_{datetime.now():%Y%m%d}_{job['id']}.md"
    dest.write_text(report["markdown"], encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": "byrdhouse", "kind": "report",
        "path": str(dest), "purpose": "daily report", "status": "approved",
        "created_at": datetime.now(timezone.utc).isoformat()}]})


def run_content_thumbnail(job) -> None:
    """v3.1 §3 two-pass: generate the ART (no text), then composite REAL text.
    payload.image_path skips pass 1 entirely — real screenshots and box art
    beat diffused lookalikes for virality, so bring-your-own-image is first-class."""
    p = json.loads(job["payload"])
    title = p.get("title") or ""
    if not title:
        raise RuntimeError("content.thumbnail needs payload.title")

    # A source can arrive two ways: a path already on this worker (image_path)
    # or a real image the founder uploaded through the dashboard, saved on the
    # router and referenced by artifact id (source_artifact) — fetch that here.
    src = p.get("image_path")
    src_art = p.get("source_artifact")
    if src or src_art:
        if src_art and not src:
            png = fetch_artifact_file(src_art, ROOT / "artifacts" / "_sources")
        else:
            png = Path(src)
            if not png.exists():
                raise RuntimeError(f"image_path not found on this worker: {png}")
        month_dir = ROOT / "artifacts" / p.get("project", "careyrpg") / f"{datetime.now():%Y-%m}"
        final = month_dir / f"{png.stem}_{job['id']}_final.png"
        compose_thumbnail.compose(
            png, title, final, zone=p.get("zone", "bottom"),
            palette=p.get("palette", "black-gold"), style=p.get("style", "banner"))
        card = {"artifact_id": f"art.{job['id']}.0", "job_id": job["id"],
                "project": p.get("project", "careyrpg"), "kind": "thumbnail",
                "path": str(final), "title": title, "source_image": str(png),
                "source_artifact": src_art,
                "purpose": p.get("purpose", "thumbnail"), "prompt": "",
                "slots": {}, "score": None, "tags": [], "caption": "",
                "status": "draft",
                "created_at": datetime.now(timezone.utc).isoformat()}
        final.with_suffix(".png.json").write_text(json.dumps(card, indent=2),
                                                  encoding="utf-8")
        register_cards(job, [card])
        return

    recipe_spec = byrdimage.load_json(byrdimage.find_recipe(ROOT, p["recipe"]))
    _, saved = byrdimage.generate(
        ROOT, p["recipe"], p.get("slots", {}), p.get("project", "careyrpg"),
        p.get("purpose", "thumbnail"), batch=p.get("batch"),
        checkpoint=p.get("checkpoint"), job_id=job["id"])
    compose_cfg = recipe_spec.get("compose", {})
    cards = []
    for png, card in saved:
        final = png.with_name(png.stem + "_final.png")
        compose_thumbnail.compose(
            png, title, final,
            zone=compose_cfg.get("text_zone", "upper-left"),
            palette=card.get("vary_picks", {}).get("palette", "default"),
            max_words=compose_cfg.get("max_words", 5),
            style=compose_cfg.get("style", "accent"))
        card = dict(card, kind="thumbnail", path=str(final), title=title,
                    artifact_id=card["artifact_id"] + "f")
        final.with_suffix(".png.json").write_text(json.dumps(card, indent=2),
                                                  encoding="utf-8")
        cards.append(card)
    register_cards(job, cards)


def _loaded_models() -> list:
    try:
        with urllib.request.urlopen(
                CFG["services"]["lmstudio"].rstrip("/") + "/models", timeout=8) as r:
            return [m["id"] for m in json.loads(r.read().decode()).get("data", [])]
    except Exception:
        return []


def _lms_chat(prompt: str, max_tokens=900) -> str:
    model = CFG["gpu"].get("operator_model", "")
    if not model or model.startswith("CHANGE_ME"):
        # interchangeable: no configured operator -> use whatever is loaded
        loaded = _loaded_models()
        if not loaded:
            raise RuntimeError("gpu.operator_model not set and nothing loaded in LM Studio")
        model = loaded[0]
        log(f"operator_model not set — using loaded model '{model}'")
    elif model not in _loaded_models():
        _lms_unload_all()
        _lms_load(model)
    lms = CFG["services"]["lmstudio"].rstrip("/")
    req = urllib.request.Request(
        f"{lms}/chat/completions",
        data=json.dumps({"model": model, "temperature": 0.7, "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]


def run_content_package(job) -> None:
    """v3.1 §2: transcript -> titles/tags/description/pinned comment in YOUR voice."""
    import re as _re
    p = json.loads(job["payload"])
    transcript = p.get("transcript_text") or Path(p["transcript_path"]).read_text(encoding="utf-8-sig")
    voice_path = ROOT / "recipes" / "voice_carey.json"
    voice = json.loads(voice_path.read_text(encoding="utf-8-sig")) if voice_path.exists() else {}
    prompt = (
        "You write YouTube packaging for the channel "
        f"{voice.get('channel', 'CareyRPG')} ({voice.get('niche', 'gaming')}). "
        f"Write EXACTLY in the voice of these real examples: {json.dumps(voice.get('examples', {}))}. "
        f"Rules: {json.dumps(voice.get('rules', []))}.\n\n"
        f"Video transcript (may be truncated):\n{transcript[:6000]}\n\n"
        "Reply with ONLY a JSON object: {\"titles\": [5 options], \"tags\": [12-18 tags], "
        "\"description\": \"2 short paragraphs + timestamps placeholder\", "
        "\"pinned_comment\": \"one comment\"}")
    content = _lms_chat(prompt)
    m = _re.search(r"\{.*\}", content, _re.DOTALL)
    if not m:
        raise RuntimeError(f"packager returned no JSON: {content[:200]}")
    package = json.loads(m.group(0))
    out_dir = ROOT / "artifacts" / p.get("project", "careyrpg") / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"package_{job['id']}.json"
    dest.write_text(json.dumps(package, indent=2), encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": p.get("project", "careyrpg"),
        "kind": "package", "path": str(dest),
        "purpose": p.get("purpose", "video packaging"), "status": "draft",
        "titles": package.get("titles", []),
        "created_at": datetime.now(timezone.utc).isoformat()}]})


def run_content_research(job) -> None:
    """v3.1 §2: outlier CSV (manual export) -> ranked video ideas artifact."""
    import csv
    p = json.loads(job["payload"])
    rows = []
    with open(p["csv_path"], newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            norm = {k.lower().strip(): (v or "").strip() for k, v in row.items()}
            def num(*keys):
                for k in keys:
                    try:
                        return float(norm.get(k, "").replace("x", "").replace(",", ""))
                    except ValueError:
                        continue
                return 0.0
            rows.append({"title": norm.get("title") or norm.get("video") or "?",
                         "multiplier": num("multiplier", "outlier", "x"),
                         "vph": num("vph", "views per hour", "viewsperhour")})
    rows.sort(key=lambda r: (r["multiplier"], r["vph"]), reverse=True)
    top = rows[: int(p.get("top", 5))]
    md = [f"# This week's video ideas — {datetime.now():%Y-%m-%d}",
          "", "Ranked by outlier multiplier, then views/hour:", ""]
    md += [f"{i+1}. **{r['title']}** — {r['multiplier']:g}x, {r['vph']:g} VPH"
           for i, r in enumerate(top)]
    out_dir = ROOT / "artifacts" / p.get("project", "careyrpg") / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"ideas_{job['id']}.md"
    dest.write_text("\n".join(md), encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": p.get("project", "careyrpg"),
        "kind": "ideas", "path": str(dest), "purpose": "weekly topic research",
        "status": "draft", "created_at": datetime.now(timezone.utc).isoformat()}]})


def run_export_csv(job) -> None:
    """Exports Room: dump artifacts (or jobs) to a CSV artifact."""
    import csv
    p = json.loads(job["payload"])
    what = p.get("what", "artifacts")
    if what not in ("artifacts", "jobs"):
        raise RuntimeError("export.csv payload.what must be artifacts|jobs")
    rows = api(f"/{what}?limit={int(p.get('limit', 1000))}")
    out_dir = ROOT / "artifacts" / "exports" / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{what}_{datetime.now():%Y%m%d}_{job['id']}.csv"
    if rows:
        with open(dest, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    else:
        dest.write_text("", encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": "byrdhouse", "kind": "export",
        "path": str(dest), "purpose": f"{what} export", "status": "approved",
        "created_at": datetime.now(timezone.utc).isoformat()}]})


RUNNERS = {"image.generate": run_generate, "image.judge": run_judge,
           "image.identity_generate": run_generate,
           "image.identity_variation": run_identity_variation,
           "image.caption": run_caption,
           "image.faceswap": run_faceswap,
           "image.refine": run_refine, "image.upscale": run_refine,
           "report.daily": run_report, "inventory.scan": run_inventory,
           "video.i2v": run_video_i2v,
           "content.enhance": run_content_enhance,
           "content.thumbnail": run_content_thumbnail,
           "content.package": run_content_package,
           "content.research": run_content_research,
           "export.csv": run_export_csv}


def desired_mode(gpu: Gpu) -> str:
    """v2 §7: enter IMAGE when >=3 image jobs queued OR oldest older than 10 min;
    otherwise OPERATOR (judging happens there). VIDEO wins outright when queued —
    a clip is a long, deliberate, founder-initiated run and the 3070 cannot hold a
    video model beside anything else (handoff §6), so we do not batch-wait it."""
    queued = api("/jobs?status=queued&limit=100")
    video_jobs = [j for j in queued if j["required_mode"] == "VIDEO"]
    if video_jobs:
        return "VIDEO"
    image_jobs = [j for j in queued if j["required_mode"] == "IMAGE"]
    operator_jobs = [j for j in queued if j["required_mode"] in ("OPERATOR", "ANY")]
    if image_jobs:
        oldest = min(j["created_at"] for j in image_jobs)
        age_min = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(oldest)).total_seconds() / 60
        if len(image_jobs) >= 3 or age_min > 10 or not operator_jobs:
            return "IMAGE"
    if operator_jobs:
        return "OPERATOR"
    return gpu.mode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=float, default=5.0)
    args = ap.parse_args()
    global GPU_ENABLED
    GPU_ENABLED = not args.no_gpu

    global _GPU
    gpu = Gpu(enabled=GPU_ENABLED)
    _GPU = gpu  # heartbeat() (incl. the background thread) reports gpu.mode
    log(f"{WORKER_ID} starting — router {ROUTER}, mode {gpu.mode}, "
        f"gpu={'on' if gpu.enabled else 'off'}, build {BUILD['sha']}")

    # Continuous liveness: a daemon thread beats every HEARTBEAT_SEC so a long
    # generation (which blocks this main thread inside runner()) never makes
    # GAMING look dead to MINI's reaper. Skipped under --once so the drain-once
    # test path stays deterministic. A crashed process kills the daemon too, so
    # real failures still stop heartbeating and get reaped.
    if not args.once:
        threading.Thread(target=_heartbeat_thread, daemon=True, name="heartbeat").start()
        log("heartbeat thread up — GAMING stays visible to MINI during long jobs")

    last_beat = 0.0
    idle_streak = 0

    while True:
        try:
            if time.time() - last_beat > 30:
                beat = heartbeat()
                last_beat = time.time()
                req = beat.get("requested_mode") if beat else None
                if req and req != gpu.mode:  # dashboard/manual mode request
                    gpu.switch(req)
                    api("/mode", {"mode": ""})  # clear the request

            gpu.switch(desired_mode(gpu))
            job = api("/jobs/claim", {"worker_id": WORKER_ID, "caps": CAPS, "mode": gpu.mode})
            if not job or not job.get("id"):
                idle_streak += 1
                if args.once and idle_streak >= 2:
                    log("queue drained — exiting (--once)")
                    return
                time.sleep(args.poll)
                continue
            idle_streak = 0

            log(f"claimed {job['id']} ({job['type']})")
            api(f"/jobs/{job['id']}/status", {"status": "running"})
            runner = RUNNERS.get(job["type"])
            try:
                if runner is None:
                    raise RuntimeError(f"no runner for job type {job['type']}")
                runner(job)
                api(f"/jobs/{job['id']}/status", {"status": "done"})
                log(f"done {job['id']}")
            except SystemExit as e:  # byrdimage.die()
                api(f"/jobs/{job['id']}/status", {"status": "failed", "error": str(e.code)})
                log(f"FAILED {job['id']}: {e.code}")
            except Exception as e:
                api(f"/jobs/{job['id']}/status", {"status": "failed", "error": str(e)})
                log(f"FAILED {job['id']}: {e}")
        except KeyboardInterrupt:
            log("stopping")
            return
        except Exception as e:
            log(f"loop error ({e}) — retrying in 10s")
            time.sleep(10)


if __name__ == "__main__":
    main()
