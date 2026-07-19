"""
ByrdHouse belt integration test â€” runs the ENTIRE pipeline with zero GPU:
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
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" â€” {detail}" if detail and not cond else ""))
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
    # â”€â”€ build an isolated root â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    for d in ("recipes", "workflows", "scripts", "router", "dashboard", "profiles", "configs", "docs"):
        shutil.copytree(REPO / d, ROOT / d)
    # Give the root a minimal .git so router/worker build_sha resolves exactly as
    # it does on the machines (both run from a git checkout). Only HEAD + refs are
    # needed â€” repo_build() never touches objects/.
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

        # Recipe slots are deduped â€” game-anchored templates repeat {game}
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

        hard_anime_recipe_path = ROOT / "recipes" / "anime_face_zone_hard_edit.v1.json"
        check("hard-anime split-authority recipe exists",
              hard_anime_recipe_path.is_file(), str(hard_anime_recipe_path))
        hard_anime_recipe = (
            json.loads(hard_anime_recipe_path.read_text(encoding="utf-8-sig"))
            if hard_anime_recipe_path.is_file() else {}
        )
        hard_anime_vegeta = (
            (hard_anime_recipe.get("target_presets") or {}).get("vegeta") or {}
        )
        check("Vegeta hard-anime recipe splits inner identity from full-head complexion authority",
              hard_anime_recipe.get("id") == "anime_face_zone_hard_edit"
              and hard_anime_recipe.get("runner") == "face_zone_identity_edit"
              and hard_anime_recipe.get("version") == 1
              and hard_anime_vegeta.get("gpu_mask_key") == "identity_mesh_warp_mask"
              and hard_anime_vegeta.get("mesh_geometry_fit") == "target-landmarks-core"
              and hard_anime_recipe.get("defaults", {}).get("min_mesh_coverage") == 0.70
              and hard_anime_vegeta.get("gpu_defaults", {}).get("denoise") == 0.26
              and hard_anime_vegeta.get("identity_strength") == 0.52
              and hard_anime_vegeta.get("identity_clip_strength") == 0.72,
              str(hard_anime_vegeta))
        hard_core_compositor_path = ROOT / "scripts" / "compose_hard_anime_core.py"
        hard_core_source = (
            hard_core_compositor_path.read_text(encoding="utf-8-sig")
            if hard_core_compositor_path.is_file() else ""
        )
        check("hard-anime bounded core compositor locks exterior and complexion",
              "identity_mesh_warp_mask" in hard_core_source
              and "outside_core_drift_pixels" in hard_core_source
              and "protected_feature_drift_pixels" in hard_core_source
              and "residual_pale_skin_pixels" in hard_core_source
              and "locked_baseline_edge_recall" in hard_core_source)
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
              and '"identity_mesh_seed"' in facezone_source
              and ('mesh_geometry_fit_mode == "target-landmarks"' in facezone_source
                   or 'mesh_geometry_fit_mode in {"target-landmarks", "target-landmarks-core"}' in facezone_source))
        check("byrdimage exposes the face-zone adapter",
              "def edit_face_zone(" in byrdimage_source
              and 'recipe.get("runner") != "face_zone_identity_edit"' in byrdimage_source
              and 'zone_script = root / "scripts" / "byrdfacezone.py"' in byrdimage_source)
        check("face-zone adapter applies target calibration before GPU resolution",
              "defaults.update(dict(preset_gpu_defaults))" in byrdimage_source
              and "def _resolve_face_zone_identity_weights(" in byrdimage_source
              and "identity, preset, engine, identity_strength" in byrdimage_source
              and 'zone_cmd += ["--mesh-geometry-fit", str(mesh_geometry_fit)]' in byrdimage_source)
        check("face-zone adapter supports validated identity-core GPU authority",
              '"identity_mesh_warp_mask"' in byrdimage_source
              and 'configured_gpu_mask_key' in byrdimage_source
              and 'full head reserved for CPU complexion' in byrdimage_source)
        check("face-zone composite restores protected target material after GPU cleanup",
              "restore_protected_material(" in facezone_source)
        check("face-zone composite pastes the GPU result into the final image",
              "original.paste(generated, (left, top), soft)" in facezone_source)
        check("face-zone final pass owns visible chin and neck handoff",
              '"final_chin_neck_touchup"' in facezone_source
              and '"last exported-image pass recolors neck without broad lower-jaw repaint"' in facezone_source
              and '"identity-detail-lock-only-no-broad-final-jaw-repaint"' in facezone_source
              and '"carey-tone-fill-sampled-from-generated-face"' in facezone_source)
        check("face-zone final reference/target audit is exported and warns on drift",
              "def _final_reference_target_recheck(" in facezone_source
              and "final_export_authority_mask" in facezone_source
              and "FINAL_REFERENCE_IDENTITY_RECHECK_LOW" in facezone_source
              and "reference_target_recheck.png" in facezone_source)
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
              production_identity.get("lora") == "carey_meina_sd15_expanded_hybrid_r32_20260714_125628-step00001200_hybrid_r32_1200_preview.safetensors"
              and isinstance(production_identity.get("strength"), (int, float))
              and isinstance(production_identity.get("clip_strength"), (int, float)),
              str(production_identity))
        # â”€â”€ The examiner (founder contract): before ANY edit the system must
        #    understand where it can and can't operate on THIS image â”€â”€
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
        check("Differential Diffusion receives the true soft outline ramp",
              'gpu_mask_key = "soft_mask" if uses_differential_diffusion else "graded_mask"'
              in byrdimage_source
              and '"differential_diffusion": uses_differential_diffusion' in byrdimage_source)
        check("quality lane is drivable by hand (facelab.ps1 + --edit-face-zone CLI)",
              "--edit-face-zone" in byrdimage_source
              and (ROOT / "scripts" / "facelab.ps1").is_file()
              and "quality" in (ROOT / "scripts" / "facelab.ps1").read_text(encoding="utf-8-sig"))
        check("face-zone adapter refuses an unconditioned production run",
              "face-zone edit requires an installed identity LoRA" in byrdimage_source
              and "selected_identity_lora = resolve_lora(" in byrdimage_source
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
        check("face-zone production recipe requires GPU cleanup",
              v2_recipe.get("defaults", {}).get("require_gpu_cleanup") is True
              and v2_recipe.get("defaults", {}).get("skip_gpu_cleanup") is False
              and "require_gpu_cleanup and skip_gpu_cleanup" in byrdimage_source
              and "CPU-only completion is forbidden" in byrdimage_source)
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
        v1_vegeta = (face_recipe.get("target_presets") or {}).get("vegeta") or {}
        v1_vegeta_defaults = dict(face_recipe.get("defaults") or {})
        v1_vegeta_defaults.update(dict(v1_vegeta.get("gpu_defaults") or {}))
        v1_vegeta_plan = byrdimage._resolve_face_zone_gpu_passes(
            {}, v1_vegeta_defaults, 7125
        )
        v1_identity_weights = byrdimage._resolve_face_zone_identity_weights(
            face_recipe.get("identity") or {}, v1_vegeta, {}, None
        )
        check("Vegeta v1 preset resolves the locked successful GPU calibration",
              list(v1_vegeta_plan) == ["default"]
              and v1_vegeta_plan["default"]["steps"] == 30
              and v1_vegeta_plan["default"]["cfg"] == 5.5
              and v1_vegeta_plan["default"]["denoise"] == 0.68
              and v1_identity_weights == (0.9, 1.0)
              and v1_vegeta.get("mesh_geometry_fit") == "target-landmarks",
              str({"plan": v1_vegeta_plan, "identity": v1_identity_weights}))
        v2_plan = byrdimage._resolve_face_zone_gpu_passes({}, v2_recipe["defaults"], 7132)
        check("v2 adapter resolves the two local GPU passes deterministically",
              list(v2_plan) == ["identity_fill", "line_harmonize"]
              and [entry["seed"] for entry in v2_plan.values()] == [7132, 7133]
              and [entry["steps"] for entry in v2_plan.values()] == [16, 8]
              and [entry["denoise"] for entry in v2_plan.values()] == [0.38, 0.12], str(v2_plan))
        try:
            byrdimage._resolve_face_zone_gpu_passes(
                {"gpu_passes": {"identity_fill": {"denoise": 0}}}, v2_recipe["defaults"], 7132
            )
        except SystemExit as exc:
            invalid_pass_rejected = "denoise" in str(exc)
        else:
            invalid_pass_rejected = False
        check("v2 adapter rejects an unsafe GPU-pass override", invalid_pass_rejected)

        # ─── HARD-ANIME MANUAL LANDMARK FALLBACK (luffy padded) ───
        # The padded Luffy target (1024x768) defeats the CPU face
        # detector (it returns false hat/forehead/ear boxes instead of
        # the central face).  The fix is a reviewed manual face box
        # plus an identity-template-to-manual-box mode that derives
        # the canonical target mesh from a clean Carey reference photo
        # rather than from the Luffy target.  These tests lock every
        # contract end to end and fail closed on regressions.
        v3_recipe_path = ROOT / "recipes" / "anime_face_zone_edit.v3.json"
        check("plug-and-play face-swap v3 recipe exists",
              v3_recipe_path.is_file(), str(v3_recipe_path))
        v3_recipe = (json.loads(v3_recipe_path.read_text(encoding="utf-8-sig"))
                     if v3_recipe_path.is_file() else {})
        v3_presets = v3_recipe.get("target_presets") or {}
        v3_luffy_close = v3_presets.get("luffy_close") or {}
        check("v3 luffy_close preset pins the reviewed manual face box",
              v3_luffy_close.get("manual_face_box") == {
                  "x": 145, "y": 185, "width": 735, "height": 465,
              }
              and v3_luffy_close.get("manual_landmark_mode")
              == "identity-template-to-manual-box"
              and v3_luffy_close.get("eye_source") == "target"
              and v3_luffy_close.get("eye_protection") == 1.0,
              str(v3_luffy_close))
        check("byrdfacezone implements the identity-template-to-manual-box mode",
              "def _map_identity_template_to_manual_box(" in facezone_source
              and "--manual-landmark-mode" in facezone_source
              and "\"identity-template-to-manual-box\"" in facezone_source
              and "manual_landmark_mode: str = \"ellipse-only\"" in facezone_source
              and "reviewed-manual-anime-template" in facezone_source
              and "manual_provenance" in facezone_source)
        check("manual mode fail-closed gates protect the Luffy target",
              "manual_face_box is outside the target" in facezone_source
              and "identity-template-to-manual-box requires a real identity reference image"
              in facezone_source
              and "identity reference mesh returned only" in facezone_source
              and "no identity reference supplied" in facezone_source)
        check("byrdimage forwards the manual landmark mode to the CPU script",
              "manual_landmark_mode" in byrdimage_source
              and "--manual-landmark-mode" in byrdimage_source
              and "identity-template-to-manual-box" in byrdimage_source
              and "engine.get(\"manual_face_box\") or preset.get(\"manual_face_box\")"
              in byrdimage_source)
        # Functional smoke: run the reviewed fallback on the actual
        # Luffy padded target and confirm the 478-point mesh seeds,
        # crop preflight passes, and the manual_provenance record is
        # exported for the audit trail.  We do not exercise the full
        # GPU composite here; that gate is locked separately.
        try:
            import byrdfacezone as _bz
            # The integration test root is an isolated snapshot; the
            # reviewed Luffy target and Carey identity photo live in
            # the source repo's Images/ + profiles/ trees.  Resolve
            # from REPO so the test is hermetic.
            _target_path = (REPO / "Images" / "Targets" / "anime_games"
                            / "luffy_face_padded.png")
            _identity_path = (REPO / "profiles" / "me" / "references"
                              / "generated_anime_cartoon" / "003_one-piece.png")
            if _target_path.is_file() and _identity_path.is_file():
                _record = _bz.prepare_face_zone(
                    REPO, _target_path, "luffy_padded_integration_test",
                    manual_box=(145.0, 185.0, 735.0, 465.0),
                    identity_reference=_identity_path,
                    eye_source_mode="target",
                    eye_protection_strength=1.0,
                    mesh_geometry_fit_mode="target-landmarks-core",
                    manual_landmark_mode="identity-template-to-manual-box",
                    absent_accessories=("eyeglasses", "earrings", "necklaces"),
                )
                _imp = _record.get("manual_provenance") or {}
                _mesh_stage = next(
                    (s for s in (_record.get("upload_analysis") or {}).get("stages", [])
                     if s.get("id") == "face-detection-and-478-point-mesh"),
                    {},
                )
                check("reviewed manual fallback produces 478 mapped landmarks",
                      _imp.get("mapped_landmark_count") == 478
                      and _record.get("detected_faces") == 1
                      and _record.get("manual_landmark_mode")
                      == "identity-template-to-manual-box"
                      and _record.get("detector_variant")
                      == "reviewed-manual-anime-template"
                      and _mesh_stage.get("mesh_points") == 478
                      and _mesh_stage.get("mesh_source")
                      == "reviewed-manual-anime-template"
                      and _mesh_stage.get("passed") is True,
                      str({"mapped": _imp.get("mapped_landmark_count"),
                           "variant": _record.get("detector_variant"),
                           "stage": _mesh_stage}))
                check("reviewed manual fallback passes the crop preflight",
                      (_record.get("crop_preflight") or {}).get("passed") is True
                      and ((_record.get("crop_preflight") or {})
                           .get("expandable_contacts") or []) == [],
                      str(_record.get("crop_preflight")))
                check("reviewed manual fallback records manual_provenance and target SHA",
                      _imp.get("target_sha256") is not None
                      and _imp.get("identity_reference_sha256") is not None
                      and _imp.get("identity_reference") is not None,
                      str({k: _imp.get(k) for k in
                           ("target_sha256", "identity_reference_sha256",
                            "identity_reference")}))
                # Fail-closed: missing identity reference must refuse,
                # not silently fall back to ellipse-only.
                try:
                    _bz.prepare_face_zone(
                        REPO, _target_path, "luffy_padded_fail_closed_ref",
                        manual_box=(145.0, 185.0, 735.0, 465.0),
                        identity_reference=None,
                        manual_landmark_mode="identity-template-to-manual-box",
                        absent_accessories=("eyeglasses", "earrings", "necklaces"),
                    )
                    _fail_closed_missing_ref = False
                except RuntimeError as _exc:
                    _fail_closed_missing_ref = (
                        "identity-template-to-manual-box" in str(_exc)
                        and "identity reference" in str(_exc).lower()
                    )
                check("manual mode fails closed when identity reference is missing",
                      _fail_closed_missing_ref, str(_fail_closed_missing_ref))
                # Fail-closed: manual box outside the target must refuse.
                try:
                    _bz.prepare_face_zone(
                        REPO, _target_path, "luffy_padded_fail_closed_box",
                        manual_box=(-50.0, -50.0, 200.0, 200.0),
                        identity_reference=_identity_path,
                        manual_landmark_mode="identity-template-to-manual-box",
                        absent_accessories=("eyeglasses", "earrings", "necklaces"),
                    )
                    _fail_closed_outside_box = False
                except RuntimeError as _exc:
                    _fail_closed_outside_box = "outside the target" in str(_exc)
                check("manual mode fails closed when box is outside the target",
                      _fail_closed_outside_box, str(_fail_closed_outside_box))
            else:
                check("reviewed manual fallback smoke (target + identity present)",
                      False,
                      f"missing target or identity: {_target_path} / {_identity_path}")
        except Exception as _exc:
            check("reviewed manual fallback runs without crashing", False, repr(_exc))
        check("byrdfacezone_manual_preview script exists and is importable",
              (REPO / "scripts" / "byrdfacezone_manual_preview.py").is_file()
              and "manual_preview.png" in (REPO / "scripts"
                                          / "byrdfacezone_manual_preview.py")
                                         .read_text(encoding="utf-8-sig"))

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
        (ckpt_dir / "Meina V5.1 - Baked VAE.safetensors").write_bytes(b"stub")
        resolved, matched = byrdimage.resolve_checkpoint_info(ROOT, "does-not-exist")
        check("unmatched checkpoint falls back AND flags it",
              resolved == "Meina V5.1 - Baked VAE.safetensors" and matched is False)
        _, matched2 = byrdimage.resolve_checkpoint_info(ROOT, "only installed")
        check("matched checkpoint resolves by loose name, no fallback flag", matched2 is True)
        check("recipe version pin honored",
              byrdimage.find_recipe(ROOT, "rpg_tier_list@1").name == "rpg_tier_list.v1.json")
        check("bare recipe name resolves to highest version",
              byrdimage.find_recipe(ROOT, "rpg_tier_list").name == "rpg_tier_list.v2.json")

        # â”€â”€ Regression: the dashboardâ†’recipe slot contract (yt_thumbnail v4) â”€â”€
        # job_19f525b23183s9na6 & siblings died twice with
        # "unfilled slots ['emotion']": the form let a required, non-vary slot
        # through empty. Lock every side of the contract with the EXACT recipe.
        yt = [r for r in api("/recipes") if r["file"] == "yt_thumbnail.v4.json"][0]
        yt_vary = set(yt["vary"])
        yt_required = [s for s in yt["slots"] if s not in yt_vary]
        # (1) /recipes exposes emotion as a required slot the form must render
        check("yt_thumbnail.v4 exposes emotion as a required (non-vary) slot",
              "emotion" in yt_required and "emotion" not in yt_vary)
        # (2) byrdimage rejects a generate that is missing a required slot â€”
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

        # â”€â”€ Uploaded source image: saved on the router, recorded at top grade,
        #    then composited onto by the worker (which fetches it back). This is
        #    the endpoint the operator model will call once its tools unlock. â”€â”€
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

        # â”€â”€ Belt-as-MCP: the bot's audited hands on the belt (byrd_belt_mcp) â”€â”€
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
        # autonomy ladder is literally a permission filter â€” no separate build
        belt.READONLY = True
        ro = {t["name"] for t in belt.handle(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/list"})["result"]["tools"]}
        blocked = belt.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                               "params": {"name": "queue_image", "arguments": {"prompt": "x"}}})
        check("read-only mode hides + blocks write tools (autonomy = a permission)",
              "queue_image" not in ro and "belt_status" in ro
              and blocked["result"]["isError"] is True)
        belt.READONLY = False

        # web_search: the in-app chat's research tool â€” config-driven, graceful
        sys.path.insert(0, str(ROOT / "router"))
        import router as router_mod
        ws = router_mod.run_chat_tool("web_search", {"query": "viral palworld thumbnail"}, "test")
        check("web_search reports clearly when unconfigured",
              isinstance(ws, dict) and "not configured" in ws.get("error", ""))

        # â”€â”€ IP-Adapter: reference-driven generation (the 'make it look like THIS
        #    game' engine). Reuse the uploaded source (src_id) as the reference. â”€â”€
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

        # â”€â”€ image.faceswap: ReActor face swap through the belt (Face Lab).
        #    The face auto-resolves from profiles/me/references exactly like the
        #    me-recipes; the target is an uploaded artifact fetched back. â”€â”€
        print("== image.faceswap (direct swap + anime style blend)")
        face_dir = ROOT / "profiles" / "me" / "references"
        face_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (256, 256), (200, 170, 150)).save(face_dir / "front.jpg")
        blend_target = ROOT / "artifacts" / "_sources" / "faceswap_blend_target.png"
        Image.new("RGB", (512, 512), (120, 100, 180)).save(blend_target)
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
            check("swap card records face source + target + reactor workflow",
                  "front" in Path(meta.get("face_source", "")).stem.lower()
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
        try:
            byrdimage.faceswap(ROOT, str(blend_target),
                               str(face_dir / "front.jpg"), "careyrpg", "blend miss",
                               style_blend=0.35, checkpoint="does-not-exist", dry_run=True)
            check("faceswap blend rejects a missing checkpoint loudly", False)
        except SystemExit as e:
            check("faceswap blend rejects a missing checkpoint loudly",
                  "requires its requested checkpoint" in str(e))

        # graph surgery is validated up front: a swapped/missing node pair must
        # die loudly, never quietly swap the wrong direction
        try:
            byrdimage.faceswap(ROOT, str(ROOT / "workflows" / "nope.png"),
                               str(face_dir / "front.jpg"), "careyrpg", "x")
            check("faceswap rejects a missing target loudly", False)
        except SystemExit as e:
            check("faceswap rejects a missing target loudly", "not found" in str(e))

        # zone route (the founder lane): a mask means the GPU edits ONLY inside
        # the approved zone â€” VAEEncodeForInpaint graph, identity from LoRA+prompt
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
        # redraws it as the founder â€” no hand mask, no face photo in payload
        api("/jobs", {"type": "image.faceswap", "project": "careyrpg",
                      "required_mode": "IMAGE", "required_caps": ["comfyui"],
                      "payload": {"target_artifact": src_id, "route": "auto",
                                  "prompt": "the same man as Vegeta, cel shading",
                                  "project": "careyrpg", "purpose": "auto route test"}})
        run_worker()
        autos = [a for a in api("/artifacts?limit=250") if a["kind"] == "image"
                 and json.loads(a["meta"] or "{}").get("recipe") in {"anime_face_zone_edit@1", "anime_face_zone_edit@3"}]
        check("auto route archived through the audited face-zone workflow", len(autos) == 1,
              str(len(autos)))
        if autos:
            am = json.loads(autos[0]["meta"])
            check("auto card records detector + corridor denoise + prompt",
                  am.get("detector", "").startswith("bbox/")
                  and am.get("denoise") == 0.7
                  and "face_zone" in am
                  and "Vegeta" in am.get("prompt", ""), str(am))

        # PREVIEW route (the CPU pre-step): detection only, archives the zone
        # overlay + the soft mask for approval â€” the GPU never decides the mask
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
            # the approved mask feeds the zone route by artifact id â€” the full
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

        # A retried job re-registers its artifacts â€” must upsert, not duplicate
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

        # PowerShell 5.1 writes status.json with a UTF-8 BOM â€” /status must tolerate it
        (ROOT / "status.json").write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"host": "TEST", "overall": "green", "checks": []}).encode())
        st = api("/status")
        check("/status reads BOM'd status.json", st["machine"].get("host") == "TEST")

        # â”€â”€ 2-PC coordination: the belt spans MINI (router) and GAMING (worker).
        #    These lock the machine-to-machine contract so a silent version split,
        #    a duplicate-work requeue, or an invisible upscale can't regress. â”€â”€
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

        # â”€â”€ ByrdCast Swap V0: self-contained target-image-first face swap â”€â”€
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



