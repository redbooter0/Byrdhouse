"""
ByrdHouse belt integration test — runs the ENTIRE pipeline with zero GPU:
mock ComfyUI + mock LM Studio, real router, real worker.

    python tests/integration_test.py

Asserts: job create -> claim -> generate -> archive+card -> auto-judge ->
needs_review -> approve; two-pass thumbnail compositing (if Pillow present);
content.package voice output; content.research CSV ranking; export.csv;
retry -> dead with real error message; auth rejection; stats/report.
Exit 0 = belt healthy.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CP, LP, RP = 18188, 11234, 18787   # test ports: comfy, lms, router
ROOT = Path(os.environ.get("BH_TEST_ROOT", "/tmp/byrdhouse-test-root"))
TOKEN = "test-token-123"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def api(path, payload=None, token=TOKEN, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{RP}{path}", data=data, method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def run_worker():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "worker.py"),
                    "--no-gpu", "--once", "--poll", "0.3"],
                   env={**os.environ, "BYRDHOUSE_ROOT": str(ROOT)},
                   timeout=120, check=True)


def main():
    # ── build an isolated root ────────────────────────────────────────────────
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    for d in ("recipes", "workflows", "scripts", "router", "dashboard"):
        shutil.copytree(REPO / d, ROOT / d)
    cfg = json.loads((REPO / "byrdhouse.config.json").read_text())
    cfg["services"].update(comfyui=f"http://127.0.0.1:{CP}",
                           lmstudio=f"http://127.0.0.1:{LP}/v1",
                           router=f"http://127.0.0.1:{RP}")
    cfg["gpu"].update(judge_model="mock-vl", operator_model="mock-vl")
    cfg["auth"]["admin_token"] = TOKEN
    (ROOT / "byrdhouse.config.json").write_text(json.dumps(cfg, indent=2))

    sys.path.insert(0, str(HERE))
    import mocks
    mocks.start(CP, LP)

    router = subprocess.Popen([sys.executable, str(ROOT / "router" / "router.py")],
                              env={**os.environ, "BYRDHOUSE_ROOT": str(ROOT)},
                              stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(40):
            try:
                api("/health"); break
            except Exception:
                time.sleep(0.25)
        else:
            sys.exit("router never came up")

        print("== auth")
        try:
            api("/jobs", {"type": "report.daily"}, token="wrong")
            check("bad token rejected", False)
        except urllib.error.HTTPError as e:
            check("bad token rejected", e.code == 401)

        print("== image.generate -> auto-judge -> approve")
        j = api("/jobs", {"type": "image.generate", "project": "careyrpg",
                          "required_mode": "IMAGE", "required_caps": ["comfyui"],
                          "payload": {"recipe": "rpg_tier_list",
                                      "slots": {"subject": "paladin", "game": "Last Epoch"},
                                      "project": "careyrpg", "purpose": "test", "batch": 2}})
        run_worker()
        job = api(f"/jobs?type=image.generate")[0]
        check("generate -> needs_review", job["status"] == "needs_review", job["status"])
        arts = [a for a in api("/artifacts?limit=50") if a["kind"] == "image"]
        check("2 artifacts registered", len(arts) == 2, str(len(arts)))
        check("judged score on artifacts", all(a["score"] == 4.2 for a in arts))
        pngs = list((ROOT / "artifacts" / "careyrpg").rglob("*.png"))
        cards = list((ROOT / "artifacts" / "careyrpg").rglob("*.png.json"))
        check("pngs + sidecar cards on disk", len(pngs) >= 2 and len(cards) >= 2)
        card = json.loads(cards[0].read_text())
        check("card has purpose/seed/checkpoint",
              all(k in card for k in ("purpose", "seed", "checkpoint", "recipe")))
        approved = api(f"/artifacts/{arts[0]['id']}/review", {"action": "approve"})
        check("approve flow", approved["status"] == "approved")
        api(f"/artifacts/{arts[1]['id']}/review", {"action": "reject"})

        # Idempotency: the same key submitted twice yields one job, not two
        k = "idem-test-key-1"
        j1 = api("/jobs", {"type": "report.daily", "idempotency_key": k})
        j2 = api("/jobs", {"type": "report.daily", "idempotency_key": k})
        check("idempotency key dedupes job submits",
              j1["id"] == j2["id"] and j2.get("idempotent") is True)
        same = [x for x in api("/jobs?limit=200") if x["id"] == j1["id"]]
        check("only one job exists for the key", len(same) == 1)

        # Learn loop: the belt projects its own approve/reject history into
        # an approval-rate ranking (reverse-engineered reinforcement signal)
        learn = api("/learn?by=recipe")
        rt = next((b for b in learn["buckets"] if b["value"] == "rpg_tier_list@2"), None)
        check("learn projection ranks by approval rate",
              rt and rt["approved"] == 1 and rt["rejected"] == 1 and rt["approval_rate"] == 0.5)
        pal = api("/learn?by=palette")
        check("learn projects vary-picks (palette) too",
              any(b["labeled"] >= 1 for b in pal["buckets"]))

        print("== content.thumbnail (two-pass, needs Pillow)")
        try:
            import PIL  # noqa: F401
            api("/jobs", {"type": "content.thumbnail", "required_mode": "IMAGE",
                          "required_caps": ["comfyui"],
                          "payload": {"recipe": "rpg_tier_list",
                                      "slots": {"subject": "necromancer", "game": "Last Epoch"},
                                      "project": "careyrpg", "purpose": "thumb test",
                                      "title": "BEST BUILDS TIER LIST", "batch": 1}})
            run_worker()
            thumbs = [a for a in api("/artifacts?limit=50") if a["kind"] == "thumbnail"]
            check("thumbnail artifact registered", len(thumbs) == 1, str(len(thumbs)))
            finals = list((ROOT / "artifacts").rglob("*_final.png"))
            check("composited final png exists", len(finals) == 1)
            from PIL import Image
            with Image.open(finals[0]) as im:
                check("final is 1280x720", im.size == (1280, 720), str(im.size))
            check("thumbnail judged", thumbs[0]["score"] == 4.2)
        except ImportError:
            print("  [SKIP] Pillow not installed here")

        print("== content.package (voice pack)")
        tr = ROOT / "inbox"; tr.mkdir(exist_ok=True)
        (tr / "t.txt").write_text("today we rank every build in last epoch season 3")
        api("/jobs", {"type": "content.package", "required_mode": "OPERATOR",
                      "required_caps": ["lmstudio"],
                      "payload": {"transcript_path": str(tr / "t.txt"), "project": "careyrpg"}})
        run_worker()
        pkg = [a for a in api("/artifacts?limit=50") if a["kind"] == "package"]
        check("package artifact", len(pkg) == 1)
        if pkg:
            data = json.loads(Path(json.loads(pkg[0]["meta"])["path"]).read_text())
            check("package has 5 titles", len(data.get("titles", [])) == 5)

        print("== content.research (outlier CSV)")
        (tr / "outliers.csv").write_text(
            "Title,Multiplier,VPH\nTier List,22,424.7\nMeh Video,1.1,3\nBuild Guide,9,120\n")
        api("/jobs", {"type": "content.research",
                      "payload": {"csv_path": str(tr / "outliers.csv"), "top": 2}})
        run_worker()
        ideas = [a for a in api("/artifacts?limit=50") if a["kind"] == "ideas"]
        check("ideas artifact", len(ideas) == 1)
        if ideas:
            md = Path(json.loads(ideas[0]["meta"])["path"]).read_text()
            check("tier list ranked #1", "1. **Tier List**" in md, md[:120])

        print("== export.csv")
        api("/jobs", {"type": "export.csv", "payload": {"what": "artifacts"}})
        run_worker()
        exp = [a for a in api("/artifacts?limit=50") if a["kind"] == "export"]
        check("export artifact (auto-approved)", len(exp) == 1 and exp[0]["status"] == "approved")

        print("== failure -> retry -> dead")
        api("/jobs", {"type": "image.generate", "required_mode": "IMAGE",
                      "payload": {"recipe": "nope", "slots": {}, "purpose": "fail"}})
        run_worker()
        dead = [x for x in api("/jobs?type=image.generate") if x["status"] == "dead"]
        check("dead after retries", len(dead) == 1)
        check("real error message recorded", dead and "no recipe 'nope'" in (dead[0]["error"] or ""))

        print("== requeue + cancel + worker liveness")
        rq = api(f"/jobs/{dead[0]['id']}/requeue", {})
        check("dead job requeued", rq["status"] == "queued" and rq["attempts"] == 0 and rq["error"] is None)
        cx = api(f"/jobs/{rq['id']}/cancel", {})
        check("queued job cancelled", cx["status"] == "cancelled")
        try:
            api(f"/jobs/{cx['id']}/cancel", {})
            check("cancel refuses non-queued job", False)
        except urllib.error.HTTPError as e:
            check("cancel refuses non-queued job", e.code == 400)
        st = api("/status")
        check("workers report computed liveness",
              st["workers"] and all(w.get("status") in ("online", "offline") for w in st["workers"]))

        # Cards carry job timing (queued/claimed/finished + duration) and the
        # founder's requested slots, so the dashboard can show both
        timed = [a for a in api("/artifacts?limit=50") if a["kind"] == "image"]
        check("artifacts expose job timing", timed and all(
            a["job_queued_at"] and a["job_claimed_at"] and a["job_finished_at"]
            and isinstance(a["gen_seconds"], int) and a["gen_seconds"] >= 0 for a in timed))
        card_meta = json.loads(timed[0]["meta"])
        check("card records requested slots", card_meta.get("slots", {}).get("game") == "Last Epoch")

        # Operator chat: router proxies to LM Studio with live belt context
        ch = api("/chat", {"messages": [{"role": "user", "content": "what is queued?"}]})
        check("chat replies through the operator model",
              bool(ch.get("reply")) and ch.get("model") == "mock-vl")
        try:
            api("/chat", {})
            check("chat rejects empty messages", False)
        except urllib.error.HTTPError as e:
            check("chat rejects empty messages", e.code == 400)

        # Recipe slots are deduped — game-anchored templates repeat {game}
        # in the prompt but the form needs exactly one input for it
        bg3 = [r for r in api("/recipes") if r["file"] == "build_guide.v3.json"][0]
        check("recipe slots deduped for the form",
              bg3["slots"].count("game") == 1 and len(bg3["slots"]) == len(set(bg3["slots"])))

        # Chat tools: the operator model can queue a generation from chat
        ch2 = api("/chat", {"messages": [{"role": "user",
                                          "content": "TOOLTEST make me palworld art"}]})
        check("chat tool loop executes and answers",
              bool(ch2.get("reply")) and ch2.get("actions")
              and ch2["actions"][0]["tool"] == "queue_image")
        chat_jobs = [j for j in api("/jobs?type=image.generate&status=queued")
                     if "chat request" in j["payload"]]
        check("chat-queued job is a real belt job", len(chat_jobs) >= 1)

        # image.refine: img2img over an existing artifact via /artifacts/<id>/refine
        src_art = [a for a in api("/artifacts?limit=50")
                   if a["kind"] == "image" and a["path"]][0]
        rj = api(f"/artifacts/{src_art['id']}/refine", {"strength": 0.5, "scale": 1.5})
        check("refine endpoint queues an image.refine job", rj["status"] == "queued")
        run_worker()
        refined = [a for a in api("/artifacts?limit=80")
                   if a["job_id"] == rj["id"] and a["kind"] == "image"]
        check("refined artifact registered with lineage", len(refined) >= 1 and
              json.loads(refined[0]["meta"]).get("refined_from") == src_art["path"])

        # content.enhance: operator model rewrites the prompt, then generation runs
        api("/jobs", {"type": "content.enhance", "project": "sandbox",
                      "required_mode": "OPERATOR", "required_caps": ["lmstudio"],
                      "payload": {"recipe": "freeform@1",
                                  "slots": {"prompt": "cool palworld thumbnail"},
                                  "project": "sandbox", "purpose": "enhance test"}})
        run_worker()  # enhance (OPERATOR) enqueues generate; --once drains both
        enhanced = [a for a in api("/artifacts?limit=100") if a["kind"] == "image"
                    and json.loads(a["meta"]).get("recipe", "").startswith("freeform")]
        check("enhanced prompt flowed into a freeform generation",
              enhanced and json.loads(enhanced[0]["meta"])["prompt"] != "")

        # aspect presets snap to SDXL-native dims; LoRA splices into the graph
        sys.path.insert(0, str(ROOT / "scripts"))
        import byrdimage
        check("aspect preset resolves SDXL dims", byrdimage.pick_dims("9:16") == (768, 1344))
        g = json.loads((ROOT / "workflows" / "sdxl_base_api.json").read_text())
        g.pop("_comment", None)
        byrdimage.insert_lora(g, "test_lora.safetensors", 0.8)
        lora_ok = (g["byrd_lora"]["class_type"] == "LoraLoader"
                   and g["3"]["inputs"]["model"] == ["byrd_lora", 0]
                   and g["6"]["inputs"]["clip"] == ["byrd_lora", 1])
        check("LoRA splices between checkpoint and consumers", lora_ok)

        # 'name@N' pins that recipe version; bare name resolves to the highest
        sys.path.insert(0, str(ROOT / "scripts"))
        import byrdimage
        import byrdjudge

        # Judging requires a vision model (a text model must not invent scores);
        # the mock's 'mock-vl' id is vision-capable, so it still judges.
        check("judge picks the loaded vision model over an absent configured one",
              byrdjudge._pick_judge_model(f"http://127.0.0.1:{LP}/v1", "ghost-model") == "mock-vl")
        check("vision detection: VL/vision ids yes, plain text no",
              byrdjudge._looks_vision("qwen3-vl-4b") and byrdjudge._looks_vision("llava-1.6")
              and not byrdjudge._looks_vision("llama-3.1-8b-instruct"))
        # Checkpoints fall back to what's installed, but the fallback is RECORDED
        ckpt_dir = ROOT / "Generators" / "ComfyUI" / "models" / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        (ckpt_dir / "onlyInstalled_v1.safetensors").write_bytes(b"stub")
        resolved, matched = byrdimage.resolve_checkpoint_info(ROOT, "does-not-exist")
        check("unmatched checkpoint falls back AND flags it",
              resolved == "onlyInstalled_v1.safetensors" and matched is False)
        _, matched2 = byrdimage.resolve_checkpoint_info(ROOT, "only installed")
        check("matched checkpoint resolves by loose name, no fallback flag", matched2 is True)
        check("recipe version pin honored",
              byrdimage.find_recipe(ROOT, "rpg_tier_list@1").name == "rpg_tier_list.v1.json")
        check("bare recipe name resolves to highest version",
              byrdimage.find_recipe(ROOT, "rpg_tier_list").name == "rpg_tier_list.v2.json")

        # ── Regression: the dashboard→recipe slot contract (yt_thumbnail v4) ──
        # job_19f525b23183s9na6 & siblings died twice with
        # "unfilled slots ['emotion']": the form let a required, non-vary slot
        # through empty. Lock every side of the contract with the EXACT recipe.
        yt = [r for r in api("/recipes") if r["file"] == "yt_thumbnail.v4.json"][0]
        yt_vary = set(yt["vary"])
        yt_required = [s for s in yt["slots"] if s not in yt_vary]
        # (1) /recipes exposes emotion as a required slot the form must render
        check("yt_thumbnail.v4 exposes emotion as a required (non-vary) slot",
              "emotion" in yt_required and "emotion" not in yt_vary)
        # (2) byrdimage rejects a generate that is missing a required slot —
        #     the exact failure the three dead jobs hit
        try:
            byrdimage.generate(ROOT, "yt_thumbnail@4",
                               {"game": "Palworld", "subject": "a Pal trainer"},
                               "careyrpg", "regression: missing emotion", dry_run=True)
            check("byrdimage rejects a generate missing the emotion slot", False)
        except SystemExit as e:
            check("byrdimage rejects a generate missing the emotion slot",
                  "emotion" in str(e), str(e))
        # (3) a vary slot must ALWAYS be filled by byrdimage: emotion supplied,
        #     every vary slot (palette/lighting/composition) omitted -> no raise
        try:
            byrdimage.generate(ROOT, "yt_thumbnail@4",
                               {"game": "Palworld", "subject": "a Pal trainer",
                                "emotion": "wide-eyed shock"},
                               "careyrpg", "regression: vary auto-fill", dry_run=True)
            check("byrdimage fills vary slots so a complete recipe submits", True)
        except SystemExit as e:
            check("byrdimage fills vary slots so a complete recipe submits",
                  False, str(e))

        # content.thumbnail with image_path composites onto a provided image
        # (no ComfyUI pass) and yields a 1280x720 final with a card
        from PIL import Image
        shot = ROOT / "inbox" / "myshot.png"
        shot.parent.mkdir(exist_ok=True)
        Image.new("RGB", (640, 360), (40, 90, 40)).save(shot)
        api("/jobs", {"type": "content.thumbnail", "project": "careyrpg",
                      "required_mode": "ANY",
                      "payload": {"title": "MY OWN SHOT", "image_path": str(shot),
                                  "project": "careyrpg", "purpose": "byo image"}})
        run_worker()
        byo = [a for a in api("/artifacts?limit=80")
               if a["kind"] == "thumbnail" and "myshot" in (a["path"] or "")]
        check("thumbnail composited from provided image", len(byo) == 1)
        if byo:
            check("provided-image final is 1280x720",
                  Image.open(byo[0]["path"]).size == (1280, 720))

        # ── Uploaded source image: saved on the router, recorded at top grade,
        #    then composited onto by the worker (which fetches it back). This is
        #    the endpoint the operator model will call once its tools unlock. ──
        import io
        buf = io.BytesIO()
        Image.new("RGB", (800, 450), (120, 40, 160)).save(buf, "PNG")
        src_bytes = buf.getvalue()
        rqs = urllib.request.Request(
            f"http://127.0.0.1:{RP}/sources/palworld_base.png?project=careyrpg",
            data=src_bytes, method="POST",
            headers={"Content-Type": "image/png", "Authorization": f"Bearer {TOKEN}"})
        src_resp = json.loads(urllib.request.urlopen(rqs, timeout=15).read().decode())
        src_id = src_resp.get("id")
        check("source upload returns a recorded artifact id", bool(src_id), str(src_resp))
        src_art = [a for a in api("/artifacts?limit=100") if a["id"] == src_id]
        check("uploaded source is recorded, approved, top grade",
              len(src_art) == 1 and src_art[0]["kind"] == "source"
              and src_art[0]["status"] == "approved" and src_art[0]["score"] == 5.0,
              str(src_art))
        with urllib.request.urlopen(
                f"http://127.0.0.1:{RP}/artifacts/{src_id}/file", timeout=15) as r:
            check("uploaded source served from the router host", r.read() == src_bytes)
        # compose a title onto the uploaded source by artifact id (no local path)
        api("/jobs", {"type": "content.thumbnail", "project": "careyrpg",
                      "required_mode": "ANY",
                      "payload": {"title": "SOURCE UPLOAD WORKS",
                                  "source_artifact": src_id,
                                  "project": "careyrpg", "purpose": "uploaded source compose"}})
        run_worker()
        composed = [a for a in api("/artifacts?limit=100")
                    if a["kind"] == "thumbnail"
                    and json.loads(a["meta"] or "{}").get("source_artifact") == src_id]
        check("worker fetched the uploaded source and composited onto it",
              len(composed) == 1)
        if composed:
            check("uploaded-source final is 1280x720",
                  Image.open(composed[0]["path"]).size == (1280, 720))

        # A retried job re-registers its artifacts — must upsert, not duplicate
        dupe_card = {"artifact_id": "art.dupetest.0", "job_id": "job_dupetest",
                     "kind": "image", "path": "/tmp/dupetest.png", "status": "draft"}
        api("/jobs/job_dupetest/artifacts", {"artifacts": [dupe_card]})
        api("/jobs/job_dupetest/artifacts", {"artifacts": [dict(dupe_card, status="needs_review")]})
        rows = [a for a in api("/artifacts?limit=100") if a["job_id"] == "job_dupetest"]
        check("re-registered artifact upserts (one card, latest state)",
              len(rows) == 1 and rows[0]["status"] == "needs_review")

        # Artifact files live on the worker's disk; the dashboard preview must
        # come from the bytes the worker uploaded to the router
        png = b"\x89PNG-preview-test"
        rq2 = urllib.request.Request(
            f"http://127.0.0.1:{RP}/artifacts/art.dupetest.0/file", data=png, method="POST",
            headers={"Content-Type": "image/png", "Authorization": f"Bearer {TOKEN}"})
        urllib.request.urlopen(rq2, timeout=15).read()
        with urllib.request.urlopen(f"http://127.0.0.1:{RP}/artifacts/art.dupetest.0/file", timeout=15) as r:
            check("preview served from uploaded cache (file not on router host)", r.read() == png)

        # Reference library: upload from the dashboard, list, serve to the judge
        ref_png = b"\x89PNG-ref-bytes"
        rq3 = urllib.request.Request(
            f"http://127.0.0.1:{RP}/references/palworld/fave.png", data=ref_png, method="POST",
            headers={"Content-Type": "image/png", "Authorization": f"Bearer {TOKEN}"})
        urllib.request.urlopen(rq3, timeout=15).read()
        refs = api("/references?tag=palworld")
        check("reference listed under its tag",
              len(refs) == 1 and refs[0]["name"] == "fave.png")
        with urllib.request.urlopen(
                f"http://127.0.0.1:{RP}/references/palworld/fave.png/file", timeout=15) as r:
            check("reference file served", r.read() == ref_png)

        # PowerShell 5.1 writes status.json with a UTF-8 BOM — /status must tolerate it
        (ROOT / "status.json").write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"host": "TEST", "overall": "green", "checks": []}).encode())
        st = api("/status")
        check("/status reads BOM'd status.json", st["machine"].get("host") == "TEST")

        print("== stats + report + dashboard")
        st = api("/stats")
        check("stats counts artifacts", st["artifacts_total"] >= 4, str(st))
        rep = api("/reports/daily")
        check("daily report markdown", rep["markdown"].startswith("# ByrdHouse daily report"))
        with urllib.request.urlopen(f"http://127.0.0.1:{RP}/", timeout=10) as r:
            check("dashboard serves", r.status == 200 and b"Command Center" in r.read())

    finally:
        router.terminate()

    print(f"\n{'ALL CHECKS PASSED' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    import urllib.error  # noqa: F401  (used in auth check)
    main()
