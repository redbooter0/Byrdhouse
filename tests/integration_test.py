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

        # Interchangeable models: judge falls back to whatever LM Studio has
        # loaded; checkpoints fall back to whatever is actually installed
        check("judge uses the loaded model when the configured one is absent",
              byrdjudge._pick_model(f"http://127.0.0.1:{LP}/v1", "ghost-model") == "mock-vl")
        ckpt_dir = ROOT / "Generators" / "ComfyUI" / "models" / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        (ckpt_dir / "onlyInstalled_v1.safetensors").write_bytes(b"stub")
        check("unmatched checkpoint request falls back to an installed one",
              byrdimage.resolve_checkpoint(ROOT, "does-not-exist")
              == "onlyInstalled_v1.safetensors")
        check("matched checkpoint still resolves by loose name",
              byrdimage.resolve_checkpoint(ROOT, "only installed")
              == "onlyInstalled_v1.safetensors")
        check("recipe version pin honored",
              byrdimage.find_recipe(ROOT, "rpg_tier_list@1").name == "rpg_tier_list.v1.json")
        check("bare recipe name resolves to highest version",
              byrdimage.find_recipe(ROOT, "rpg_tier_list").name == "rpg_tier_list.v2.json")

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
