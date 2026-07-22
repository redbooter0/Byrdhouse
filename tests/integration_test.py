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
    for d in ("recipes", "workflows", "scripts", "router", "dashboard", "profiles", "configs", "docs"):
        shutil.copytree(REPO / d, ROOT / d)
    # Give the root a minimal .git so router/worker build_sha resolves exactly as
    # it does on the machines (both run from a git checkout). Only HEAD + refs are
    # needed — repo_build() never touches objects/.
    gsrc, gdst = REPO / ".git", ROOT / ".git"
    if gsrc.is_dir():
        gdst.mkdir(exist_ok=True)
        if (gsrc / "HEAD").exists():
            shutil.copy(gsrc / "HEAD", gdst / "HEAD")
        if (gsrc / "refs").exists():
            shutil.copytree(gsrc / "refs", gdst / "refs", dirs_exist_ok=True)
        if (gsrc / "packed-refs").exists():
            shutil.copy(gsrc / "packed-refs", gdst / "packed-refs")
    # The checked-in config is UTF-8 with a BOM.  Specify the codec so the
    # belt test is deterministic on Windows consoles whose default codec is
    # cp1252, as well as on Linux CI.
    cfg = json.loads((REPO / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
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

        # Permanent CPU semantic face-zone identity route: keep the recipe,
        # neck-up-minus-hair mask, mesh-seeded cleanup graph, worker dispatch,
        # reference map, and production LoRA contract locked together.  These
        # are structural checks so the zero-GPU belt test catches a renamed or
        # missing route before a gaming-PC job reaches ComfyUI.
        face_recipe_path = ROOT / "recipes" / "anime_face_zone_edit.v1.json"
        check("CPU face-zone recipe exists", face_recipe_path.is_file(),
              str(face_recipe_path))
        face_recipe = (json.loads(face_recipe_path.read_text(encoding="utf-8-sig"))
                       if face_recipe_path.is_file() else {})
        check("CPU face-zone recipe uses the permanent runner",
              face_recipe.get("runner") == "face_zone_identity_edit",
              str(face_recipe.get("runner")))

        face_workflow_rel = face_recipe.get("workflow", "")
        check("CPU face-zone recipe selects the mesh-seed cleanup graph",
              face_workflow_rel == "workflows/sd15_face_mesh_seed_refine_api.json",
              str(face_workflow_rel))
        face_workflow_path = ROOT / face_workflow_rel if face_workflow_rel else None
        check("CPU face-zone workflow exists",
              bool(face_workflow_path and face_workflow_path.is_file()),
              str(face_workflow_path))
        face_graph = (json.loads(face_workflow_path.read_text(encoding="utf-8-sig"))
                      if face_workflow_path and face_workflow_path.is_file() else {})
        face_node_types = {node.get("class_type") for node in face_graph.values()
                           if isinstance(node, dict)}
        check("CPU face-zone workflow refines the retained mesh seed",
              {"VAEEncode", "SetLatentNoiseMask"} <= face_node_types,
              str(sorted(node for node in face_node_types if node)))

        identity_references = face_recipe.get("identity_references") or {}
        expected_identity_references = {
            "gojo": "profiles/me/references/generated_anime_cartoon/002_naruto.png",
            "vegeta": "profiles/me/references/generated_anime_cartoon/013_yu-yu-hakusho.png",
            "luffy_close": "profiles/me/references/generated_anime_cartoon/003_one-piece.png",
            "luffy_full": "profiles/me/references/generated_anime_cartoon/003_one-piece.png",
        }
        check("face-zone presets pin reviewed identity references",
              identity_references == expected_identity_references,
              str(identity_references))

        facezone_source = (ROOT / "scripts" / "byrdfacezone.py").read_text(
            encoding="utf-8-sig")
        byrdimage_source = (ROOT / "scripts" / "byrdimage.py").read_text(
            encoding="utf-8-sig")
        worker_source = (ROOT / "scripts" / "worker.py").read_text(
            encoding="utf-8-sig")
        check("CPU face-zone script exposes prepare and composite functions",
              "def prepare_face_zone(" in facezone_source
              and "def composite_generated(" in facezone_source)
        check("CPU face-zone script locks the closed-head-minus-hair rule",
              '"zone_kind": "closed-head-envelope-minus-independent-hair-outline-plus-neck"' in facezone_source
              and '"hair_headwear_exclusion"' in facezone_source
              and '"neck_anchor"' in facezone_source
              and '"semantic_labels"' in facezone_source)
        check("CPU face-zone script locks the commercial semantic model",
              'SELFIE_SEGMENTER_SHA256 = "c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0"'
              in facezone_source
              and '"license": "Apache-2.0"' in facezone_source)
        check("anime semantic fallback stays private pending license review",
              'PARSENET_SHA256 = "3d558d8d0e42c20224f13cf5a29c79eba2d59913419f945545d8cf7b72920de2"'
              in facezone_source
              and '"license": "deployment-license-review-required"' in facezone_source
              and '"deployment_scope": "private-local-evaluation-only"' in facezone_source)
        check("CPU identity seed uses the 478-point triangle warp plus tone transfer",
              "def _build_identity_mesh_seed(" in facezone_source
              and '"method": "cpu-mediapipe-478-triangle-warp-plus-semantic-tone-transfer"' in facezone_source
              and '"identity_mesh_seed"' in facezone_source)
        check("byrdimage exposes the face-zone adapter",
              "def edit_face_zone(" in byrdimage_source
              and 'recipe.get("runner") != "face_zone_identity_edit"' in byrdimage_source
              and 'zone_script = root / "scripts" / "byrdfacezone.py"' in byrdimage_source)
        check("face-zone composite restores protected target material after GPU cleanup",
              "restore_protected_material(" in facezone_source)
        check("face-zone composite pastes the GPU result into the final image",
              "original.paste(generated, (left, top), soft)" in facezone_source)
        check("identity-eye mode releases target feature locks",
              'eye_source_mode == "target" and eye_protection_strength > 0.0' in facezone_source)
        from PIL import Image
        check("whole-head seed restores target hair and accessories after identity fill",
              "identity_seed = restore_protected_material(identity_seed, crop, hair_exclusion)" in facezone_source
              and '"target_theme_overlay"' in facezone_source
              and '"mask_artifact": "hair_headwear_exclusion"' in facezone_source)


        check("CPU upload analyzer walks neck-to-head before generation",
              "def _ordered_body_part_traversal(" in facezone_source
              and '"neck-left"' in facezone_source
              and '"top-of-head"' in facezone_source
              and '"neck-anchor-close"' in facezone_source
              and "def _build_upload_analysis(" in facezone_source)
        check("CPU foundation separates face-core from whole-zone coverage",
              '"core_coverage_ratio"' in facezone_source
              and '"facial_core_coverage"' in facezone_source
              and "core_coverage_ratio < 0.55" in facezone_source)
        check("adapter blocks GPU until every upload-analysis stage passes",
              "CPU upload analysis did not pass every ordered body-part stage" in byrdimage_source
              and "expected_upload_stages" in byrdimage_source
              and '"upload_analysis": upload_analysis' in byrdimage_source)
        sys.path.insert(0, str(ROOT / "scripts"))
        from facezone_composite import restore_protected_material
        target_material = Image.new("RGB", (10, 10), (12, 34, 56))
        generated_material = Image.new("RGB", (10, 10), (220, 30, 30))
        protected_material = Image.new("L", (10, 10), 0)
        for x in range(4, 6):
            for y in range(4, 6):
                target_material.putpixel((x, y), (25, 205, 95))
                protected_material.putpixel((x, y), 255)
        restored_material = restore_protected_material(
            generated_material, target_material, protected_material
        )
        check("protected target pixels survive final face-zone composite",
              restored_material.getpixel((4, 4)) == (25, 205, 95)
              and restored_material.getpixel((5, 5)) == (25, 205, 95)
              and restored_material.getpixel((0, 0)) == (220, 30, 30))
        check("worker dispatches face-zone jobs to byrdimage",
              'recipe_data.get("runner") == "face_zone_identity_edit"' in worker_source
              and "byrdimage.edit_face_zone(" in worker_source)

        production_identity = face_recipe.get("identity") or {}
        check("face-zone production LoRA is explicit",
              production_identity.get("lora") == "carey_meina_sd15_v1.safetensors"
              and isinstance(production_identity.get("strength"), (int, float))
              and isinstance(production_identity.get("clip_strength"), (int, float)),
              str(production_identity))
        # ── The examiner (founder contract): before ANY edit the system must
        #    understand where it can and can't operate on THIS image ──
        check("examiner gates the quality lane before any zone/GPU work",
              "def _face_report(" in byrdimage_source
              and "face_report = _face_report(" in byrdimage_source
              and "face report: cannot operate" in byrdimage_source
              and '"face_report": face_report' in byrdimage_source)
        check("examiner reports every face with verdicts, risk flags and a feature plan",
              "def analyze_image(" in facezone_source
              and "FEATURE_PLAN_DEFAULT" in facezone_source
              and "extreme_expression" in facezone_source
              and "strong_profile" in facezone_source
              and '"feature_plan"' in facezone_source
              and "def render_report_overview(" in facezone_source)
        check("examine route archives the report without editing (any GPU mode)",
              "def facezone_examine(" in byrdimage_source
              and '"examine"' in worker_source
              and "byrdimage.facezone_examine(" in worker_source
              and '"face-report"' in byrdimage_source)
        check("thorough scrutiny is the founder default with a recommended lane",
              "def _thorough_face_checks(" in facezone_source
              and "geometry_stability" in facezone_source
              and "def _recommend_lane(" in facezone_source
              and "analysis_seconds" in facezone_source
              and "thorough=not engine.get(\"quick_report\", False)" in byrdimage_source)
        check("flow: canvas follows the measured face, candidates batch one submit",
              "--canvas-size" in facezone_source
              and "CANVAS_SIZE = int(args.canvas_size)" in facezone_source
              and '"--canvas-size", str(canvas)' in byrdimage_source
              and '"RepeatLatentBatch"' in byrdimage_source
              and "saved.append((final, card))" in byrdimage_source)
        v3_graph = json.loads((ROOT / "workflows" / "sd15_face_zone_controlnet_api.json")
                              .read_text(encoding="utf-8-sig"))
        check("v3 graph batches candidates inside the masked latent chain",
              v3_graph.get("15", {}).get("class_type") == "RepeatLatentBatch"
              and v3_graph["15"]["inputs"]["samples"] == ["8", 0]
              and v3_graph["9"]["inputs"]["latent_image"] == ["15", 0])
        check("avenues ride as parameters: workflow override + identity photo anchor",
              'engine.get("workflow") or recipe.get(' in byrdimage_source.replace("(engine or {})", "engine")
              or '(engine or {}).get("workflow") or recipe.get(' in byrdimage_source)
        check("avenue graphs are valid and keep the adapter contract",
              all(json.loads((ROOT / "workflows" / name).read_text(encoding="utf-8-sig"))
                  .get("1", {}).get("_meta", {}).get("title") == "IDENTITY MESH SEED"
                  for name in ("sd15_face_zone_diffdiff_api.json",
                               "sd15_face_zone_ipadapter_api.json"))
              and json.loads((ROOT / "workflows" / "sd15_face_zone_diffdiff_api.json")
                             .read_text(encoding="utf-8-sig"))["16"]["class_type"] == "DifferentialDiffusion"
              and json.loads((ROOT / "workflows" / "sd15_face_zone_ipadapter_api.json")
                             .read_text(encoding="utf-8-sig"))["21"]["class_type"] == "IPAdapterUnifiedLoader"
              and '"IDENTITY PHOTO"' in byrdimage_source)
        check("quality lane is drivable by hand (facelab.ps1 + --edit-face-zone CLI)",
              "--edit-face-zone" in byrdimage_source
              and (ROOT / "scripts" / "facelab.ps1").is_file()
              and "quality" in (ROOT / "scripts" / "facelab.ps1").read_text(encoding="utf-8-sig"))
        check("face-zone adapter refuses an unconditioned production run",
              "no deployed identity LoRA exists" in byrdimage_source
              and "select_identity_lora(root, identity, identity_lora)" in byrdimage_source
              and 'lora_id="byrd_identity_lora"' in byrdimage_source)

        # aspect presets snap to SDXL-native dims; LoRA splices into the graph
        v2_recipe_path = ROOT / "recipes" / "anime_face_zone_edit.v2.json"
        check("plug-and-play face-swap v2 recipe exists", v2_recipe_path.is_file(), str(v2_recipe_path))
        v2_recipe = (json.loads(v2_recipe_path.read_text(encoding="utf-8-sig"))
                     if v2_recipe_path.is_file() else {})
        v2_passes = (v2_recipe.get("defaults") or {}).get("gpu_passes") or {}
        check("v2 recipe pins the local two-pass mesh route",
              v2_recipe.get("runner") == "face_zone_identity_edit"
              and v2_recipe.get("workflow") == "workflows/sd15_face_mesh_seed_multipass_api.json"
              and v2_recipe.get("identity_references", {}).get("auto")
              and v2_recipe.get("defaults", {}).get("min_mesh_coverage") == 0.55
              and list(v2_passes) == ["identity_fill", "line_harmonize"], str(v2_passes))

        v2_presets = v2_recipe.get("target_presets") or {}
        check("hard-test presets encode accessory truth before masking",
              v2_presets.get("vegeta", {}).get("absent_accessories")
              == ["eyeglasses", "headwear", "earrings", "necklaces"]
              and "headwear" not in v2_presets.get("luffy_close", {}).get("absent_accessories", [])
              and "headwear" in v2_presets.get("luffy_close", {}).get(
                  "expected_preserved_materials", []),
              str(v2_presets))
        check("preset contradictions are corrected only inside detected face geometry",
              'contradictory = (category == label) & seed' in facezone_source
              and 'hair_headwear &= ~contradictory' in facezone_source
              and '"residual_absent_accessory_pixels_in_geometric_face"' in facezone_source
              and 'zone_cmd += ["--absent-accessory", str(accessory)]' in byrdimage_source)
        check("adapter records crop preflight and refuses expandable heads before GPU",
              'crop_preflight = dict(zone.get("crop_preflight") or {})' in byrdimage_source
              and 'crop_preflight.get("passed") is False' in byrdimage_source
              and 'CPU crop preflight did not contain the full head/neck before GPU work' in byrdimage_source
              and '"crop_preflight": crop_preflight' in byrdimage_source)
        # 2026-07-16: defaults promoted to the founder-VERIFIED golden runs —
        # GPU finish ON by default (the d28 Gojo was a GPU-finished crop; the
        # raw CPU-only ship is what produced the broken Vegeta). The CPU-only
        # finish remains available as an engine capability, never the default.
        check("face-zone v2 defaults run the verified GPU finish (CPU-only stays available)",
              '"skip_gpu_cleanup": false' in v2_recipe_path.read_text(encoding="utf-8-sig")
              and 'skip_gpu_cleanup = bool(' in byrdimage_source
              and 'CPU identity mesh seed used without GPU cleanup' in byrdimage_source
              and 'cpu_face_zone_sd15_seed_only' in byrdimage_source)
        v2_graph_path = ROOT / v2_recipe.get("workflow", "")
        v2_graph = (json.loads(v2_graph_path.read_text(encoding="utf-8-sig"))
                    if v2_graph_path.is_file() else {})
        v2_samplers = [node for node in v2_graph.values() if isinstance(node, dict) and node.get("class_type") == "KSampler"]
        v2_pass_ids = {node.get("_meta", {}).get("byrd_pass") for node in v2_samplers}
        v2_node_types = [node.get("class_type") for node in v2_graph.values() if isinstance(node, dict)]
        check("v2 graph keeps the GPU route in one masked latent chain",
              len(v2_samplers) == 2 and v2_pass_ids == {"identity_fill", "line_harmonize"}
              and v2_graph.get("12", {}).get("inputs", {}).get("samples") == ["9", 0]
              and v2_graph.get("13", {}).get("inputs", {}).get("latent_image") == ["12", 0]
              and v2_node_types.count("VAEEncode") == 1
              and v2_node_types.count("VAEDecode") == 1
              and v2_node_types.count("SaveImage") == 1
              and any(isinstance(node, dict) and node.get("_meta", {}).get("title") == "EDGE HARMONIZE MASK" for node in v2_graph.values()),
              str(v2_pass_ids))
        check("adapter fails closed for invalid face-swap inputs",
              'identity_references.get(preset_key) or identity_references.get("auto")' in byrdimage_source
              and "unknown face-zone target preset" in byrdimage_source
              and "refusing generic inpaint fallback" in byrdimage_source
              and "min_mesh_coverage must be a number between 0 and 1" in byrdimage_source
              and "immutable_upload_root" in byrdimage_source)

        sys.path.insert(0, str(ROOT / "scripts"))
        import byrdimage
        check("aspect preset resolves SDXL dims", byrdimage.pick_dims("9:16") == (768, 1344))
        v2_plan = byrdimage._resolve_face_zone_gpu_passes({}, v2_recipe["defaults"], 7132)
        check("v2 adapter resolves the two local GPU passes deterministically",
              list(v2_plan) == ["identity_fill", "line_harmonize"]
              and [entry["seed"] for entry in v2_plan.values()] == [7132, 7133]
              and [entry["steps"] for entry in v2_plan.values()] == [16, 8]
              and [entry["denoise"] for entry in v2_plan.values()] == [0.28, 0.12], str(v2_plan))
        try:
            byrdimage._resolve_face_zone_gpu_passes(
                {"gpu_passes": {"identity_fill": {"denoise": 0}}}, v2_recipe["defaults"], 7132
            )
        except SystemExit as exc:
            invalid_pass_rejected = "denoise" in str(exc)
        else:
            invalid_pass_rejected = False
        check("v2 adapter rejects an unsafe GPU-pass override", invalid_pass_rejected)

        uploaded_target = ROOT / "artifacts" / "_sources" / "dashboard-upload.png"
        uploaded_target.parent.mkdir(parents=True, exist_ok=True)
        uploaded_target.write_bytes(b"immutable upload")
        try:
            byrdimage._require_original_target(ROOT, uploaded_target)
        except SystemExit:
            upload_cache_allowed = False
        else:
            upload_cache_allowed = True
        generated_target = ROOT / "artifacts" / "image_lab" / "generated.png"
        generated_target.parent.mkdir(parents=True, exist_ok=True)
        generated_target.write_bytes(b"generated output")
        try:
            byrdimage._require_original_target(ROOT, generated_target)
        except SystemExit:
            generated_target_rejected = True
        else:
            generated_target_rejected = False
        check("adapter accepts immutable dashboard uploads but rejects generated retries",
              upload_cache_allowed and generated_target_rejected)
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

        # ── Belt-as-MCP: the bot's audited hands on the belt (byrd_belt_mcp) ──
        # Same 2-machine setup, one shared tool surface: any MCP client drives
        # the belt through the router, never ComfyUI/GPU directly.
        os.environ["BYRDHOUSE_ROOT"] = str(ROOT)
        import byrd_belt_mcp as belt
        init = belt.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        check("belt-MCP initialize returns a protocol version",
              init["result"]["protocolVersion"] == belt.PROTOCOL_VERSION)
        tools = {t["name"] for t in belt.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
        check("belt-MCP exposes the belt tools",
              {"belt_status", "list_artifacts", "queue_image", "compose_thumbnail",
               "review_artifact"} <= tools)
        st = belt.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "belt_status", "arguments": {}}})
        check("belt-MCP belt_status proxies to the router",
              st["result"]["isError"] is False
              and "queue" in st["result"]["content"][0]["text"])
        before = len(api("/jobs?limit=200"))
        qr = belt.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "queue_image",
                                     "arguments": {"prompt": "a bot-queued test image"}}})
        check("belt-MCP queue_image creates a real audited job",
              qr["result"]["isError"] is False
              and len(api("/jobs?limit=200")) == before + 1)
        # autonomy ladder is literally a permission filter — no separate build
        belt.READONLY = True
        ro = {t["name"] for t in belt.handle(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/list"})["result"]["tools"]}
        blocked = belt.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                               "params": {"name": "queue_image", "arguments": {"prompt": "x"}}})
        check("read-only mode hides + blocks write tools (autonomy = a permission)",
              "queue_image" not in ro and "belt_status" in ro
              and blocked["result"]["isError"] is True)
        belt.READONLY = False

        # web_search: the in-app chat's research tool — config-driven, graceful
        sys.path.insert(0, str(ROOT / "router"))
        import router as router_mod
        ws = router_mod.run_chat_tool("web_search", {"query": "viral palworld thumbnail"}, "test")
        check("web_search reports clearly when unconfigured",
              isinstance(ws, dict) and "not configured" in ws.get("error", ""))

        # ── IP-Adapter: reference-driven generation (the 'make it look like THIS
        #    game' engine). Reuse the uploaded source (src_id) as the reference. ──
        api("/jobs", {"type": "image.generate", "project": "careyrpg",
                      "required_mode": "IMAGE", "required_caps": ["comfyui"],
                      "payload": {"recipe": "game_ref", "reference_artifact": src_id,
                                  "slots": {"subject": "a Pal trainer", "emotion": "shocked"},
                                  "project": "careyrpg", "purpose": "ref-driven test", "batch": 2}})
        run_worker()
        refgen = [a for a in api("/artifacts?limit=120")
                  if a["kind"] == "image"
                  and json.loads(a["meta"] or "{}").get("reference")]
        check("reference-driven generation archived images with reference lineage",
              len(refgen) >= 2, str(len(refgen)))
        if refgen:
            check("reference generation ran through the IP-Adapter workflow",
                  "ipadapter" in json.loads(refgen[0]["meta"]).get("workflow", ""))

        # ── image.faceswap: ReActor face swap through the belt (Face Lab).
        #    The face auto-resolves from profiles/me/references exactly like the
        #    me-recipes; the target is an uploaded artifact fetched back. ──
        print("== image.faceswap (direct swap + anime style blend)")
        face_dir = ROOT / "profiles" / "me" / "references"
        face_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (256, 256), (200, 170, 150)).save(face_dir / "front.jpg")
        api("/jobs", {"type": "image.faceswap", "project": "careyrpg",
                      "required_mode": "IMAGE", "required_caps": ["comfyui"],
                      "payload": {"target_artifact": src_id, "subject_profile": "me",
                                  "style_blend": 0, "project": "careyrpg",
                                  "purpose": "direct swap test"}})
        run_worker()
        swaps = [a for a in api("/artifacts?limit=200") if a["kind"] == "image"
                 and json.loads(a["meta"] or "{}").get("recipe") == "faceswap@1"]
        check("faceswap artifact archived with a card", len(swaps) == 1, str(len(swaps)))
        if swaps:
            meta = json.loads(swaps[0]["meta"])
            face_source = str(meta.get("face_source", ""))
            check("swap card records face source + target + reactor workflow",
                  face_source
                  and "profiles" in face_source
                  and "references" in face_source
                  and meta.get("swap_target")
                  and "reactor_faceswap_api" in meta.get("workflow", ""), str(meta))
            check("direct swap card is honest: no seed, no checkpoint",
                  meta.get("seed") is None and "checkpoint" not in meta)
            check("faceswap auto-judged like any artifact", swaps[0]["score"] == 4.2)
        # blend pass: anime targets (Gojo/Vegeta/Luffy) melt the swap into the
        # art style with a low-denoise img2img pass driven by a character prompt
        api("/jobs", {"type": "image.faceswap", "project": "careyrpg",
                      "required_mode": "IMAGE", "required_caps": ["comfyui"],
                      "payload": {"target_artifact": src_id, "style_blend": 0.35,
                                  "prompt": "Gojo Satoru, white hair, black blindfold",
                                  "project": "careyrpg", "purpose": "blend swap test"}})
        run_worker()
        blends = [a for a in api("/artifacts?limit=200") if a["kind"] == "image"
                  and json.loads(a["meta"] or "{}").get("style_blend") == 0.35]
        check("blend swap ran the two-pass workflow", len(blends) == 1, str(len(blends)))
        if blends:
            bm = json.loads(blends[0]["meta"])
            check("blend card carries prompt/seed/checkpoint for the img2img pass",
                  "Gojo" in bm.get("prompt", "") and bm.get("seed") is not None
                  and bm.get("checkpoint")
                  and "blend" in bm.get("workflow", ""), str(bm))
        # graph surgery is validated up front: a swapped/missing node pair must
        # die loudly, never quietly swap the wrong direction
        try:
            byrdimage.faceswap(ROOT, str(ROOT / "workflows" / "nope.png"),
                               str(face_dir / "front.jpg"), "careyrpg", "x")
            check("faceswap rejects a missing target loudly", False)
        except SystemExit as e:
            check("faceswap rejects a missing target loudly", "not found" in str(e))

        # zone route (the founder lane): a mask means the GPU edits ONLY inside
        # the approved zone — VAEEncodeForInpaint graph, identity from LoRA+prompt
        mbuf = io.BytesIO()
        Image.new("RGB", (800, 450), (255, 255, 255)).save(mbuf, "PNG")
        rqm = urllib.request.Request(
            f"http://127.0.0.1:{RP}/sources/facezone_mask.png?project=careyrpg",
            data=mbuf.getvalue(), method="POST",
            headers={"Content-Type": "image/png", "Authorization": f"Bearer {TOKEN}"})
        mask_id = json.loads(urllib.request.urlopen(rqm, timeout=15).read().decode())["id"]
        api("/jobs", {"type": "image.faceswap", "project": "careyrpg",
                      "required_mode": "IMAGE", "required_caps": ["comfyui"],
                      "payload": {"target_artifact": src_id, "mask_artifact": mask_id,
                                  "prompt": "the same man as Gojo, cel shading",
                                  "project": "careyrpg", "purpose": "zone edit test"}})
        run_worker()
        zones = [a for a in api("/artifacts?limit=250") if a["kind"] == "image"
                 and json.loads(a["meta"] or "{}").get("recipe") == "facezone@1"]
        check("zone edit archived through the inpaint workflow", len(zones) == 1,
              str(len(zones)))
        if zones:
            zm = json.loads(zones[0]["meta"])
            check("zone card records mask + corridor denoise + checkpoint",
                  zm.get("mask_source") and zm.get("denoise") == 0.7
                  and "inpaint" in zm.get("workflow", "")
                  and zm.get("checkpoint"), str(zm))

        # AUTO route (the daily driver): detector finds the face, masks it,
        # redraws it as the founder — no hand mask, no face photo in payload
        api("/jobs", {"type": "image.faceswap", "project": "careyrpg",
                      "required_mode": "IMAGE", "required_caps": ["comfyui"],
                      "payload": {"target_artifact": src_id, "route": "auto",
                                  "prompt": "the same man as Vegeta, cel shading",
                                  "project": "careyrpg", "purpose": "auto route test"}})
        run_worker()
        autos = [a for a in api("/artifacts?limit=250") if a["kind"] == "image"
                 and json.loads(a["meta"] or "{}").get("recipe") == "facezone_auto@1"]
        check("auto route archived through the FaceDetailer workflow", len(autos) == 1,
              str(len(autos)))
        if autos:
            am = json.loads(autos[0]["meta"])
            check("auto card records detector + corridor denoise + prompt",
                  am.get("detector", "").startswith("bbox/")
                  and am.get("denoise") == 0.7
                  and "facezone_auto" in am.get("workflow", "")
                  and "Vegeta" in am.get("prompt", ""), str(am))

        # PREVIEW route (the CPU pre-step): detection only, archives the zone
        # overlay + the soft mask for approval — the GPU never decides the mask
        api("/jobs", {"type": "image.faceswap", "project": "careyrpg",
                      "required_mode": "ANY", "required_caps": ["comfyui"],
                      "payload": {"target_artifact": src_id, "route": "preview",
                                  "project": "careyrpg", "purpose": "zone preview test"}})
        run_worker()
        previews = [a for a in api("/artifacts?limit=300") if a["kind"] == "image"
                    and json.loads(a["meta"] or "{}").get("recipe") == "facezone_preview@1"]
        check("zone preview archived overlay + mask (two artifacts)",
              len(previews) == 2, str(len(previews)))
        if len(previews) == 2:
            paths = sorted(a["path"] for a in previews)
            check("preview outputs are tellable apart (_mask/_overlay)",
                  any("_mask" in p for p in paths) and any("_overlay" in p for p in paths),
                  str(paths))
            pm = json.loads(previews[0]["meta"])
            check("preview card records detector + threshold, no seed",
                  pm.get("detector", "").startswith("bbox/")
                  and pm.get("threshold") == 0.5 and pm.get("seed") is None, str(pm))
            # the approved mask feeds the zone route by artifact id — the full
            # founder loop: preview -> approve -> GPU edits only that zone
            mask_art = next(a for a in previews if "_mask" in a["path"])
            api("/jobs", {"type": "image.faceswap", "project": "careyrpg",
                          "required_mode": "IMAGE", "required_caps": ["comfyui"],
                          "payload": {"target_artifact": src_id,
                                      "mask_artifact": mask_art["id"],
                                      "prompt": "the same man, cel shading",
                                      "project": "careyrpg",
                                      "purpose": "preview-mask zone edit"}})
            run_worker()
            chained = [a for a in api("/artifacts?limit=300")
                       if json.loads(a["meta"] or "{}").get("purpose") == "preview-mask zone edit"]
            check("preview mask chains into a zone edit by artifact id",
                  len(chained) == 1
                  and json.loads(chained[0]["meta"]).get("recipe") == "facezone@1",
                  str(len(chained)))

        # facelab_preflight: the on-PC proof tool must diagnose a ComfyUI
        # without ReActor (what the mock is) precisely and exit 2
        pf = subprocess.run([sys.executable, str(ROOT / "scripts" / "facelab_preflight.py")],
                            env={**os.environ, "BYRDHOUSE_ROOT": str(ROOT)},
                            capture_output=True, text=True, timeout=60)
        check("facelab preflight detects missing ReActor and exits 2",
              pf.returncode == 2 and "ReActor" in pf.stdout, pf.stdout[:200])

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

        # ── 2-PC coordination: the belt spans MINI (router) and GAMING (worker).
        #    These lock the machine-to-machine contract so a silent version split,
        #    a duplicate-work requeue, or an invisible upscale can't regress. ──
        print("== 2-PC coordination (version drift, requeue fencing, refine res)")
        h = api("/health")
        check("/health carries api_version + real build_sha",
              h.get("api_version") == "1" and h.get("build_sha") not in (None, "", "unknown"),
              str(h))
        router_sha = h["build_sha"]
        st = api("/status")
        check("/status reports the router build", st.get("router", {}).get("sha") == router_sha)
        check("/status carries a drift list", isinstance(st.get("drift"), list))
        # the real worker (run many times above) heartbeats its build; same repo
        # as the router, so it must match and NOT drift
        wrow = [w for w in st["workers"] if w.get("build_sha")]
        check("worker heartbeats its build_sha", bool(wrow), str(st["workers"]))
        check("matched worker/router builds do not drift",
              not any(d["issue"] == "commit_mismatch" and d.get("worker_sha") == router_sha
                      for d in st["drift"]))
        # a worker on another commit lights up the drift list (the silent-split guard)
        api("/workers/heartbeat", {"id": "worker-ghost", "host": "byrd-gaming",
                                   "caps": ["comfyui"], "mode": "IMAGE",
                                   "build_sha": "deadbeef1234", "api_version": "1"})
        drift = api("/status")["drift"]
        check("drift flags a worker on a different commit",
              any(d["worker"] == "worker-ghost" and d["issue"] == "commit_mismatch" for d in drift),
              str(drift))
        # requeue fencing: a live worker's running job cannot be requeued (would
        # duplicate work on the one GPU); a crashed (offline) worker's job can
        api("/workers/heartbeat", {"id": "worker-live", "host": "h", "caps": [],
                                   "mode": "ANY", "build_sha": router_sha, "api_version": "1"})
        fj = api("/jobs", {"type": "report.daily", "payload": {}})
        api("/jobs/claim", {"worker_id": "worker-live", "caps": [], "mode": "ANY"})
        api(f"/jobs/{fj['id']}/status", {"status": "running"})
        try:
            api(f"/jobs/{fj['id']}/requeue", {})
            check("requeue of a live running job is refused", False)
        except urllib.error.HTTPError as e:
            check("requeue of a live running job is refused (409)", e.code == 409, str(e.code))
        import sqlite3 as _sq
        _c = _sq.connect(ROOT / "db" / "byrdhouse.db")
        _c.execute("UPDATE workers SET last_heartbeat='2000-01-01T00:00:00+00:00' WHERE id='worker-live'")
        _c.commit(); _c.close()
        rq = api(f"/jobs/{fj['id']}/requeue", {})
        check("requeue allowed once the worker is offline (crash recovery)",
              rq["status"] == "queued" and rq["attempts"] == 0)
        # refine records the resolution change so an upscale is visible + on the card
        rsrc = [a for a in api("/artifacts?limit=80")
                if a["kind"] == "image" and a["path"] and str(ROOT) in a["path"]][0]
        rrj = api(f"/artifacts/{rsrc['id']}/refine", {"strength": 0.4, "scale": 1.5})
        run_worker()
        rref = [a for a in api("/artifacts?limit=120")
                if a["job_id"] == rrj["id"] and a["kind"] == "image"]
        check("refine records in_size/out_size/steps on the card",
              rref and all(k in json.loads(rref[0]["meta"]) for k in ("in_size", "out_size", "steps")),
              str(json.loads(rref[0]["meta"]) if rref else {}))

        # ── ByrdCast Swap V0: self-contained target-image-first face swap ──
        #    Structural contract: script exists, compiles, config/workflow/docs
        #    present, and a dry-run produces every required acceptance file.
        print("== ByrdCast Swap V0 (contract)")
        bcs_script = ROOT / "scripts" / "byrdcast_swap.py"
        bcs_config = ROOT / "configs" / "byrdcast_swap_v0.json"
        bcs_workflow = ROOT / "workflows" / "byrdcast_swap_v0.json"
        bcs_doc = ROOT / "docs" / "BYRDCAST_SWAP_V0.md"
        check("byrdcast_swap.py exists", bcs_script.is_file())
        check("byrdcast_swap config exists", bcs_config.is_file())
        check("byrdcast_swap workflow exists", bcs_workflow.is_file())
        check("byrdcast_swap docs exist", bcs_doc.is_file())

        bcs_src = bcs_script.read_text(encoding="utf-8") if bcs_script.is_file() else ""
        check("byrdcast_swap compiles",
              subprocess.run([sys.executable, "-c",
                              f"import py_compile; py_compile.compile({str(bcs_script)!r}, doraise=True)"],
                             capture_output=True, timeout=30).returncode == 0)
        check("byrdcast_swap has the 14-stage pipeline functions",
              "def detect_face(" in bcs_src
              and "def choose_reference(" in bcs_src
              and "def build_masks(" in bcs_src
              and "def run_swap(" in bcs_src
              and "def score_candidate(" in bcs_src
              and "def mask_overlay(" in bcs_src)
        check("byrdcast_swap detector chain: insightface -> opencv -> placeholder",
              '"method": "insightface"' in bcs_src
              and '"method": "opencv_haar"' in bcs_src
              and '"method": "placeholder_center"' in bcs_src)
        check("byrdcast_swap fails closed (accepted=false with reasons)",
              '"accepted": accepted' in bcs_src
              and '"reasons": reasons' in bcs_src
              and "accepted = (route" in bcs_src)
        check("byrdcast_swap supports --dry-run",
              '"--dry-run"' in bcs_src
              and "dry-run: swap/refine/blend skipped" in bcs_src)

        bcs_cfg = (json.loads(bcs_config.read_text(encoding="utf-8"))
                   if bcs_config.is_file() else {})
        check("byrdcast_swap config enforces 8GB budget",
              bcs_cfg.get("hardware", {}).get("vram_budget_mb") == 7200
              and bcs_cfg.get("hardware", {}).get("batch_size") == 1)
        check("byrdcast_swap config has reference selection weights",
              set(bcs_cfg.get("reference_selection", {}).get("weights", {}).keys())
              == {"face_angle", "expression", "lighting", "quality"})
        check("byrdcast_swap config has scoring weights + threshold",
              set(bcs_cfg.get("scoring", {}).get("weights", {}).keys())
              == {"identity_similarity", "mask_fit", "landmark_alignment",
                  "blend_quality", "artifact_risk"}
              and isinstance(bcs_cfg.get("scoring", {}).get("accept_threshold"), float))
        check("byrdcast_swap config has quality modes",
              {"fast", "balanced", "best"} <= set(bcs_cfg.get("quality_modes", {}).keys()))

        bcs_wf = (json.loads(bcs_workflow.read_text(encoding="utf-8"))
                  if bcs_workflow.is_file() else {})
        bcs_node_types = {n.get("class_type") for n in bcs_wf.values()
                          if isinstance(n, dict) and "class_type" in n}
        check("byrdcast_swap workflow has ReActor + FaceDetailer nodes",
              "ReActorFaceSwap" in bcs_node_types
              and "FaceDetailer" in bcs_node_types)
        check("byrdcast_swap workflow has TARGET and FACE load nodes",
              bcs_wf.get("target", {}).get("_meta", {}).get("title") == "TARGET"
              and bcs_wf.get("face", {}).get("_meta", {}).get("title") == "FACE")

        # Dry-run acceptance test: build a synthetic target + refs, run --dry-run,
        # verify every required output file is produced
        bcs_test_dir = ROOT / "_byrdcast_test"
        bcs_test_dir.mkdir(exist_ok=True)
        bcs_target = bcs_test_dir / "target.png"
        bcs_refs = bcs_test_dir / "refs"
        bcs_refs.mkdir(exist_ok=True)
        bcs_out = bcs_test_dir / "out"
        Image.new("RGB", (512, 512), (180, 140, 120)).save(bcs_target)
        Image.new("RGB", (256, 256), (200, 170, 150)).save(bcs_refs / "ref_01.png")
        Image.new("RGB", (256, 256), (190, 160, 140)).save(bcs_refs / "ref_02.png")
        bcs_run = subprocess.run(
            [sys.executable, str(bcs_script),
             "--identity", "TestId", "--target", str(bcs_target),
             "--refs", str(bcs_refs), "--out", str(bcs_out),
             "--quality", "best", "--dry-run"],
            env={**os.environ, "BYRDHOUSE_ROOT": str(ROOT)},
            capture_output=True, text=True, timeout=60)
        check("byrdcast_swap dry-run exits 0", bcs_run.returncode == 0,
              bcs_run.stderr[:300] if bcs_run.returncode != 0 else "")
        # Find the job folder (timestamped)
        bcs_jobs = sorted(bcs_out.glob("*")) if bcs_out.is_dir() else []
        bcs_job = bcs_jobs[0] if bcs_jobs else Path("/nonexistent")
        required_files = ["final.png", "face_detect_overlay.png", "mask_overlay.png",
                          "selected_reference.png", "score.json", "sidecar.json"]
        present = [f for f in required_files if (bcs_job / f).is_file()]
        check("dry-run produces all 6 required output files",
              len(present) == 6, f"got {present}")
        masks_dir = bcs_job / "masks"
        check("dry-run produces masks/ folder with zone PNGs",
              masks_dir.is_dir() and len(list(masks_dir.glob("*.png"))) >= 5,
              str(list(masks_dir.glob("*.png")) if masks_dir.is_dir() else []))
        if (bcs_job / "sidecar.json").is_file():
            bcs_sidecar = json.loads((bcs_job / "sidecar.json").read_text())
            check("dry-run sidecar marks accepted=false",
                  bcs_sidecar.get("accepted") is False)
            check("dry-run sidecar records the detector method",
                  bcs_sidecar.get("target_face", {}).get("method") in
                  ("insightface", "opencv_haar", "placeholder_center"))
            check("dry-run sidecar lists reasons for failure",
                  len(bcs_sidecar.get("reasons", [])) >= 1)

        # ── ByrdCoder Local V0 contract (docs/BYRDCODER_LOCAL.md) ──────────
        # Config / permission / allowlist behavior: the local coding agent
        # must default read-only, pin its bridge, never hardcode hosts, and
        # keep push/merge/secret paths structurally impossible.
        print("== byrdcoder local v0 contract")
        bc_dir = ROOT / "configs" / "byrdcoder"
        bc_profiles = ("byrd-ask", "byrd-patch", "byrd-build", "byrd-test",
                       "byrd-review", "byrd-offline", "byrd-private")
        for fname in ("BYRDCODER_LOCAL.md", "byrdcoder-model-benchmark.md",
                      "byrdcoder-security-review.md"):
            check(f"byrdcoder doc {fname} exists", (ROOT / "docs" / fname).is_file())
        for sname in ("byrdcoder-preflight.ps1", "start-byrdcoder.ps1",
                      "test-byrdcoder.ps1", "byrdcoder-benchmark.ps1"):
            check(f"byrdcoder script {sname} exists",
                  (ROOT / "scripts" / sname).is_file())
        for pyname in ("byrdcoder_models.py", "byrdcoder_review.py"):
            check(f"byrdcoder helper {pyname} compiles",
                  subprocess.run([sys.executable, "-m", "py_compile",
                                  str(ROOT / "scripts" / pyname)],
                                 capture_output=True).returncode == 0)

        bc_cfg = json.loads((bc_dir / "opencode.example.json").read_text())
        check("byrdcoder bridge plugin pinned",
              any(p.startswith("opencode-lmstudio@") and p[18:19].isdigit()
                  for p in bc_cfg.get("plugin", [])), str(bc_cfg.get("plugin")))
        check("byrdcoder LM Studio URL is a placeholder (zero hardcoded hosts)",
              bc_cfg["provider"]["lmstudio"]["options"]["baseURL"] == "{{LMSTUDIO_URL}}")
        check("byrdcoder default is read-only (global edit+bash+webfetch deny)",
              bc_cfg["permission"]["edit"] == "deny"
              and bc_cfg["permission"]["bash"].get("*") == "deny"
              and bc_cfg["permission"]["webfetch"] == "deny")
        check("byrdcoder share disabled + autoupdate off",
              bc_cfg.get("share") == "disabled" and bc_cfg.get("autoupdate") is False)
        check("byrdcoder defines all 7 profiles",
              set(bc_profiles) <= set(bc_cfg.get("agent", {})))
        for ro in ("byrd-ask", "byrd-review", "byrd-offline", "byrd-private"):
            a = bc_cfg["agent"][ro]
            check(f"byrdcoder {ro} is read-only",
                  a["permission"]["edit"] == "deny"
                  and a["tools"]["write"] is False and a["tools"]["edit"] is False)
        bb = bc_cfg["agent"]["byrd-build"]["permission"]["bash"]
        check("byrdcoder byrd-build cannot push/merge/reach main",
              bb.get("git push*") == "deny" and bb.get("git merge*") == "deny"
              and bb.get("git checkout main*") == "deny" and bb.get("*") == "deny")
        bt = bc_cfg["agent"]["byrd-test"]["permission"]
        check("byrdcoder byrd-test executes only allowlisted tests",
              bt["edit"] == "deny" and bt["bash"].get("*") == "deny"
              and bt["bash"].get("python tests/integration_test.py") == "allow")
        check("byrdcoder byrd-patch never applies (edit deny)",
              bc_cfg["agent"]["byrd-patch"]["permission"]["edit"] == "deny")

        bc_allow = json.loads((bc_dir / "allowlist.json").read_text())
        check("byrdcoder allowlist protects main",
              "main" in bc_allow["branches"]["protected"])
        check("byrdcoder deny list covers push/merge/delete/net/install",
              {"git push", "git merge", "git reset --hard", "rm", "Remove-Item",
               "pip install", "Invoke-WebRequest"} <= set(bc_allow["commands"]["deny"]))
        check("byrdcoder allow list has no escape hatches",
              not [c for c in bc_allow["commands"]["allow"]
                   if any(w in c for w in ("push", "merge", "rm", "del",
                                           "install", "curl", "wget"))])
        check("byrdcoder forbidden dirs cover secrets/identity/production",
              {".env", "secrets", "credentials", "db", "profiles/*/references",
               "Generators/ComfyUI"} <= set(bc_allow["directories"]["forbidden"]))
        for prof in bc_profiles:
            prompt = bc_dir / "prompts" / f"{prof}.md"
            check(f"byrdcoder prompt {prof}.md is substantive",
                  prompt.is_file() and len(prompt.read_text()) > 200)
        raw_cfg = (bc_dir / "opencode.example.json").read_text()
        check("byrdcoder example config has no hardcoded host/IP",
              "byrd-gaming" not in raw_cfg and "http://" not in raw_cfg.replace(
                  "https://opencode.ai/config.json", ""))

        # ── ByrdCoder ComfyUI MCP layer (docs/BYRDCODER_COMFY_MCP.md) ──────
        # Role A behavioral proof: path traversal and unmapped parameter
        # overrides are REJECTED; dangerous upstream tools stay absent;
        # read-only mode hides write tools. Role B: pinned version + hard env.
        print("== byrdcoder comfyui mcp layer")
        sys.path.insert(0, str(ROOT / "scripts"))
        import byrd_comfy_mcp as bcm

        check("comfy-mcp doc exists", (ROOT / "docs" / "BYRDCODER_COMFY_MCP.md").is_file())
        manifest = bcm.load_manifest(ROOT)
        check("comfy-mcp approved manifest loads with entries",
              len(manifest["approved"]) >= 1, str(sorted(manifest["approved"])))
        for rid, entry in manifest["approved"].items():
            try:
                bcm.resolve_workflow_path(ROOT, entry["workflow"])
                wf_ok = True
            except ValueError:
                wf_ok = False
            check(f"comfy-mcp approved '{rid}' workflow resolves safely", wf_ok)
            rec = ROOT / "recipes" / f"{entry['recipe']}.v{entry['recipe_version']}.json"
            check(f"comfy-mcp approved '{rid}' recipe file exists", rec.is_file())
            check(f"comfy-mcp approved '{rid}' params are typed",
                  all(p.get("type") in ("string", "int", "float", "enum")
                      for p in entry.get("params", {}).values()))

        def rejects(fn, *fargs):
            try:
                fn(*fargs)
                return False
            except ValueError:
                return True
        check("comfy-mcp rejects .. path traversal",
              rejects(bcm.resolve_workflow_path, ROOT, "workflows/../db/byrdhouse.db"))
        check("comfy-mcp rejects parent-escape traversal",
              rejects(bcm.resolve_workflow_path, ROOT, "../secrets/evil.json"))
        check("comfy-mcp rejects absolute paths",
              rejects(bcm.resolve_workflow_path, ROOT, "/etc/passwd")
              and rejects(bcm.resolve_workflow_path, ROOT, "C:/Windows/evil.json"))
        check("comfy-mcp rejects paths outside workflows/",
              rejects(bcm.resolve_workflow_path, ROOT, "recipes/fast_preview.v1.json"))

        fp_entry = manifest["approved"]["fast_preview"]
        check("comfy-mcp rejects unmapped override by name",
              rejects(bcm.validate_overrides, fp_entry,
                      {"prompt": "ok", "checkpoint_path": "../../evil"}))
        check("comfy-mcp rejects enum value outside allowed set",
              rejects(bcm.validate_overrides, fp_entry, {"aspect": "4:3"}))
        check("comfy-mcp rejects overlong string override",
              rejects(bcm.validate_overrides, fp_entry, {"prompt": "x" * 501}))
        check("comfy-mcp accepts a valid mapped override set",
              bcm.validate_overrides(fp_entry,
                                     {"prompt": "castle at dawn", "aspect": "16:9"})
              == {"prompt": "castle at dawn", "aspect": "16:9"})
        int_entry = {"params": {"steps": {"type": "int", "min": 1, "max": 40}}}
        check("comfy-mcp rejects out-of-bounds int override",
              rejects(bcm.validate_overrides, int_entry, {"steps": 999})
              and rejects(bcm.validate_overrides, int_entry, {"steps": 0}))

        roster = {t["name"] for t in bcm.TOOLS}
        check("comfy-mcp removed upstream tools stay absent",
              not (roster & set(bcm.REMOVED_TOOLS)), str(roster & set(bcm.REMOVED_TOOLS)))
        check("comfy-mcp keeps the useful surface",
              {"list_recipes", "describe_recipe", "submit_recipe", "job_status",
               "cancel_job", "regenerate", "asset_meta", "last_error"} <= roster)
        os.environ["BYRD_COMFY_MCP_READONLY"] = "1"
        try:
            ro_roster = {t["name"] for t in bcm.visible_tools()}
            check("comfy-mcp read-only mode hides write tools",
                  not ({"submit_recipe", "cancel_job", "regenerate"} & ro_roster)
                  and "list_recipes" in ro_roster)
            blocked, is_err = bcm.call_tool({}, "submit_recipe", {"recipe_id": "fast_preview"})
            check("comfy-mcp read-only mode blocks submit with a tier message",
                  is_err and "read-only" in blocked.get("error", ""))
        finally:
            del os.environ["BYRD_COMFY_MCP_READONLY"]

        oc_cfg = json.loads((bc_dir / "opencode.example.json").read_text())
        mcp = oc_cfg.get("mcp", {})
        check("comfy-mcp wired into opencode config, read-only by default",
              mcp.get("byrd-comfy", {}).get("environment", {})
                 .get("BYRD_COMFY_MCP_READONLY") == "1"
              and mcp.get("byrd-comfy", {}).get("enabled") is True)
        lab = mcp.get("comfyui-lab", {})
        check("comfyui-lab pinned to 0.34.0 and disabled by default",
              any("comfyui-mcp@0.34.0" in c for c in lab.get("command", []))
              and lab.get("enabled") is False)
        lab_env = lab.get("environment", {})
        check("comfyui-lab env: no autoinstall/autoupdate, compact mode, no tokens",
              lab_env.get("COMFYUI_MCP_PANEL_AUTOINSTALL") == "0"
              and lab_env.get("COMFYUI_MCP_AUTOUPDATE") == "0"
              and lab_env.get("COMFYUI_MCP_TOOL_MODE") == "compact"
              and not ({"CIVITAI_API_TOKEN", "HUGGINGFACE_TOKEN", "COMFYUI_API_KEY"}
                       & set(lab_env)))
        for prof in ("byrd-offline", "byrd-private"):
            tools = oc_cfg["agent"][prof]["tools"]
            check(f"comfy-mcp servers disabled in {prof}",
                  tools.get("byrd-comfy*") is False and tools.get("comfyui-lab*") is False)

        lab_env_file = (bc_dir / "comfyui-mcp-lab.env.example").read_text()
        check("comfyui-lab env example pins version + reviewed commit",
              "comfyui-mcp@0.34.0" in lab_env_file
              and "6a7ceeb9b578a149b0da65b43e0def708f0b3078" in lab_env_file)
        lab_url_lines = [ln for ln in lab_env_file.splitlines()
                         if ln.startswith("COMFYUI_URL=")]
        check("comfyui-lab env example never points at production :8188",
              lab_url_lines and all("8188" not in ln for ln in lab_url_lines))
        check("lab + candidates gate READMEs exist",
              (ROOT / "workflows" / "experiments" / "comfyui-mcp-lab" / "README.md").is_file()
              and (ROOT / "workflows" / "candidates" / "README.md").is_file())

        # ── Identity + Face Acceptance Layer (2026-07-19) ────────────────────
        # Post-generation check: did the face survive in the output?
        # Runs on the FINAL composite (not the target), flags framing failures.
        print("== acceptance check (output-side face gate)")
        check("acceptance_check function exists in byrdfacezone",
              "def acceptance_check(" in facezone_source)
        check("accept subcommand registered in byrdfacezone parse_args",
              '"accept"' in facezone_source
              and 'accept.add_argument("--image"' in facezone_source
              and 'acceptance_check(args.root, args.image' in facezone_source)
        check("acceptance_check has all required output keys",
              '"accepted"' in facezone_source
              and '"face_count"' in facezone_source
              and '"framing_ok"' in facezone_source
              and '"flags"' in facezone_source
              and '"face_crop_preview"' in facezone_source
              and '"side_px"' in facezone_source
              and '"check_seconds"' in facezone_source)
        check("acceptance_check checks all four framing edges",
              "face_cropped_left" in facezone_source
              and "face_cropped_right" in facezone_source
              and "face_cropped_top" in facezone_source
              and "face_cropped_bottom" in facezone_source)
        check("acceptance_check saves face_crop_preview when output_dir provided",
              "_accept_crop.jpg" in facezone_source
              and "crop_img.save(" in facezone_source)
        check("acceptance_check never raises on detection failure",
              "except RuntimeError as exc:" in facezone_source
              and "no_face_detected" in facezone_source
              and "result[\"check_seconds\"]" in facezone_source)
        check("acceptance_check accepted=True only when framing_ok and single face",
              "result[\"accepted\"] = result[\"framing_ok\"] and total == 1"
              in facezone_source)
        check("edit_face_zone calls acceptance check on every final composite",
              "accept_cmd" in byrdimage_source
              and '"accept"' in byrdimage_source
              and '"--image", str(final)' in byrdimage_source
              and '"--output-dir"' in byrdimage_source)
        check("output_acceptance block written to card",
              'card["output_acceptance"]' in byrdimage_source)
        check("acceptance gate logs flags when output is flagged",
              '"acceptance gate: FLAGGED"' in byrdimage_source
              and '"output_acceptance.get(\"accepted\")' in byrdimage_source
              or 'acceptance gate: FLAGGED' in byrdimage_source)
        check("repo comparison doc exists",
              (ROOT / "docs" / "REPO_COMPARISON.md").is_file())
        repo_cmp = ((ROOT / "docs" / "REPO_COMPARISON.md").read_text(encoding="utf-8-sig")
                    if (ROOT / "docs" / "REPO_COMPARISON.md").is_file() else "")
        check("comparison doc covers ZPix, gimp-mcp, adopt/reject verdicts, and three specs",
              "ZPix" in repo_cmp
              and "gimp-mcp" in repo_cmp
              and "Create Room" in repo_cmp
              and "Identity + Face Acceptance Layer" in repo_cmp
              and "Media Finisher" in repo_cmp
              and "Adopt" in repo_cmp)

        print("== dashboard — acceptance badge + seed lock + rerun button")
        dashboard_source = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        check("dashboard artCard stores meta for rerun lookup",
              "window._artMeta" in dashboard_source
              and "window._artMeta[a.id] = meta" in dashboard_source)
        check("dashboard artCard computes acceptance badge from output_acceptance",
              "output_acceptance" in dashboard_source
              and "acceptBadge" in dashboard_source
              and "face OK" in dashboard_source
              and "var(--green)" in dashboard_source)
        check("dashboard artCard shows yellow flag badge when face flagged",
              "_shortFlag" in dashboard_source
              and "var(--yellow)" in dashboard_source
              and "_oa.flags" in dashboard_source)
        check("dashboard artCard renders rerun button when reproduce block present",
              "hasRerun" in dashboard_source
              and "copyRerun" in dashboard_source
              and "meta.reproduce" in dashboard_source)
        check("dashboard face swap panel has seed field",
              'id="swapSeed"' in dashboard_source
              and 'type="number"' in dashboard_source
              and 'swapSeedLock' in dashboard_source)
        check("dashboard face swap panel has lock and random seed buttons",
              "toggleSwapSeedLock" in dashboard_source
              and "randomSwapSeed" in dashboard_source)
        check("submitSwap wires seed into payload",
              "_seedRaw" in dashboard_source
              and "payload.seed = _seedRaw" in dashboard_source)
        check("copyRerun builds facelab.ps1 command from reproduce block",
              "function copyRerun(" in dashboard_source
              and "facelab.ps1 quality" in dashboard_source
              and "navigator.clipboard.writeText" in dashboard_source)
        # ── Face-lane repair guards (2026-07-16, hard Vegeta failure) ──────
        # The 10 required automated tests: honest diffdiff graphs, pre-submit
        # model gating, LoRA truth, outside-mask preservation, eye protection,
        # geometry gate fail-closed, and rich ComfyUI HTTP errors.
        print("== face-lane repair guards")
        sys.path.insert(0, str(ROOT / "scripts"))
        import byrdimage as bi
        import facezone_composite as fzc
        from PIL import Image as PILImage, ImageDraw as PILDraw

        # 1. JSON workflow validation
        dd_true = json.loads((ROOT / "workflows" / "sd15_face_zone_diffdiff_api.json").read_text())
        dd_combo = json.loads((ROOT / "workflows" / "sd15_face_zone_diffdiff_canny_api.json").read_text())
        check("diffdiff workflows are valid JSON graphs",
              any(n.get("class_type") == "KSampler" for n in dd_true.values() if isinstance(n, dict))
              and any(n.get("class_type") == "KSampler" for n in dd_combo.values() if isinstance(n, dict)))

        # 3. TRUE diffdiff contains no ControlNet anything
        true_classes = {n.get("class_type") for n in dd_true.values() if isinstance(n, dict)}
        check("TRUE diffdiff has no ControlNet nodes",
              not any(c and "ControlNet" in c for c in true_classes),
              str(true_classes))
        check("TRUE diffdiff keeps the graded-mask seam killer",
              {"DifferentialDiffusion", "SetLatentNoiseMask"} <= true_classes)
        sampler = next(n for n in dd_true.values()
                       if isinstance(n, dict) and n.get("class_type") == "KSampler")
        check("TRUE diffdiff sampler conditioned straight from the prompts",
              sampler["inputs"]["positive"][0] == "5" and sampler["inputs"]["negative"][0] == "6")
        combo_classes = {n.get("class_type") for n in dd_combo.values() if isinstance(n, dict)}
        check("combined diffdiff-canny is clearly the ControlNet variant",
              "ControlNetLoader" in combo_classes and "DifferentialDiffusion" in combo_classes)

        # 2. /object_info-style schema validation (same helper preflight uses live)
        core_catalog = {c for c in (true_classes | combo_classes) if c} - {"ControlNetLoader"}
        check("schema validation passes for TRUE diffdiff on a ControlNet-less server",
              bi.validate_graph_classes(dd_true, core_catalog) == [])
        check("schema validation names ControlNetLoader missing for the combined graph",
              bi.validate_graph_classes(dd_combo, core_catalog) == ["ControlNetLoader"])

        # 4. combined route refuses BEFORE submit when the canny model is missing
        def raises_value(fn, *fargs):
            try:
                fn(*fargs)
                return None
            except ValueError as exc:
                return str(exc)
        msg = raises_value(bi.require_workflow_models, ROOT, dd_combo,
                           "workflows/sd15_face_zone_diffdiff_canny_api.json")
        check("combined graph refuses pre-submit and names the missing model",
              bool(msg) and "control_v11p_sd15_canny" in msg and "NOT installed" in msg, str(msg)[:120])
        check("TRUE diffdiff needs no model gate",
              raises_value(bi.require_workflow_models, ROOT, dd_true, "x") is None)
        cn_dir = ROOT / "Generators" / "ComfyUI" / "models" / "controlnet"
        cn_dir.mkdir(parents=True, exist_ok=True)
        (cn_dir / "control_v11p_sd15_canny.safetensors").write_bytes(b"fake")
        check("combined graph passes once the canny model exists",
              raises_value(bi.require_workflow_models, ROOT, dd_combo, "x") is None)

        # 5. job LoRA overrides stale recipe value; no silent preview promotion
        lora_dir = ROOT / "Generators" / "ComfyUI" / "models" / "loras"
        lora_dir.mkdir(parents=True, exist_ok=True)
        (lora_dir / "carey_preview_hybrid_r32_1200.safetensors").write_bytes(b"fake")
        name, status = bi.select_identity_lora(ROOT, {"lora": "carey_meina_sd15_v1.safetensors"},
                                               "carey_preview_hybrid_r32_1200")
        check("explicit -Lora overrides the stale recipe LoRA cleanly",
              name == "carey_preview_hybrid_r32_1200.safetensors"
              and "explicit-override" in status and "preview" in status)
        msg = raises_value(bi.select_identity_lora, ROOT,
                           {"lora": "carey_meina_sd15_v1.safetensors"}, None)
        check("stale recipe LoRA is refused by name, never partial-matched to a preview",
              bool(msg) and "carey_meina_sd15_v1" in msg and "not installed" in msg)
        msg = raises_value(bi.select_identity_lora, ROOT, {}, None)
        check("no deployed LoRA is said plainly",
              bool(msg) and "no deployed identity LoRA" in msg)
        for rv in ("2", "3"):
            rj = json.loads((ROOT / "recipes" / f"anime_face_zone_edit.v{rv}.json").read_text())
            check(f"anime_face_zone_edit v{rv} no longer ships the stale deployed-LoRA claim",
                  rj["identity"]["lora"] is None)

        # 6. outside-mask pixels remain unchanged (and tampering is caught)
        orig = PILImage.new("RGB", (64, 64), (40, 80, 120))
        gen = PILImage.new("RGB", (64, 64), (200, 60, 60))
        mask = PILImage.new("L", (64, 64), 0)
        PILDraw.Draw(mask).ellipse((20, 20, 44, 44), fill=255)
        final_img = orig.copy()
        final_img.paste(gen, (0, 0), mask)
        check("outside-mask preservation verifies a clean composite",
              fzc.verify_outside_mask(orig, final_img, mask)["passed"] is True)
        tampered = final_img.copy()
        tampered.putpixel((2, 2), (255, 255, 255))
        bad = fzc.verify_outside_mask(orig, tampered, mask)
        check("outside-mask verification catches a leak",
              bad["passed"] is False and bad["changed_pixels"] >= 1)
        leaky = PILImage.new("L", (64, 64), 0)
        PILDraw.Draw(leaky).rectangle((0, 0, 63, 30), fill=255)  # touches the border
        clamped, frac = fzc.clamp_mask_border(leaky)
        check("rectangular border leak is clamped and measured",
              frac > 0 and clamped.getpixel((0, 0)) == 0 and clamped.getpixel((32, 20)) == 255)

        # 7. eye_source=target restores protected eye pixels exactly
        eye_mask = PILImage.new("L", (64, 64), 0)
        PILDraw.Draw(eye_mask).ellipse((24, 26, 40, 36), fill=255)
        restored = fzc.restore_protected_material(gen, orig, eye_mask)
        check("protected target-eye pixels are restored after generation",
              restored.getpixel((32, 31)) == (40, 80, 120)
              and restored.getpixel((5, 5)) == (200, 60, 60))

        # D. raw-triangle shard heuristic
        shardy = PILImage.new("L", (128, 128), 128)
        d = PILDraw.Draw(shardy)
        for i in range(0, 128, 9):
            d.line((0, i, 127, i), fill=255, width=1)
            d.line((i, 0, i, 127), fill=255, width=1)
        full = PILImage.new("L", (128, 128), 255)
        verdict = fzc.mesh_shard_score(shardy.convert("RGB"), full)
        check("shard detector flags dense straight seams",
              verdict["shards_detected"] is True, str(verdict))
        smooth = PILImage.new("RGB", (128, 128), (120, 110, 100))
        check("shard detector passes a smooth face crop",
              fzc.mesh_shard_score(smooth, full)["shards_detected"] is False)

        # 8. geometry_stability=0 can never yield a CPU-only founder-facing final
        unstable_report = {"faces": [{"index": 0, "flags": ["strong_profile"],
                                      "checks": {"geometry_stability": 0.0,
                                                 "geometry_warning": "landmarks disagree across scales"}}]}
        g = bi.geometry_gate(unstable_report)
        check("geometry gate blocks unstable mesh case and CPU-only final",
              g["mesh_case_allowed"] is False and g["cpu_final_allowed"] is False
              and len(g["reasons"]) >= 2 and "reviewed-mask" in g["fallback"])
        stable_report = {"faces": [{"index": 0, "flags": [],
                                    "checks": {"geometry_stability": 0.92}}]}
        g2 = bi.geometry_gate(stable_report)
        check("geometry gate passes stable geometry",
              g2["mesh_case_allowed"] is True and g2["reasons"] == [])
        g3 = bi.geometry_gate({"faces": [{"index": 0, "flags": [], "checks": {}}]})
        check("unmeasurable stability fails closed",
              g3["mesh_case_allowed"] is False)

        # 9. HTTP 400 responses surface the body, node_errors, ids and classes
        err_body = json.dumps({
            "error": {"type": "prompt_outputs_failed_validation",
                      "message": "Prompt outputs failed validation"},
            "node_errors": {"13": {"class_type": "ControlNetLoader", "errors": [
                {"type": "value_not_in_list",
                 "message": "control_net_name 'control_v11p_sd15_canny.safetensors' not in []"}]}}})
        formatted = bi._format_comfy_http_error(400, err_body)
        check("ComfyUI HTTP 400 surfaces status, node id, class and message",
              "HTTP 400" in formatted and "node 13" in formatted
              and "ControlNetLoader" in formatted and "value_not_in_list" in formatted,
              formatted[:160])
        check("non-JSON error bodies are still printed",
              "some html error page" in bi._format_comfy_http_error(500, "some html error page"))

        # Free swap stack skeleton (docs/FREE_SWAP_STACK.md): photo-anchored
        # identity needs NO LoRA and the doc keeps the lane license-clean.
        free_doc = (ROOT / "docs" / "FREE_SWAP_STACK.md")
        check("free swap stack skeleton doc exists",
              free_doc.is_file() and "Excluded on purpose" in free_doc.read_text(encoding="utf-8-sig"))
        bi_source = (ROOT / "scripts" / "byrdimage.py").read_text(encoding="utf-8-sig")
        check("photo-anchored workflows run LoRA-free (license-clean identity)",
              '"IDENTITY PHOTO\\"" in' in repr(bi_source) or '\'"IDENTITY PHOTO"\'' in bi_source
              or '"IDENTITY PHOTO"' in bi_source)
        check("LoRA splice is conditional, never mandatory",
              "if selected_identity_lora:" in bi_source
              and "photo-anchored identity" in bi_source)
        ipad_graph = json.loads((ROOT / "workflows" / "sd15_face_zone_ipadapter_api.json")
                                .read_text(encoding="utf-8-sig"))
        check("avenue-B zone graph really has the IDENTITY PHOTO anchor node",
              any(n.get("_meta", {}).get("title") == "IDENTITY PHOTO"
                  for n in ipad_graph.values() if isinstance(n, dict)))

        # The conductor (byrdswap.py): the bot's lane decisions, zero GPU.
        import byrdswap
        stable_rep = {"faces": [{"index": 0, "flags": [],
                                 "checks": {"geometry_stability": 0.9}}]}
        unstable_rep = {"faces": [{"index": 0, "flags": ["strong_profile"],
                                   "checks": {"geometry_stability": 0.0,
                                              "geometry_warning": "landmarks disagree across scales"}}]}
        p = byrdswap.plan_ladder(unstable_rep, lora="x", identity_photo="p.jpg")
        check("conductor stops on unstable geometry with manual next steps",
              p["lanes"] == [] and "geometry gate" in p["stop_reason"]
              and any("zone" in s for s in p["manual_next"]))
        p = byrdswap.plan_ladder(stable_rep, lora=None, identity_photo="p.jpg")
        check("conductor picks the free photo-anchored lane first, no LoRA",
              p["lanes"][0]["lane"] == "quality_photo_anchored"
              and any(s["lane"] == "quality_lora_mesh" for s in p["skipped"]))
        p = byrdswap.plan_ladder(stable_rep, lora="preview_r32", identity_photo=None)
        check("conductor uses explicit LoRA lanes when photo is unavailable",
              [l["lane"] for l in p["lanes"]] == ["quality_lora_mesh", "auto_facedetailer"]
              and any(s["lane"] == "quality_photo_anchored" for s in p["skipped"]))
        p = byrdswap.plan_ladder(stable_rep, lora=None, identity_photo=None)
        check("conductor says plainly when nothing is runnable",
              p["lanes"] == [] and "stop_reason" in p)
        check("facelab run command wires the conductor",
              '"run"' in (ROOT / "scripts" / "facelab.ps1").read_text(encoding="utf-8-sig")
              and "byrdswap.py" in (ROOT / "scripts" / "facelab.ps1").read_text(encoding="utf-8-sig"))

        # The founder-verified gojo avenue (d0.28 / mesh 0.40) + finish pass
        check("gojo avenue codified: identity_fill d0.28, mesh 0.40, eyes protected, cleanup ON",
              byrdswap.GOJO_AVENUE_ENGINE["gpu_passes"]["identity_fill"]["denoise"] == 0.28
              and byrdswap.GOJO_AVENUE_ENGINE["mesh_identity_strength"] == 0.40
              and byrdswap.GOJO_AVENUE_ENGINE["eye_source"] == "target"
              and byrdswap.GOJO_AVENUE_ENGINE["skip_gpu_cleanup"] is False)
        p = byrdswap.plan_ladder(stable_rep, lora="preview", identity_photo=None)
        check("conductor's LoRA lane rides the gojo avenue",
              p["lanes"][0]["engine"].get("mesh_identity_strength") == 0.40)
        # Golden-run replay (reproduce the runs that actually worked)
        import byrdswap_replay as replay
        golden_card = {"recipe": "anime_face_zone_edit@2", "seed": 42,
                       "lora": "carey_hybrid_r32.safetensors",
                       "workflow": "workflows/sd15_face_mesh_seed_multipass_api.json",
                       "target": "E:/x/gojo.png", "target_preset": "gojo",
                       "gpu_passes": [{"id": "identity_fill", "denoise": 0.28},
                                      {"id": "line_harmonize", "denoise": 0.12}],
                       "face_zone": {"identity_mesh": {"mesh_identity_strength": 0.40,
                                                       "eye_source_mode": "target"}}}
        gp = replay.extract_golden_params(golden_card)
        check("replay recovers the golden parameters from a card",
              gp["denoise_per_pass"]["identity_fill"] == 0.28
              and gp["mesh_identity_strength"] == 0.40 and gp["seed"] == 42)
        today = json.loads((ROOT / "recipes" / "anime_face_zone_edit.v2.json")
                           .read_text(encoding="utf-8-sig"))
        drift = replay.diff_vs_recipe(gp, today)
        check("replay names remaining drift (recipe now MATCHES the golden denoise)",
              not any("identity_fill" in d for d in drift)
              and any("LoRA" in d for d in drift))
        old_recipe = {"defaults": {"gpu_passes": {"identity_fill": {"denoise": 0.38}},
                                   "skip_gpu_cleanup": True}, "identity": {}}
        old_drift = replay.diff_vs_recipe(gp, old_recipe)
        check("replay catches denoise + skip drift against a stale recipe",
              any("0.28" in d and "0.38" in d for d in old_drift)
              and any("SKIPS gpu cleanup" in d for d in old_drift))
        check("replay emits an exact rerun command",
              "-Lora" in replay.rerun_command(gp) and "quality" in replay.rerun_command(gp))

        # Complete settings capture: every card carries a full reproduce block
        empty_block = bi.reproduce_block()
        check("reproduce block always contains every required key (None when n/a)",
              set(bi.REPRODUCE_REQUIRED) <= set(empty_block)
              and all(empty_block[k] is None for k in bi.REPRODUCE_REQUIRED))
        check("both face-zone card paths embed the reproduce block",
              bi_source.count('"reproduce": reproduce,') >= 2
              and '"workflow_sha256"' in bi_source)
        modern_card = {"seed": 42,
                       "reproduce": {"seed": 7, "lora": "x.safetensors",
                                     "gpu_passes": [{"id": "identity_fill", "denoise": 0.28}]}}
        check("replay prefers the complete reproduce block over legacy fields",
              replay.extract_golden_params(modern_card)["seed"] == 7
              and replay.extract_golden_params(modern_card)
                  ["denoise_per_pass"]["identity_fill"] == 0.28)

        # FINISH never edits a processed image: it re-renders generation 1
        # from the immutable original using the card's captured settings.
        fin_img = ROOT / "artifacts" / "fin_test.png"
        fin_img.parent.mkdir(parents=True, exist_ok=True)
        fin_img.write_bytes(b"png")
        Path(str(fin_img) + ".json").write_text(json.dumps(
            {"job_id": "job_x", "reproduce": {
                "target": "E:/originals/vegeta.jpg", "seed": 99,
                "lora": "hybrid_r32.safetensors", "target_preset": "vegeta",
                "recipe": "anime_face_zone_edit@2",
                "engine": {"crop_size": 640}}}))
        fsrc = byrdswap.finish_source(fin_img)
        check("finish re-renders from the immutable original with the same seed",
              fsrc["original"] == "E:/originals/vegeta.jpg" and fsrc["seed"] == 99
              and fsrc["recipe"] == "anime_face_zone_edit@2"
              and fsrc["engine"] == {"crop_size": 640})
        bare = ROOT / "artifacts" / "bare.png"
        bare.write_bytes(b"png")
        try:
            byrdswap.finish_source(bare)
            fin_refused = False
        except ValueError as exc:
            fin_refused = "no generation card" in str(exc)
        check("finish refuses a cardless image instead of guessing", fin_refused)
        check("every card is generation 1 (edit-on-edit structurally refused)",
              bi_source.count('"generation": 1,') >= 3
              and "fresh-retry policy rejected" in bi_source
              and '"finish"' in (ROOT / "scripts" / "facelab.ps1").read_text(encoding="utf-8-sig"))

        # No-op law: an untouched copy must never ship as a result.
        same = PILImage.new("RGB", (64, 64), (90, 90, 90))
        check("edit_delta calls an untouched copy a no-op",
              fzc.edit_delta(same, same.copy())["edited"] is False)
        changed_img = same.copy()
        PILDraw.Draw(changed_img).ellipse((20, 20, 44, 44), fill=(180, 120, 90))
        check("edit_delta confirms a real zone edit",
              fzc.edit_delta(same, changed_img)["edited"] is True
              and fzc.edit_delta(same, changed_img, mask)["edited"] is True)
        # Bounded advisor fixes (2026-07-16): restyle after swap + hard_anime routing
        bcs_cfg_now = json.loads((ROOT / "configs" / "byrdcast_swap_v0.json").read_text(encoding="utf-8-sig"))
        check("swap restyle pass: FaceDetailer denoise 0.40 with 14px feather",
              bcs_cfg_now["refine"]["facedetailer_denoise"] == 0.4
              and bcs_cfg_now["refine"]["facedetailer_feather_px"] == 14)
        bi_source_now = (ROOT / "scripts" / "byrdimage.py").read_text(encoding="utf-8-sig")
        check("hard_anime targets are refused by ReActor and routed to the redraw path",
              "hard_anime target: ReActor paste is disabled" in bi_source_now
              and "extreme_expression" in bi_source_now)
        check("no-op outputs are rejected on every lane (run_graph + zone paths)",
              bi_source_now.count("untouched copy") >= 3
              and "images_effectively_identical" in bi_source_now
              and '"edit_applied"' in (ROOT / "scripts" / "byrdfacezone.py")
                  .read_text(encoding="utf-8-sig"))

        # ── realistic_reactor_refine lane (2026-07-20) ──────────────────────
        # Preferred conductor lane for stable, front-facing, realistic human
        # targets. Pure-function proof of the Stage 3 mask policy, Stage 4
        # denoise clamp, Stage 5 verifier, and the conductor routing — zero GPU.
        print("== realistic_reactor_refine lane")
        lane_cfg_path = ROOT / "configs" / "image" / "realistic_reactor_refine.json"
        check("lane config exists and is valid JSON", lane_cfg_path.is_file())
        lane_cfg = json.loads(lane_cfg_path.read_text(encoding="utf-8-sig"))
        check("lane config is flagged non-commercial / private-experiment",
              lane_cfg["license"]["non_commercial"] is True
              and "private-local-experiment" in lane_cfg["license"]["scope"])
        check("lane config keeps the cleanup denoise in the 0.20-0.35 band",
              lane_cfg["refine"]["denoise_min"] == 0.20
              and lane_cfg["refine"]["denoise_max"] == 0.35
              and lane_cfg["refine"]["denoise_refuse_at_or_above"] <= 0.50)

        sys.path.insert(0, str(ROOT / "scripts"))
        import realistic_reactor_refine as rrr
        import byrdswap as bswap

        # Stage 4: denoise clamp — refuse the identity-regenerating 0.55, keep 0.28
        rc = lane_cfg["refine"]
        d_hi = rrr.clamp_refine_denoise(0.55, rc)
        d_ok = rrr.clamp_refine_denoise(0.28, rc)
        d_lo = rrr.clamp_refine_denoise(0.10, rc)
        check("denoise 0.55 is refused (would regenerate the target identity)",
              d_hi["refused"] is True and d_hi["denoise"] <= 0.35)
        check("denoise 0.28 passes through unchanged",
              d_ok["denoise"] == 0.28 and d_ok["refused"] is False)
        check("denoise 0.10 clamps up into the band",
              d_lo["denoise"] == 0.20 and d_lo["clamped"] is True)

        # Stage 5: verifier — every status code reachable, accept only on clean pass
        vc = lane_cfg["verification"]
        v_pass = rrr.verify_identity(0.50, True, 10.0, False, vc)
        v_idf = rrr.verify_identity(0.10, True, 10.0, False, vc)
        v_unm = rrr.verify_identity(None, True, 10.0, False, vc)
        v_hair = rrr.verify_identity(0.50, True, 10.0, True, vc)
        v_seam = rrr.verify_identity(0.50, True, 99.0, False, vc)
        v_noface = rrr.verify_identity(0.50, False, 10.0, False, vc)
        check("verifier: clean pass -> IDENTITY_PASS accepted",
              v_pass["primary_status"] == "IDENTITY_PASS" and v_pass["accepted"] is True)
        check("verifier: low similarity -> IDENTITY_FAIL rejected",
              v_idf["primary_status"] == "IDENTITY_FAIL" and v_idf["accepted"] is False)
        check("verifier: unmeasured identity fails closed",
              v_unm["primary_status"] == "IDENTITY_FAIL" and v_unm["accepted"] is False)
        check("verifier: doubled beard -> FACIAL_HAIR_FAIL not accepted",
              "FACIAL_HAIR_FAIL" in v_hair["statuses"] and v_hair["accepted"] is False)
        check("verifier: high seam energy -> SEAM_FAIL not accepted",
              "SEAM_FAIL" in v_seam["statuses"] and v_seam["accepted"] is False)
        check("verifier: no face -> FACE_DETECTION_FAIL, identity not judged",
              v_noface["primary_status"] == "FACE_DETECTION_FAIL"
              and "IDENTITY_PASS" not in v_noface["statuses"]
              and v_noface["accepted"] is False)

        # Stage 3: facial-hair-aware mask — facial hair INSIDE, scalp OUTSIDE
        box = [120, 120, 280, 320]
        masks = rrr.build_facial_identity_mask((400, 500), box, lane_cfg["facial_hair_mask"])
        bw, bh = box[2] - box[0], box[3] - box[1]
        cx = (box[0] + box[2]) // 2
        chin = masks["identity"].getpixel((cx, box[3] - int(bh * 0.05)))
        scalp_in_ident = masks["identity"].getpixel((cx, box[1] + int(bh * 0.08)))
        scalp_in_scalp = masks["scalp_exclude"].getpixel((cx, box[1] + int(bh * 0.08)))
        sideburn = masks["identity"].getpixel((box[0] + int(bw * 0.03), box[1] + int(bh * 0.6)))
        check("mask: chin/beard is inside the identity zone", chin > 160)
        check("mask: scalp is OUTSIDE the identity zone", scalp_in_ident < 96)
        check("mask: scalp is inside the scalp-exclude zone", scalp_in_scalp > 160)
        check("mask: sideburn is inside the identity zone", sideburn > 120)

        # Conductor routing — realism/frontal signals + lane order
        def _rep(stability=0.8, yaw=0.1, parser="selfie_multiclass", flags=None):
            return {"faces": [{"index": 0, "flags": flags or [],
                               "checks": {"geometry_stability": stability,
                                          "yaw_asymmetry": yaw, "parser": parser}}]}
        p_real = bswap.plan_ladder(_rep(), reactor_available=True, has_references=True,
                                   identity_photo="p.jpg")
        check("conductor: stable+frontal+realistic -> realistic_reactor_refine is FIRST",
              p_real["lanes"] and p_real["lanes"][0]["lane"] == "realistic_reactor_refine"
              and "quality_photo_anchored" not in [l["lane"] for l in p_real["lanes"]]
              and "quality_photo_anchored" in [s["lane"] for s in p_real["skipped"]])
        p_anime = bswap.plan_ladder(_rep(parser="parsenet-anime-fallback"),
                                    reactor_available=True, has_references=True,
                                    identity_photo="p.jpg", lora="carey_v2")
        check("conductor: anime target never gets the reactor lane",
              "realistic_reactor_refine" not in [l["lane"] for l in p_anime["lanes"]]
              and p_anime["realism"] == "stylized")
        p_noreactor = bswap.plan_ladder(_rep(), reactor_available=False,
                                        has_references=True, identity_photo="p.jpg")
        check("conductor: no ReActor installed -> realistic photo stops instead of anime fallback",
              "realistic_reactor_refine" in [s["lane"] for s in p_noreactor["skipped"]]
              and "quality_photo_anchored" in [s["lane"] for s in p_noreactor["skipped"]]
              and p_noreactor["lanes"] == [])
        p_profile = bswap.plan_ladder(_rep(yaw=0.45, flags=["strong_profile — strains"]),
                                      reactor_available=True, has_references=True,
                                      identity_photo="p.jpg")
        check("conductor: non-frontal/profile target does not get the reactor lane",
              p_profile["frontal"] is False
              and "realistic_reactor_refine" not in [l["lane"] for l in p_profile["lanes"]]
              and "quality_photo_anchored" not in [l["lane"] for l in p_profile["lanes"]])

        # ── examiner-schema normalization (2026-07-20 baseline stall) ────────
        # The REAL report nests geometry_stability/parser under "thorough" and
        # promotes yaw_asymmetry to the face top level — NOT under "checks".
        # This fixture has NO "checks" key, so any reader that only looks at
        # "checks" sees stability=None -> unstable gate -> zero lanes, and these
        # asserts fail. That is the regression guard the founder asked for.
        import byrdimage as bimg
        real_report = {"faces": [{
            "index": 0,
            "yaw_asymmetry": 0.0999,
            "flags": [],
            "thorough": {"geometry_stability": 0.987, "parser": "selfie_multiclass"},
        }]}
        sig = bimg.collect_face_signals(real_report["faces"][0])
        check("collect_face_signals lifts thorough + top-level fields",
              sig.get("geometry_stability") == 0.987
              and sig.get("parser") == "selfie_multiclass"
              and sig.get("yaw_asymmetry") == 0.0999)
        rg = bimg.geometry_gate(real_report)
        check("real report: geometry_gate is stable with stability 0.987",
              rg["stable"] is True and rg["geometry_stability"] == 0.987)
        check("real report: classify_realism == 'realistic'",
              bswap.classify_realism(real_report) == "realistic")
        check("real report: is_frontal is True (yaw 0.0999)",
              bswap.is_frontal(real_report) is True)
        rp = bswap.plan_ladder(real_report, reactor_available=True, has_references=True,
                               identity_photo="/tmp/carey_ref.jpg")
        check("real report: plan_ladder places realistic_reactor_refine FIRST",
              rp["lanes"] and rp["lanes"][0]["lane"] == "realistic_reactor_refine")

        # promoted runtime hotfixes (2026-07-20 — repo sync had reverted these)
        bswap_src = (ROOT / "scripts" / "byrdswap.py").read_text(encoding="utf-8-sig")
        check("conductor default recipe is anime_face_zone_edit@2 (resolvable), not .v2",
              'default="anime_face_zone_edit@2"' in bswap_src
              and 'default="anime_face_zone_edit.v2"' not in bswap_src)
        eng = bswap.PHOTO_ANCHORED_ENGINE("/tmp/ref.jpg")
        check("photo-anchored engine sets no_identity_mesh + one GPU pass 26/5.5/dpmpp_2m/karras/0.55",
              eng["no_identity_mesh"] is True
              and len(eng["gpu_passes"]) == 1
              and list(eng["gpu_passes"].values())[0] == {
                  "steps": 26, "cfg": 5.5, "sampler_name": "dpmpp_2m",
                  "scheduler": "karras", "denoise": 0.55})
        bi_src = (ROOT / "scripts" / "byrdimage.py").read_text(encoding="utf-8-sig")
        check("photo mode crop node accepts both FACE CROP and legacy IDENTITY MESH SEED",
              '"FACE CROP", "IDENTITY MESH SEED"' in bi_src)
        check("no_identity_mesh + explicit gpu_passes REPLACE recipe defaults (1 sampler safe)",
              "replace_passes" in bi_src)
        ipad_wf = json.loads((ROOT / "workflows" / "sd15_face_zone_ipadapter_api.json")
                             .read_text(encoding="utf-8-sig"))
        check("ipadapter workflow preset is exactly 'PLUS FACE (portraits)'",
              any(n.get("inputs", {}).get("preset") == "PLUS FACE (portraits)"
                  for n in ipad_wf.values() if isinstance(n, dict)))

        print("== stats + report + dashboard")
        st = api("/stats")
        check("stats counts artifacts", st["artifacts_total"] >= 4, str(st))
        rep = api("/reports/daily")
        check("daily report markdown", rep["markdown"].startswith("# ByrdHouse daily report"))
        with urllib.request.urlopen(f"http://127.0.0.1:{RP}/", timeout=10) as r:
            check("dashboard serves", r.status == 200 and b"ByrdHouse" in r.read())

    finally:
        router.terminate()

    print(f"\n{'ALL CHECKS PASSED' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    import urllib.error  # noqa: F401  (used in auth check)
    main()



