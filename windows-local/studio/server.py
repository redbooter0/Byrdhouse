"""ByrdHouse Studio: local-only, stdlib image queue for a local ComfyUI server."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import mimetypes
import secrets
import shutil
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from identity_belt import BeltError, IdentityBelt
from reference_inputs import stage_reference, reverify_reference, ReferenceInputError
from wan22_workflow import ready as wan22_ready, PREVIEWS as VIDEO_PREVIEWS
from anime_continuity import ReviewInterrupted

HERE = Path(__file__).resolve().parent
ASPECTS = {"square": (1024, 1024), "portrait": (832, 1216), "landscape": (1216, 832)}
PRESETS = {
    "photo": "editorial photograph, natural light, realistic skin texture, sharp focus",
    "cinematic": "cinematic photograph, dramatic lighting, film still, detailed environment",
    "anime": "anime illustration, expressive character, clean linework, rich colors",
}
IDENTITY_GUARD = ("Black man, brown skin matching the reference photograph, dark brown eyes, "
                  "natural black afro hair, short beard and mustache")
NEGATIVE = ("white person, pale skin, bleached skin, different person, "
            "watermark, text, logo, blurry, malformed hands, extra fingers, low quality")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ValidationError(ValueError):
    pass


class BackendError(RuntimeError):
    pass


class ObservationPending(BackendError):
    """The submitted work is not known to have failed; keep its identity."""
    pass


def local_url(value):
    url = urllib.parse.urlsplit(value)
    if (url.scheme != "http" or url.hostname not in LOOPBACK or url.username
            or url.password or url.path not in ("", "/") or url.query or url.fragment):
        raise ValidationError("ComfyUI must be a local HTTP address with no path.")
    _ = url.port  # Validate malformed port syntax.
    return value.rstrip("/")


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    config["comfy_url"] = local_url(config["comfy_url"])
    if config.get("studio_host", "127.0.0.1") != "127.0.0.1":
        raise ValidationError("Studio binds to 127.0.0.1 only.")
    config["studio_host"] = "127.0.0.1"
    port = config.get("studio_port", 8787)
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValidationError("studio_port must be an integer between 1024 and 65535.")
    config["studio_port"] = port
    for key in ("checkpoint", "lightning_lora", "output_dir", "photo_dir"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValidationError(f"Missing configuration: {key}")
    config.setdefault("reference_dir", "training/carey/references")
    for key in ("output_dir", "photo_dir", "reference_dir"):
        target = Path(config[key])
        config[key] = str((path.parent / target).resolve() if not target.is_absolute() else target.resolve())
    if config.get("anime_canon_profile"):
        target = Path(config["anime_canon_profile"])
        config["anime_canon_profile"] = str(
            (path.parent / target).resolve() if not target.is_absolute() else target.resolve())
    return config


class LocalRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never follow a local backend redirect to another host or endpoint."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BackendError("The local ComfyUI server returned an unexpected redirect.")


class ComfyClient:
    def __init__(self, url, timeout=30):
        self.url = local_url(url)
        self.timeout = timeout
        # Ignore machine HTTP_PROXY settings: the image lane must remain local.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirectHandler())

    def request(self, endpoint, payload=None, binary=False):
        encoded = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.url + endpoint, data=encoded,
                                        headers={"Content-Type": "application/json"} if encoded else {})
        limit = 64 * 1024 * 1024 if binary else 16 * 1024 * 1024
        try:
            # ComfyUI can briefly block its HTTP loop while loading large models.
            # A submission must not be retried blindly after an ambiguous timeout.
            with self.opener.open(request, timeout=180 if endpoint == "/prompt" else self.timeout) as response:
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise BackendError("ComfyUI response exceeded the local size limit.")
                return raw if binary else json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read(1200).decode("utf-8", errors="replace")
            raise BackendError(f"ComfyUI returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendError(f"Cannot reach local ComfyUI: {exc}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BackendError("ComfyUI returned an invalid JSON response.") from exc

    def models(self):
        data = self.request("/object_info")
        def names(node, field):
            choices = data.get(node, {}).get("input", {}).get("required", {}).get(field, [[]])[0]
            return choices if isinstance(choices, list) else []
        return {"checkpoints": names("CheckpointLoaderSimple", "ckpt_name"),
                "loras": names("LoraLoader", "lora_name"),
                "diffusion_models": names("UNETLoader", "unet_name"),
                "text_encoders": names("CLIPLoader", "clip_name"),
                "vaes": names("VAELoader", "vae_name"),
                "ipadapter": names("IPAdapterModelLoader", "ipadapter_file"),
                "clip_vision": names("CLIPVisionLoader", "clip_name"),
                "pulid": names("PulidModelLoader", "pulid_file"),
                "controlnet": names("ControlNetLoader", "control_net_name"),
                "nodes": list(data)}


def build_graph(config, spec):
    if spec.get('operation') == 'mesh_cleanup':
        from mesh_cleanup import build
        return build(config, spec)
    if spec.get("engine") == "flux":
        return build_flux_graph(config, spec)
    model, clip = ["1", 0], ["1", 1]
    fast = spec["mode"] == "fast"
    fast_checkpoint = config.get("fast_checkpoint") if fast else None
    checkpoint = (config.get("anime_checkpoint") if spec.get("identity_mode") == "anime_anchor"
                  else fast_checkpoint or config["checkpoint"])
    graph = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}}}
    if spec["lora"] and spec["strength"] > 0:
        graph["2"] = {"class_type": "LoraLoader", "inputs": {
            "lora_name": spec["lora"], "strength_model": spec["strength"],
            "strength_clip": spec["strength"], "model": model, "clip": clip}}
        model, clip = ["2", 0], ["2", 1]
    if fast and not fast_checkpoint:
        graph["3"] = {"class_type": "LoraLoader", "inputs": {
            "lora_name": config["lightning_lora"], "strength_model": 1.0,
            "strength_clip": 0.0, "model": model, "clip": clip}}
        model, clip = ["3", 0], ["3", 1]
    width, height = ASPECTS[spec["aspect"]]
    photo_edit = spec.get("identity_mode") == "photo_edit"
    if spec.get("identity_mode") == "reference":
        graph.update({
            "10": {"class_type": "LoadImage", "inputs": {"image": spec["reference_image"]}},
            # Use the upstream FaceID example's loader: it pairs the actual
            # FaceID Plus V2 adapter with its required companion LoRA.
            "11": {"class_type": "IPAdapterUnifiedLoaderFaceID", "inputs": {
                "model": model, "preset": "FACEID PLUS V2",
                "lora_strength": 0.6, "provider": "CPU"}},
            "14": {"class_type": "IPAdapterFaceID", "inputs": {
                "model": ["11", 0], "ipadapter": ["11", 1], "image": ["10", 0],
                "weight": spec["reference_strength"],
                "weight_faceidv2": float(config.get("reference_faceidv2_weight", 1.5)),
                "weight_type": "linear", "combine_embeds": "average",
                "start_at": 0.0, "end_at": 0.95, "embeds_scaling": "V only"}},
        })
        model = ["14", 0]
    elif spec.get("identity_mode") == "instantid":
        # Official InstantID conditioning creates a new SDXL scene from the
        # owner-authorized reference. It never claims copied source pixels.
        graph.update({
            "10": {"class_type": "LoadImage", "inputs": {"image": spec["reference_image"]}},
            "11": {"class_type": "LoadInsightface", "inputs": {}},
            "12": {"class_type": "FaceEmbed", "inputs": {"insightface": ["11", 0], "face_image": ["10", 0]}},
            "13": {"class_type": "LoadInstantIdAdapter", "inputs": {"ipadapter": "ip-adapter.bin"}},
            "14": {"class_type": "FaceEmbedCombine", "inputs": {"resampler": ["13", 1], "face_embeds": ["12", 0]}},
            "15": {"class_type": "InstantIdAdapterApply", "inputs": {
                "model": model, "instantId_adapter": ["13", 0], "face_conditioning": ["14", 0],
                "strength": spec["reference_strength"]}},
        })
        model = ["15", 0]
    elif spec.get("identity_mode") == "pulid":
        # This is the locally validated Carey new-scene lane: three immutable
        # real-photo references provide identity while a separate real Carey
        # pose image drives Union OpenPose. It creates a new image, never a
        # source-pixel scene swap, so every output still requires review.
        refs = spec["pulid_reference_images"]
        graph.update({
            "10": {"class_type": "LoadImage", "inputs": {"image": refs[0]}},
            "11": {"class_type": "ImageScale", "inputs": {"image": ["10", 0], "upscale_method": "lanczos", "width": 512, "height": 512, "crop": "center"}},
            "12": {"class_type": "LoadImage", "inputs": {"image": refs[1]}},
            "13": {"class_type": "ImageScale", "inputs": {"image": ["12", 0], "upscale_method": "lanczos", "width": 512, "height": 512, "crop": "center"}},
            "14": {"class_type": "ImageBatch", "inputs": {"image1": ["11", 0], "image2": ["13", 0]}},
            "15": {"class_type": "LoadImage", "inputs": {"image": refs[2]}},
            "16": {"class_type": "ImageScale", "inputs": {"image": ["15", 0], "upscale_method": "lanczos", "width": 512, "height": 512, "crop": "center"}},
            "17": {"class_type": "ImageBatch", "inputs": {"image1": ["14", 0], "image2": ["16", 0]}},
            "18": {"class_type": "PulidModelLoader", "inputs": {"pulid_file": config.get("pulid_model", "pulid_v1.1.safetensors")}},
            "19": {"class_type": "PulidInsightFaceLoader", "inputs": {"provider": "CPU"}},
            "20": {"class_type": "PulidEvaClipLoader", "inputs": {}},
            "21": {"class_type": "ApplyPulidAdvanced", "inputs": {
                "model": model, "pulid": ["18", 0], "eva_clip": ["20", 0], "face_analysis": ["19", 0], "image": ["17", 0],
                "weight": float(config.get("pulid_weight", 1.0)), "projection": "ortho_v2", "fidelity": int(config.get("pulid_fidelity", 20)),
                "noise": 0.0, "start_at": 0.0, "end_at": 1.0}},
            "22": {"class_type": "LoadImage", "inputs": {"image": spec["pulid_pose_image"]}},
            "23": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": config.get("pulid_sdpose_checkpoint", "sdpose_wholebody_fp16.safetensors")}},
            "24": {"class_type": "SDPoseKeypointExtractor", "inputs": {"model": ["23", 0], "vae": ["23", 2], "image": ["22", 0], "batch_size": 1}},
            "25": {"class_type": "SDPoseDrawKeypoints", "inputs": {"keypoints": ["24", 0], "draw_body": True, "draw_hands": True, "draw_face": True, "draw_feet": False, "stick_width": 4, "face_point_size": 3, "score_threshold": 0.3, "draw_head": True}},
            "26": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": config.get("pulid_controlnet", "diffusion_pytorch_model.safetensors")}},
            "27": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["26", 0], "type": "openpose"}},
        })
        model = ["21", 0]
    elif spec.get("identity_mode") == "anime_anchor":
        # Existing CivitAI character-workflow pattern: an owner-approved
        # illustrated character anchor travels through IP-Adapter Plus Face,
        # while Union OpenPose controls the new shot. This stays in the SDXL
        # family and reuses installed upstream nodes.
        graph.update({
            "10": {"class_type": "LoadImage", "inputs": {"image": spec["reference_image"]}},
            "11": {"class_type": "IPAdapterUnifiedLoader", "inputs": {"model": model, "preset": "PLUS FACE (portraits)"}},
            "12": {"class_type": "IPAdapterAdvanced", "inputs": {
                "model": ["11", 0], "ipadapter": ["11", 1], "image": ["10", 0],
                "weight": float(config.get("anime_anchor_weight", 0.85)), "weight_type": "style transfer precise",
                "combine_embeds": "average", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "K+V"}},
            "13": {"class_type": "LoadImage", "inputs": {"image": spec["anime_pose_image"]}},
            "14": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": config.get("pulid_sdpose_checkpoint", "sdpose_wholebody_fp16.safetensors")}},
            "15": {"class_type": "SDPoseKeypointExtractor", "inputs": {"model": ["14", 0], "vae": ["14", 2], "image": ["13", 0], "batch_size": 1}},
            "16": {"class_type": "SDPoseDrawKeypoints", "inputs": {"keypoints": ["15", 0], "draw_body": True, "draw_hands": True, "draw_face": True, "draw_feet": False, "stick_width": 4, "face_point_size": 3, "score_threshold": 0.3, "draw_head": True}},
            "17": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": config.get("pulid_controlnet", "diffusion_pytorch_model.safetensors")}},
            "18": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["17", 0], "type": "openpose"}},
            # The upstream Apache-2.0 image-to-image workflow begins from the
            # supplied image latent.  Do the same for the locked anchor: it
            # preserves the approved face/hair design while the prompt and
            # controls are allowed to alter the scene gradually.
            "20": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}},
        })
        if spec.get("anime_scene_mode") == "civitai_new_scene_lab":
            # The staged CivitAI IP-Adapter + Union graph starts from empty
            # noise. Crop the approved head before IP-Adapter conditioning so
            # its white shirt does not become part of the identity reference.
            # The SDPose/Union branch remains the installed local replacement
            # for that graph's unavailable AIO line-art preprocessor.
            graph["21"] = {"class_type": "ImageCrop", "inputs": {
                "image": ["10", 0], "width": 832, "height": 832, "x": 0, "y": 0}}
            graph["12"]["inputs"]["image"] = ["21", 0]
            graph.pop("20")
        model = ["12", 0]
    negative = NEGATIVE + (", cartoon, illustration, painting, anime" if spec["preset"] != "anime" else "")
    latent_image = ["6", 0]
    if (spec.get("identity_mode") == "anime_anchor"
            and spec.get("anime_scene_mode") != "civitai_new_scene_lab"):
        latent_image = ["20", 0]
    if photo_edit:
        # Low denoise can still change facial geometry; only source-preserved
        # masked compositing has a protected-pixel equality check.
        graph.update({
            "10": {"class_type": "LoadImage", "inputs": {"image": spec["reference_image"]}},
            "11": {"class_type": "ImageScale", "inputs": {
                "image": ["10", 0], "upscale_method": "lanczos", "width": width,
                "height": height, "crop": "center"}},
            "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["1", 2]}},
        })
        latent_image = ["12", 0]
    graph.update({
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["full_prompt"], "clip": clip}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": clip}},
        "6": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "seed": spec["seed"], "steps": int(config.get("pulid_steps", 8)) if spec.get("identity_mode") == "pulid" else int(config.get("anime_steps", 30)) if spec.get("identity_mode") == "anime_anchor" else 5 if fast_checkpoint else 4 if fast else 24,
            "cfg": float(config.get("pulid_cfg", 2.0)) if spec.get("identity_mode") == "pulid" else float(config.get("anime_cfg", 4.0)) if spec.get("identity_mode") == "anime_anchor" else 1.5 if fast_checkpoint else 1.0 if fast else 6.0,
            "sampler_name": "dpmpp_2m" if spec.get("identity_mode") == "anime_anchor" else "dpmpp_sde" if fast_checkpoint else "euler" if fast else "dpmpp_2m",
            "scheduler": "karras" if spec.get("identity_mode") == "anime_anchor" or fast_checkpoint else "sgm_uniform" if fast else "karras",
            "denoise": (spec.get("denoise", 1.0) if photo_edit
                        else 1.0 if spec.get("anime_scene_mode") == "civitai_new_scene_lab"
                        else float(config.get("anime_img2img_denoise", 0.38)) if spec.get("identity_mode") == "anime_anchor"
                        else 1.0),
            "model": model, "positive": ["28", 0] if spec.get("identity_mode") == "pulid" else ["19", 0] if spec.get("identity_mode") == "anime_anchor" else ["4", 0], "negative": ["28", 1] if spec.get("identity_mode") == "pulid" else ["19", 1] if spec.get("identity_mode") == "anime_anchor" else ["5", 0], "latent_image": latent_image}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ByrdHouse/" + spec["id"], "images": ["8", 0]}},
    })
    if spec.get("identity_mode") == "pulid":
        graph["28"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": ["4", 0], "negative": ["5", 0], "control_net": ["27", 0], "image": ["25", 0],
            "strength": float(config.get("pulid_control_strength", 0.55)), "start_percent": 0.0, "end_percent": 1.0}}
    if spec.get("identity_mode") == "anime_anchor":
        graph["19"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": ["4", 0], "negative": ["5", 0], "control_net": ["18", 0], "image": ["16", 0],
            "strength": float(config.get("anime_control_strength", 0.65)), "start_percent": 0.0, "end_percent": 0.65}}
        # Adapt the already-staged AnimeFix workflow's conservative
        # FaceDetailer stage.  These nodes are installed locally (Impact Pack,
        # its YOLO face detector, and SAM); a localized low-denoise pass gives
        # the approved illustrated face a fair chance before the read-only
        # belt judges it.  It never supplies a different identity reference or
        # auto-approves the result.
        if config.get("anime_face_detailer", False):
            graph.update({
            "30": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face_yolov8m.pt"}},
            "31": {"class_type": "SAMLoader", "inputs": {"model_name": "sam_vit_b_01ec64.pth", "device_mode": "AUTO"}},
            "32": {"class_type": "ToDetailerPipe", "inputs": {
                "model": ["12", 0], "clip": clip, "vae": ["1", 2],
                "positive": ["19", 0], "negative": ["19", 1],
                "bbox_detector": ["30", 0], "sam_model_opt": ["31", 0],
                "wildcard": "", "Select to add LoRA": "Select the LoRA to add to the text",
                "Select to add Wildcard": "Select the Wildcard to add to the text"}},
            "33": {"class_type": "FaceDetailerPipe", "inputs": {
                "image": ["8", 0], "detailer_pipe": ["32", 0],
                "guide_size": 768, "guide_size_for": True, "max_size": 1024,
                "seed": spec["seed"], "steps": 20, "cfg": 3.5,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 0.22,
                "feather": 10, "noise_mask": True, "force_inpaint": True,
                "bbox_threshold": 0.3, "bbox_dilation": 10, "bbox_crop_factor": 1.8,
                "sam_detection_hint": "center-1", "sam_dilation": 0,
                "sam_threshold": 0.93, "sam_bbox_expansion": 0,
                "sam_mask_hint_threshold": 0.7, "sam_mask_hint_use_negative": "False",
                "drop_size": 10, "refiner_ratio": 0.2, "cycle": 1}},
            })
            graph["9"]["inputs"]["images"] = ["33", 0]
    return graph


def build_flux_graph(config, spec):
    """Native four-step FLUX.2 Klein editing, with Carey's actual photo latent."""
    width, height = ASPECTS[spec["aspect"]]
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": config["flux_model"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": config["flux_text_encoder"], "type": "flux2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": config["flux_vae"]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["full_prompt"], "clip": ["2", 0]}},
        "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "7": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["14", 0], "guider": ["13", 0], "sampler": ["15", 0], "sigmas": ["16", 0], "latent_image": ["6", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ByrdHouse/" + spec["id"], "images": ["8", 0]}},
        "10": {"class_type": "LoadImage", "inputs": {"image": spec["reference_image"]}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["3", 0]}},
        "12": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["4", 0], "latent": ["11", 0]}},
        "13": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["12", 0]}},
        "14": {"class_type": "RandomNoise", "inputs": {"noise_seed": spec["seed"]}},
        "15": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "16": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": width, "height": height}},
    }


class Studio:
    def __init__(self, config, data_dir=HERE, client=None, start_worker=True):
        self.config = config
        self.client = client or ComfyClient(config["comfy_url"])
        self.output_dir = Path(config["output_dir"]).resolve()
        self.photo_dir = Path(config["photo_dir"]).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.reference_dir = Path(config.get("reference_dir", self.photo_dir.parent / "references")).resolve()
        self.references = {}
        manifest = self.reference_dir / "manifest.json"
        if manifest.is_file():
            self.references = {row["id"]: row for row in json.loads(manifest.read_text(encoding="utf-8"))["references"]}
        recipe_file = HERE / "carey-recipes.json"
        self.recipes = json.loads(recipe_file.read_text(encoding="utf-8"))["recipes"] if recipe_file.is_file() else {}
        self.db_path = Path(data_dir) / "jobs.sqlite3"
        self.submission_dir = Path(data_dir) / "submissions"
        self.submission_dir.mkdir(parents=True, exist_ok=True)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.models_lock = threading.Lock()
        self.cached_models = None
        self.models_checked = 0.0
        self.identity_belt = None
        self.execution_lock = threading.Lock()
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, state TEXT NOT NULL, created TEXT NOT NULL,
                started TEXT, finished TEXT, spec TEXT NOT NULL, outputs TEXT NOT NULL DEFAULT '[]',
                error TEXT, seconds REAL, prompt_id TEXT)""")
            for row in db.execute("SELECT * FROM jobs WHERE state='running'").fetchall():
                if json.loads(row['spec']).get('operation') == 'anime_review':
                    db.execute("UPDATE jobs SET state='queued', error=NULL WHERE id=?", (row['id'],))
                    continue
                prompt_id = row['prompt_id'] or self.saved_prompt_id(json.loads(row['spec']))
                if prompt_id:
                    db.execute("UPDATE jobs SET state='recovering', prompt_id=?, error=? WHERE id=?",
                               (prompt_id, 'Reconnecting to the existing ComfyUI submission.', row['id']))
                else:
                    db.execute("UPDATE jobs SET state='failed', error=?, finished=? WHERE id=?",
                               ('Interrupted without a recorded submission ID. Inspect ComfyUI before retrying; no automatic resubmission.',
                                utcnow(), row['id']))
        self.thread = None
        if start_worker:
            self.thread = threading.Thread(target=self.work, daemon=True, name="studio-image-worker")
            self.thread.start()

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def models(self, force=False):
        with self.models_lock:
            if not force and self.cached_models and time.monotonic() - self.models_checked < 10:
                return self.cached_models
            try:
                found = self.client.models()
                result = {**found, "connected": True, "error": None}
            except Exception as exc:
                result = {"checkpoints": [], "loras": [], "connected": False, "error": str(exc)}
            self.cached_models, self.models_checked = result, time.monotonic()
            return result

    def state(self):
        models = self.models()
        identity = [name for name in models["loras"] if name != self.config["lightning_lora"]
                    and not any(word in name.lower() for word in ("lightning", "lcm", "hyper-sd", "hypersd"))]
        photo_count = sum(1 for path in self.photo_dir.iterdir()
                          if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
        base_ready = self.config["checkpoint"] in models["checkpoints"]
        fast_ready = (self.config["fast_checkpoint"] in models["checkpoints"] if self.config.get("fast_checkpoint")
                      else self.config["lightning_lora"] in models["loras"])
        reference_ready = ("IPAdapterFaceID" in models.get("nodes", [])
                           and "IPAdapterUnifiedLoaderFaceID" in models.get("nodes", [])
                           and "ip-adapter-faceid-plusv2_sdxl_lora.safetensors" in models.get("loras", [])
                           and self.config.get("ipadapter_model") in models.get("ipadapter", [])
                           and self.config.get("clip_vision_model") in models.get("clip_vision", [])
                           and bool(self.references))
        instantid_ready = (base_ready and "ip-adapter.bin" in models.get("ipadapter", [])
                           and {"LoadInsightface", "FaceEmbed", "LoadInstantIdAdapter", "FaceEmbedCombine", "InstantIdAdapterApply"}.issubset(models.get("nodes", []))
                           and bool(self.references))
        pulid_reference_ids = self.config.get("pulid_reference_ids", ["neutral", "smile", "night"])
        pulid_pose = self.config.get("pulid_pose", {})
        pulid_ready = (fast_ready
                       and self.config.get("pulid_model", "pulid_v1.1.safetensors") in models.get("pulid", [])
                       and self.config.get("pulid_controlnet", "diffusion_pytorch_model.safetensors") in models.get("controlnet", [])
                       and self.config.get("pulid_sdpose_checkpoint", "sdpose_wholebody_fp16.safetensors") in models.get("checkpoints", [])
                       and {"PulidModelLoader", "PulidInsightFaceLoader", "PulidEvaClipLoader", "ApplyPulidAdvanced",
                            "SDPoseKeypointExtractor", "SDPoseDrawKeypoints", "SetUnionControlNetType", "ControlNetApplyAdvanced"}.issubset(models.get("nodes", []))
                       and isinstance(pulid_reference_ids, list) and len(pulid_reference_ids) == 3
                       and all(isinstance(ref, str) and ref in self.references and not self.references[ref].get("generated", False)
                               for ref in pulid_reference_ids)
                       and isinstance(pulid_pose, dict) and isinstance(pulid_pose.get("id"), str)
                       and isinstance(pulid_pose.get("source"), str) and isinstance(pulid_pose.get("source_sha256"), str))
        anime_reference = self.config.get("anime_reference_id", "carey-anime-anchor")
        anime_ready = (self.config.get("anime_checkpoint") in models.get("checkpoints", [])
                       and self.config.get("anime_ipadapter_model", "ip-adapter-plus-face_sdxl_vit-h.safetensors") in models.get("ipadapter", [])
                       and self.config.get("pulid_controlnet", "diffusion_pytorch_model.safetensors") in models.get("controlnet", [])
                       and self.config.get("pulid_sdpose_checkpoint", "sdpose_wholebody_fp16.safetensors") in models.get("checkpoints", [])
                       and {"IPAdapterUnifiedLoader", "IPAdapterAdvanced", "SDPoseKeypointExtractor", "SDPoseDrawKeypoints", "SetUnionControlNetType", "ControlNetApplyAdvanced"}.issubset(models.get("nodes", []))
                       and anime_reference in self.references and self.references[anime_reference].get("generated", False)
                       and isinstance(pulid_pose, dict) and isinstance(pulid_pose.get("source"), str))
        flux_ready = (self.config.get("flux_model") in models.get("diffusion_models", [])
                      and self.config.get("flux_text_encoder") in models.get("text_encoders", [])
                      and self.config.get("flux_vae") in models.get("vaes", [])
                      and {"ReferenceLatent", "Flux2Scheduler", "EmptyFlux2LatentImage", "BasicGuider", "SamplerCustomAdvanced"}.issubset(models.get("nodes", []))
                      and bool(self.references))
        belt_models = {"ReActorFaceSwap", "ReActorMaskHelper", "UltralyticsDetectorProvider", "SAMLoader"}
        belt_ready = (models["connected"] and belt_models.issubset(set(models.get("nodes", [])))
                      and (self.config.get("comfy_dir") and
                           (Path(self.config["comfy_dir"]) / "models" / "insightface" / "inswapper_128.onnx").is_file())
                      and (Path(self.config.get("comfy_dir", "")) / "models" / "sams" / "sam_vit_b_01ec64.pth").is_file())
        training = {}
        status_path = self.photo_dir.parent / "candidate-v1" / "status.json"
        try:
            training = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        return {"comfy_url": self.config["comfy_url"], "connected": models["connected"],
                "error": models["error"], "checkpoint": self.config["checkpoint"],
                "base_ready": base_ready, "fast_ready": base_ready and fast_ready,
                "loras": identity, "photo_count": photo_count, "photo_dir": str(self.photo_dir),
                "output_dir": str(self.output_dir), "training_state": training.get("state", "not_configured"),
                "training": training,
                "identity_lora": self.config.get("identity_lora", ""),
                "default_lora_strength": self.config.get("identity_lora_strength", 0.65),
                "identity_trigger": self.config.get("identity_trigger", "byrdcarey man"),
                "default_identity_mode": self.config.get("identity_mode", "lora"),
                "default_mode": self.config.get("default_mode", "quality"),
                "default_reference": self.config.get("default_reference", "neutral"),
                "default_reference_strength": self.config.get("reference_strength", 0.72),
                "fast_checkpoint": self.config.get("fast_checkpoint"),
                "reference_ready": reference_ready,
                "instantid_ready": instantid_ready,
                "pulid_ready": pulid_ready,
                "anime_ready": anime_ready,
                "wan22_ready": wan22_ready(self.config, models),
                "flux_ready": flux_ready, "default_engine": self.config.get("default_engine", "sdxl"),
                "belt_ready": belt_ready,
                "belt_components": sorted(belt_models),
                "source_mask_ready": {"FaceParse(FaceParsing)", "FaceParsingModelLoaderNew", "ImageCompositeMasked", "VAEEncodeForInpaint", "LoadBackgroundRemovalModel", "RemoveBackground"}.issubset(models.get('nodes', [])),
                "require_carey_reference": self.config.get("require_carey_reference", False),
                "references": [{"id": row["id"], "label": row["label"], "image": "/references/" + row["id"]} for row in self.references.values()],
                "recipes": [{"id": key, "title": row["title"], "description": row["description"], "count": len(row["variations"])} for key, row in self.recipes.items()],
                "identity_note": "Carey trigger is included automatically. Compare each candidate with your reference before keeping it."}

    def create_job(self, payload):
        spec = self.make_spec(payload)
        self.enqueue([spec])
        return self.job(spec["id"])

    def make_spec(self, payload):
        if not isinstance(payload, dict):
            raise ValidationError("Request must be a JSON object.")
        allowed = {"prompt", "preset", "mode", "aspect", "lora", "strength", "seed", "identity_mode", "reference", "reference_strength", "denoise", "engine", "anime_scene_mode"}
        if set(payload) - allowed:
            raise ValidationError("Request contains unsupported fields.")
        prompt = payload.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 3000:
            raise ValidationError("Enter a prompt between 1 and 3,000 characters.")
        preset, mode, aspect = payload.get("preset", "photo"), payload.get("mode", self.config.get("default_mode", "quality")), payload.get("aspect", "portrait")
        if preset not in PRESETS or mode not in ("fast", "quality") or aspect not in ASPECTS:
            raise ValidationError("Choose one of the supplied presets, speeds, and image shapes.")
        engine = payload.get("engine", self.config.get("default_engine", "sdxl"))
        if engine not in ("sdxl", "flux"):
            raise ValidationError("Choose an installed image engine.")
        strength = payload.get("strength", self.config.get("identity_lora_strength", 0.65))
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= 1.5:
            raise ValidationError("LoRA strength must be a number from 0 to 1.5.")
        seed = payload.get("seed")
        if seed in (None, ""):
            seed = secrets.randbits(63)
        elif isinstance(seed, str) and seed.isascii() and seed.isdigit() and len(seed) <= 19:
            seed = int(seed)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 9223372036854775807:
            raise ValidationError("Seed must be an integer from 0 to 9223372036854775807, or blank for random.")
        lora = payload.get("lora") or self.config.get("identity_lora", "")
        if not isinstance(lora, str) or len(lora) > 255:
            raise ValidationError("Invalid SDXL LoRA selection.")
        identity_mode = payload.get("identity_mode", self.config.get("identity_mode", "lora"))
        if identity_mode not in ("lora", "reference", "instantid", "pulid", "anime_anchor", "photo_edit"):
            raise ValidationError("Choose a supported local Carey identity method.")
        anime_scene_mode = payload.get("anime_scene_mode", "source_likeness")
        if anime_scene_mode not in ("source_likeness", "civitai_new_scene_lab"):
            raise ValidationError("Choose a supported Carey anime scene mode.")
        if identity_mode != "anime_anchor" and "anime_scene_mode" in payload:
            raise ValidationError("Anime scene mode requires the approved anime identity method.")
        if anime_scene_mode == "civitai_new_scene_lab" and engine != "sdxl":
            raise ValidationError("The CivitAI anime scene lab requires the installed SDXL engine.")
        denoise = payload.get("denoise", 0.45)
        if (isinstance(denoise, bool) or not isinstance(denoise, (int, float))
                or not math.isfinite(denoise) or not 0.15 <= denoise <= 0.6):
            raise ValidationError("Photo edit strength must be between 0.15 and 0.60.")
        if identity_mode in ("photo_edit", "instantid"):
            mode, lora, strength = "quality", "", 0.0
        elif identity_mode == "pulid":
            # RealVisXL Lightning is the benchmark base; this lane supplies
            # its own eight-step sampler settings in build_graph.
            mode, lora, strength = "fast", "", 0.0
        elif identity_mode == "anime_anchor":
            mode, lora, strength = "quality", "", 0.0
        models = self.models()
        if not models["connected"]:
            raise ValidationError(models["error"] or "Local ComfyUI is offline.")
        if engine == "flux" and not self.state()["flux_ready"]:
            raise ValidationError("The local FLUX photo-editing models are not installed yet. Choose SDXL.")
        if engine == "sdxl" and self.config["checkpoint"] not in models["checkpoints"]:
            raise ValidationError("The configured SDXL checkpoint is not installed yet.")
        if engine == "sdxl" and mode == "fast" and not self.state()["fast_ready"]:
            raise ValidationError("The fast generation model is not installed yet. Choose Quality.")
        if engine == "sdxl" and lora and (lora not in models["loras"] or any(w in lora.lower() for w in ("lightning", "lcm", "hyper-sd", "hypersd"))):
            raise ValidationError("Select an installed SDXL identity or style LoRA from the list.")
        if engine == "flux":
            identity_mode, mode, lora, strength = "reference", "fast", "", 0.0
        elif self.config.get("require_carey_reference") and identity_mode not in ("reference", "instantid", "pulid", "anime_anchor", "photo_edit"):
            raise ValidationError("Carey generation requires your photo reference. Choose Exact photo edit or photo guidance.")
        reference_strength = payload.get("reference_strength", self.config.get("reference_strength", 0.72))
        if (isinstance(reference_strength, bool) or not isinstance(reference_strength, (int, float))
                or not math.isfinite(reference_strength) or not 0 <= reference_strength <= 1.5):
            raise ValidationError("Reference strength must be between 0 and 1.5.")
        reference = payload.get("reference", self.config.get("default_reference", "neutral"))
        if not isinstance(reference, str):
            raise ValidationError("Select a local Carey reference.")
        if identity_mode in ("reference", "instantid", "pulid", "anime_anchor", "photo_edit"):
            if engine == "sdxl" and not self.state()["reference_ready"]:
                if identity_mode == "reference":
                    raise ValidationError("Photo reference models are unavailable. Choose Carey LoRA or finish installing the reference models.")
            if identity_mode == "instantid" and not self.state()["instantid_ready"]:
                raise ValidationError("InstantID’s local private benchmark components are unavailable.")
            if identity_mode == "pulid" and not self.state()["pulid_ready"]:
                raise ValidationError("The validated PuLID + pose components are unavailable locally.")
            if identity_mode == "anime_anchor" and not self.state()["anime_ready"]:
                raise ValidationError("The approved anime-anchor model or its existing pose/reference components are unavailable locally.")
            if reference not in self.references:
                raise ValidationError("Select an installed Carey reference.")
        trigger = self.config.get("identity_trigger", "byrdcarey man") if lora and strength > 0 else ""
        # The trigger is first, before scene text, and never consumes the user's
        # input. Prompt text alone is not considered proof of identity.
        prefix = f"photo of {trigger}, {IDENTITY_GUARD}" if trigger else IDENTITY_GUARD
        if preset == "anime":
            prefix = f"anime illustration of {trigger}, {IDENTITY_GUARD}"
        full_prompt = f"{prefix}, {prompt.strip()}, {PRESETS[preset]}"
        if identity_mode == "photo_edit":
            full_prompt = ("Edit the same Carey in the reference photo. Preserve his exact facial geometry, eyes, nose, lips, beard, afro, brown skin tone, and proportions. "
                           f"Change only the requested scene, clothing, expression, and lighting. {prompt.strip()}. {PRESETS[preset]}. One person, no text or watermark.")
        if engine == "flux":
            full_prompt = ("Create a new image of the SAME man in the reference photo. He is Carey, a Black man. "
                           "Preserve his exact facial features, brown skin tone, natural afro, and beard. "
                           "Change only the requested expression, pose, clothing, setting, and art style. "
                           f"{prompt.strip()}. {PRESETS[preset]}. One Carey, no text or watermark.")
        job_id = secrets.token_hex(16)
        spec = {"id": job_id, "prompt": prompt.strip(), "preset": preset, "mode": mode,
                "aspect": aspect, "engine": engine, "lora": lora, "strength": float(strength), "seed": seed,
                "identity_mode": identity_mode, "reference": reference if identity_mode in ("reference", "instantid", "pulid", "anime_anchor", "photo_edit") else None,
                "anime_scene_mode": anime_scene_mode if identity_mode == "anime_anchor" else None,
                "reference_strength": reference_strength, "denoise": float(denoise),
                "full_prompt": full_prompt}
        if identity_mode in ("reference", "instantid", "photo_edit"):
            source = self.references[reference]
            try:
                snapshot = stage_reference(self.config, source, job_id)
            except ReferenceInputError as exc:
                raise ValidationError(str(exc)) from exc
            spec.update(reference_image=snapshot['comfy_image'], reference_snapshot=snapshot,
                        reference_source_sha256=source.get('source_sha256'),
                        reference_input_sha256=snapshot['staged_png_sha256'])
        elif identity_mode == "anime_anchor":
            # The selected reference controls only this shot's framing/pose.
            # The character identity stays bound to the locked illustrated
            # anchor below.  This lets the anchor itself make a close canonical
            # portrait before we ask a tiny full-body face to carry a scene.
            pose_reference = reference
            reference = self.config.get("anime_reference_id", "carey-anime-anchor")
            try:
                snapshot = stage_reference(self.config, self.references[reference], job_id)
                pose_snapshot = stage_reference(self.config, self.references[pose_reference],
                    hashlib.sha256(f"{job_id}:anime:pose".encode()).hexdigest()[:32])
            except (ReferenceInputError, KeyError) as exc:
                raise ValidationError(f"Cannot freeze the Carey anime anchor or pose source: {exc}") from exc
            full_prompt = ("anime illustration of Carey, Black man, rich medium-brown skin, large irregular natural black afro, high forehead, thick dark eyebrows, warm almond-shaped brown eyes, narrow rounded nose, short mustache and connected jaw beard, left-ear silver stud, clean dark ink linework, warm cel shading, consistent original animated character design, "
                           f"{prompt.strip()}, masterpiece, high quality, detailed background, no text, no watermark")
            spec.update(reference=reference, anime_pose_reference=pose_reference, full_prompt=full_prompt, reference_image=snapshot['comfy_image'],
                        reference_snapshot=snapshot, anime_pose_snapshot=pose_snapshot,
                        anime_pose_image=pose_snapshot['comfy_image'])
        elif identity_mode == "pulid":
            # Each image is pinned in its own immutable snapshot directory. The
            # reference selector remains a review aid; the tested three-photo
            # board is deliberately fixed so an arbitrary selection cannot
            # weaken identity conditioning after a job is queued.
            reference_ids = self.config.get("pulid_reference_ids", ["neutral", "smile", "night"])
            pose = self.config.get("pulid_pose", {})
            try:
                snapshots = [stage_reference(self.config, self.references[ref_id],
                             hashlib.sha256(f"{job_id}:pulid:{ref_id}".encode()).hexdigest()[:32])
                             for ref_id in reference_ids]
                pose_snapshot = stage_reference(self.config, pose,
                    hashlib.sha256(f"{job_id}:pulid:pose".encode()).hexdigest()[:32], use_original=True)
            except (ReferenceInputError, KeyError) as exc:
                raise ValidationError(f"Cannot freeze the Carey PuLID reference board: {exc}") from exc
            spec.update(reference=reference_ids[0], pulid_reference_ids=reference_ids,
                        pulid_reference_snapshots=snapshots,
                        pulid_reference_images=[snapshot['comfy_image'] for snapshot in snapshots],
                        pulid_pose_snapshot=pose_snapshot, pulid_pose_image=pose_snapshot['comfy_image'])
        return spec

    def enqueue(self, specs):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running','recovering')").fetchone()[0]
            if count + len(specs) > 64:
                raise ValidationError("The local queue is full. Wait for a few images to finish.")
            db.executemany("INSERT INTO jobs(id,state,created,spec) VALUES(?,?,?,?)",
                          [(spec["id"], "queued", utcnow(), json.dumps(spec)) for spec in specs])
        self.wake.set()

    def create_source_mask(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'reference', 'region'}:
            raise ValidationError('Photo analysis accepts a reference and background or clothing region.')
        reference = payload.get('reference', self.config.get('default_reference'))
        region = payload.get('region', 'background')
        if not isinstance(reference, str) or reference not in self.references or region not in ('background', 'clothing'):
            raise ValidationError('Choose an original photo and background or clothing region.')
        anime_anchor = reference == self.config.get('anime_reference_id', 'carey-anime-anchor')
        if self.references[reference].get('generated', False) and not anime_anchor:
            raise ValidationError('Scene preservation accepts an original photo or the locked Carey Anime Canon Anchor only.')
        if not self.state()['source_mask_ready']:
            raise ValidationError('Installed semantic parsing, BiRefNet matting, or masked-edit nodes are unavailable.')
        job_id = secrets.token_hex(16)
        try:
            snapshot = stage_reference(self.config, self.references[reference], job_id,
                                       use_original=not anime_anchor)
        except ReferenceInputError as exc:
            raise ValidationError(str(exc)) from exc
        if snapshot['width'] % 8 or snapshot['height'] % 8:
            raise ValidationError('This source-preservation preset requires native dimensions divisible by 8; choose the original portrait.')
        spec = {'id': job_id, 'operation': 'source_mask', 'reference': reference,
                'reference_snapshot': snapshot, 'region': region, 'seed': 0, 'engine': 'face_parser',
                'prompt': ('Carey Anime Canon protection mask · ' if anime_anchor else 'Carey photo protection mask · ') + region,
                'identity_mode': 'anime_source_preserve' if anime_anchor else 'source_preserve',
                'anime_anchor_scene': anime_anchor}
        self.enqueue([spec])
        return self.job(job_id)

    def create_source_edit(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'mask_job_id', 'prompt', 'seed'}:
            raise ValidationError('Scene editing accepts a reviewed mask, scene direction and optional seed.')
        mask_id = payload.get('mask_job_id')
        if not isinstance(mask_id, str) or len(mask_id) != 32 or any(c not in '0123456789abcdef' for c in mask_id):
            raise ValidationError('Choose a reviewed protection mask.')
        parent = self.job(mask_id)
        if not parent or parent.get('operation') != 'source_mask' or parent['state'] != 'approved':
            raise ValidationError('Inspect and accept the protection mask before scene editing.')
        prompt = payload.get('prompt', '')
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 3000:
            raise ValidationError('Enter scene direction between 1 and 3,000 characters.')
        seed = payload.get('seed')
        if seed in (None, ''): seed = secrets.randbits(63)
        elif isinstance(seed, str) and seed.isascii() and seed.isdigit() and len(seed) <= 19: seed = int(seed)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 9223372036854775807:
            raise ValidationError('Choose a valid seed or leave it blank.')
        anime_anchor_scene = bool(parent.get('anime_anchor_scene'))
        checkpoint = self.config.get('anime_checkpoint') if anime_anchor_scene else self.config.get('fast_checkpoint')
        if not checkpoint or checkpoint not in self.models()['checkpoints']:
            raise ValidationError('The qualified illustrated or photoreal scene-edit checkpoint is unavailable.')
        from source_preserve import checked_masks, SourceError
        card = self.metadata(mask_id)
        if card.get('review_state') != 'approved' or not isinstance(card.get('reviewed'), str) or not card['reviewed']:
            raise ValidationError('Protection mask review metadata is missing; inspect and accept the mask again.')
        job_id = secrets.token_hex(16)
        spec = {'id': job_id, 'operation': 'source_preserve', 'mask_job_id': mask_id,
                'reference': parent['reference'], 'reference_snapshot': parent['reference_snapshot'],
                'region': parent['region'], 'mask_hashes': card['inspection']['mask_hashes'],
                'mask_reviewed': card.get('reviewed'), 'prompt': prompt.strip(), 'seed': seed,
                'engine': 'sdxl', 'identity_mode': 'anime_source_preserve' if anime_anchor_scene else 'source_preserve',
                'anime_anchor_scene': anime_anchor_scene, 'checkpoint': checkpoint,
                'matte_edge_shrink_pixels': -8 if anime_anchor_scene else -2,
                'steps': int(self.config.get('anime_steps', 30)) if anime_anchor_scene else 5,
                'cfg': float(self.config.get('anime_cfg', 4.0)) if anime_anchor_scene else 1.5,
                'sampler': 'dpmpp_2m' if anime_anchor_scene else 'dpmpp_sde', 'scheduler': 'karras',
                'full_prompt': (('anime illustration background in the ByrdHouse visual canon, no people, no character, '
                                 + prompt.strip() + ', clean dark ink linework, warm cel shading, detailed environment, no text, no watermark')
                                if anime_anchor_scene else
                                'Editorial photograph, ' + prompt.strip() + ', realistic environment, coherent natural lighting, sharp detail'),
                'negative': ('person, face, head, body, human, character, crowd, pale skin, watermark, text, logo, blurry, deformed'
                             if anime_anchor_scene else
                             'additional person, extra face, face in background, pale skin, watermark, text, logo, blurry, deformed')}
        try:
            paths, _ = checked_masks(self.config, spec)
        except (SourceError, ReferenceInputError, ValueError, OSError) as exc:
            raise ValidationError(str(exc)) from exc
        input_root = Path(self.config.get('comfy_input_dir', Path(self.config['comfy_dir']) / 'input')).resolve()
        if not {'core', 'matte'}.issubset(paths) or not {'core', 'matte'}.issubset(spec['mask_hashes']):
            raise ValidationError('This legacy protection mask has no reviewed BiRefNet alpha and semantic core. Run a new photo analysis before scene editing.')
        if anime_anchor_scene and 'character' not in paths:
            raise ValidationError('This anime protection mask predates the tight character-edge workflow. Run and review a new anime mask before scene editing.')
        target = (input_root / 'ByrdHouse' / 'source-edits' / job_id / 'edit.png').resolve()
        if not target.is_relative_to(input_root):
            raise ValidationError('Scene edit input path is outside the local ComfyUI input folder.')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(paths['edit'].read_bytes())
        matte_target = (input_root / 'ByrdHouse' / 'source-edits' / job_id / 'matte.png').resolve()
        if not matte_target.is_relative_to(input_root):
            raise ValidationError('Alpha matte input path is outside the local ComfyUI input folder.')
        with matte_target.open('xb') as output:
            output.write(paths['matte'].read_bytes())
        core_target = (input_root / 'ByrdHouse' / 'source-edits' / job_id / 'core.png').resolve()
        if not core_target.is_relative_to(input_root):
            raise ValidationError('Semantic core input path is outside the local ComfyUI input folder.')
        with core_target.open('xb') as output:
            output.write(paths['core'].read_bytes())
        spec.update(edit_mask_path=str(target), edit_mask_image=target.relative_to(input_root).as_posix(),
                    matte_mask_path=str(matte_target),
                    matte_mask_image=matte_target.relative_to(input_root).as_posix(),
                    core_mask_path=str(core_target),
                    core_mask_image=core_target.relative_to(input_root).as_posix())
        if anime_anchor_scene:
            character_target = (input_root / 'ByrdHouse' / 'source-edits' / job_id / 'character.png').resolve()
            if not character_target.is_relative_to(input_root):
                raise ValidationError('Tight character mask input path is outside the local ComfyUI input folder.')
            with character_target.open('xb') as output:
                output.write(paths['character'].read_bytes())
            spec.update(character_mask_path=str(character_target),
                        character_mask_image=character_target.relative_to(input_root).as_posix())
        self.enqueue([spec])
        return self.job(job_id)

    def snapshot_path(self, job_id):
        job = self.job(job_id)
        if not job or not job.get('reference_snapshot'):
            raise FileNotFoundError()
        snapshot = reverify_reference(self.config, job['reference_snapshot'])
        return Path(snapshot['staged_path'])

    def animation_source(self, spec):
        parent_id = spec.get('parent_job_id')
        if parent_id:
            parent = self.job(parent_id)
            if not parent or parent['state'] != 'approved' or parent.get('operation') in ('portrait_animation', 'scene_animation', 'source_mask', 'anime_review'):
                raise ValidationError('Keep the still after reviewing its likeness before animating it.')
            return self.image_path(parent_id, 0)
        reference = spec.get('reference')
        allowed_illustrated = set(self.config.get('animation_allowed_illustrated_references', []))
        if reference not in self.references or (self.references[reference].get('generated', False)
                                               and reference not in allowed_illustrated):
            raise ValidationError('Choose an original Carey photo or an approved illustrated canon anchor for animation.')
        return self.reference_path(reference)

    def create_animation(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'reference','source_job_id'}:
            raise ValidationError('Animation accepts an original reference or an approved source_job_id.')
        parent_id = payload.get('source_job_id')
        if parent_id is not None and (not isinstance(parent_id,str) or len(parent_id)!=32 or any(c not in '0123456789abcdef' for c in parent_id)):
            raise ValidationError('Choose an approved still from the gallery.')
        reference = payload.get('reference', self.config.get('default_reference'))
        if parent_id:
            parent = self.job(parent_id)
            if parent: reference = parent.get('reference')
        if not isinstance(reference,str):
            raise ValidationError('Choose an original Carey reference or an approved illustrated canon anchor.')
        spec = {'id':secrets.token_hex(16),'operation':'portrait_animation',
                'parent_job_id':parent_id,'reference':reference,'seed':0,
                'prompt':'Carey · gentle blink and slight head movement',
                'identity_mode':'reference','engine':'liveportrait'}
        source = self.animation_source(spec)
        spec['animation_source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.enqueue([spec])
        return self.job(spec['id'])

    def create_scene_animation(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'reference', 'source_job_id', 'video_preset', 'prompt', 'seed'}:
            raise ValidationError('Scene animation accepts a reviewed source, movement, preview preset and seed.')
        preset = payload.get('video_preset', 'portrait_smoke')
        if not isinstance(preset, str) or preset not in VIDEO_PREVIEWS:
            raise ValidationError('Choose an installed video preview preset.')
        movement = payload.get('prompt', 'A gentle natural blink and slight shoulder breathing. Locked camera, keep the same smile and head angle.')
        if not isinstance(movement, str) or not 1 <= len(movement.strip()) <= 2000:
            raise ValidationError('Describe the movement in one to 2000 characters.')
        seed = payload.get('seed', secrets.randbelow(2**63))
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
            raise ValidationError('Video seed must be a nonnegative integer below 2^63.')
        parent_id = payload.get('source_job_id')
        if parent_id is not None and (not isinstance(parent_id, str) or len(parent_id) != 32
                or any(c not in '0123456789abcdef' for c in parent_id)):
            raise ValidationError('Choose an approved still from the gallery.')
        reference = payload.get('reference', self.config.get('anime_reference_id', 'carey-anime-anchor'))
        if parent_id:
            parent = self.job(parent_id)
            if parent: reference = parent.get('reference')
        if not isinstance(reference, str):
            raise ValidationError('Choose a reviewed Carey source.')
        spec = {'id': secrets.token_hex(16), 'operation': 'scene_animation', 'engine': 'wan22',
                'reference': reference, 'parent_job_id': parent_id, 'seed': seed,
                'video_preset': preset, 'identity_mode': 'reference',
                'prompt': ('Animate the same illustrated Carey from the supplied first frame. Black man, warm brown skin, '
                           'dark brown eyes, natural black afro, short beard and mustache. Preserve the facial proportions, '
                           'hair silhouette and clean illustrated linework. ' + movement.strip()),
                'negative': ('different person, white person, pale skin, changed hairstyle, shrinking afro, blurry face, '
                             'warped eyes, changing teeth, distorted mouth, extra earrings, flickering, text, watermark')}
        source = self.animation_source(spec)
        if not wan22_ready(self.config, self.models()):
            raise ValidationError('The Wan preview workflow and its three models must be installed first.')
        spec['animation_source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.enqueue([spec])
        return self.job(spec['id'])

    def create_pack(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"recipe", "versions", "prompt", "preset", "mode", "aspect", "lora", "strength", "seed", "identity_mode", "reference", "reference_strength", "denoise", "engine"}:
            raise ValidationError("Invalid character pack request.")
        recipe_id = payload.get("recipe")
        if not isinstance(recipe_id, str) or recipe_id not in self.recipes:
            raise ValidationError("Choose an installed Carey recipe.")
        versions = payload.get("versions", 1)
        if isinstance(versions, bool) or not isinstance(versions, int) or not 1 <= versions <= 3:
            raise ValidationError("Choose one to three versions per variation.")
        recipe = self.recipes[recipe_id]
        pack_id = secrets.token_hex(16)
        base = {key: value for key, value in payload.items() if key not in ("recipe", "versions")}
        extra = base.pop("prompt", "")
        if not isinstance(extra, str) or len(extra) > 1000:
            raise ValidationError("Pack direction must be at most 1,000 characters.")
        base.setdefault("preset", recipe["preset"])
        base.setdefault("aspect", recipe.get("aspect", "portrait"))
        specs = []
        for variation in recipe["variations"]:
            for version in range(versions):
                spec = self.make_spec({**base, "prompt": ", ".join(part for part in (recipe["base_prompt"], variation["prompt"], extra.strip()) if part)})
                if base.get("seed") not in (None, ""):
                    spec["seed"] = (spec["seed"] + len(specs)) % (2**63)
                spec.update(pack_id=pack_id, recipe=recipe_id, recipe_version=recipe["version"],
                            pack_title=recipe["title"], variant=variation["label"], version=version+1)
                specs.append(spec)
        self.enqueue(specs)
        return {"id": pack_id, "title": recipe["title"], "count": len(specs), "jobs": [spec["id"] for spec in specs]}

    def pack(self, pack_id):
        if len(pack_id) != 32 or any(c not in "0123456789abcdef" for c in pack_id):
            raise FileNotFoundError()
        with self.db() as db:
            rows = db.execute("SELECT * FROM jobs WHERE json_extract(spec, '$.pack_id')=? ORDER BY rowid", (pack_id,)).fetchall()
        if not rows:
            raise FileNotFoundError()
        return {"id": pack_id, "title": json.loads(rows[0]["spec"])["pack_title"], "jobs": [self.public_job(row) for row in rows]}

    def packs(self):
        with self.db() as db:
            ids = db.execute("SELECT json_extract(spec,'$.pack_id') AS pack_id FROM jobs WHERE json_extract(spec,'$.pack_id') IS NOT NULL GROUP BY pack_id ORDER BY MAX(rowid) DESC LIMIT 20").fetchall()
        return [self.pack(row["pack_id"]) for row in ids]

    def export_pack(self, pack_id):
        pack = self.pack(pack_id)
        if any(job["state"] in ("running", "queued", "recovering") for job in pack["jobs"]):
            raise ValidationError("Wait for the pack to finish before downloading it.")
        buffer = io.BytesIO()
        manifest = {"schema": "byrdhouse.animation.pack.v1", "purpose": "Carey animation still candidates with reproducible settings",
                    "id": pack_id, "title": pack["title"], "review_required": True, "images": []}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for job in pack["jobs"]:
                if not job["images"] or job["state"] == "rejected":
                    continue
                for index in range(len(job["images"])):
                    path = self.image_path(job["id"], index)
                    name = f"{len(manifest['images'])+1:02d}_{job['id']}.png"
                    archive.writestr(name, path.read_bytes())
                    archive.writestr(name + ".json", path.with_suffix(".png.json").read_bytes())
                    manifest["images"].append({"file": name, "label": job["variant"], "review_state": job["state"], "job_id": job["id"]})
            if not manifest["images"]:
                raise ValidationError("The pack has no usable images. Retry failed jobs or restore a rejected candidate.")
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.writestr("pack_to_blender.py", (HERE / "pack_to_blender.py").read_bytes())
            archive.writestr("README.txt", "Carey character pack\nAll candidates require a likeness review. Rejected images are omitted.\nImages are separate keyframe candidates, not a temporally coherent motion sequence.\nReview the faces, then use approved stills in Blender or an image-to-video model.\nThe JSON next to each PNG preserves prompt, seed, reference and model settings.\n\nBLENDER: Extract this ZIP, then run Blender with:\nblender --background --python pack_to_blender.py -- <extracted-pack-directory>\nThis creates Carey-animation-stills.blend with packed images and editable camera movement.\nThis animatic uses camera motion only; it does not animate limbs or expressions.\n")
        return buffer.getvalue()

    def reference_path(self, key):
        if key not in self.references:
            raise FileNotFoundError()
        path = (self.reference_dir / self.references[key]["file"]).resolve()
        if not path.is_relative_to(self.reference_dir) or not path.is_file():
            raise FileNotFoundError()
        return path

    def run_identity_belt(self, payload):
        """Validate and enqueue correction; rendering never runs in the HTTP handler."""
        if not isinstance(payload, dict) or set(payload) - {"target", "reference", "label"}:
            raise ValidationError("Identity belt accepts target, reference, and label.")
        target_value = payload.get("target")
        if not isinstance(target_value, str) or not target_value.strip():
            raise ValidationError("Identity belt needs a local target image path.")
        target_value = target_value.strip()
        target_candidates = []
        raw_target = Path(target_value)
        if raw_target.is_absolute():
            target_candidates.append(raw_target)
        else:
            target_candidates.extend((self.output_dir / raw_target, self.photo_dir / raw_target,
                                      self.reference_dir / raw_target))
        target = next((path.resolve() for path in target_candidates if path.is_file()), None)
        if target is None:
            raise ValidationError("Target must be an existing local image under the ByrdHouse library or photo folder.")
        allowed_roots = (self.output_dir.resolve(), self.photo_dir.resolve(), self.reference_dir.resolve())
        if not any(target.is_relative_to(root) for root in allowed_roots):
            raise ValidationError("Target path is outside the ByrdHouse local folders.")
        reference_key = payload.get("reference", self.config.get("default_reference", "portrait"))
        if not isinstance(reference_key, str):
            raise ValidationError("Select a local Carey reference.")
        reference = self.reference_path(reference_key)
        label = payload.get("label", "studio-belt")
        if not isinstance(label, str) or len(label) > 64:
            raise ValidationError("Belt label must be at most 64 characters.")
        with self.db() as db:
            parent = db.execute(
                'SELECT jobs.* FROM jobs, json_each(jobs.outputs) image WHERE image.value=? LIMIT 1',
                (target.name,)).fetchone() if target.parent == self.output_dir else None
        spec = json.loads(parent['spec']) if parent else {'seed': 0, 'engine': 'sdxl',
                'preset': 'photo', 'aspect': 'portrait', 'mode': 'fast', 'lora': '', 'strength': 0}
        for key in ('pack_id', 'recipe', 'variant', 'version', 'belt_analysis'):
            spec.pop(key, None)
        spec.update(id=secrets.token_hex(16), operation='identity_belt',
                    prompt='Correct Carey likeness: ' + target.name,
                    parent_job_id=parent['id'] if parent else None,
                    reference=reference_key, identity_mode='reference', belt_target=str(target),
                    belt_target_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    belt_reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                    belt_label=label or 'studio-belt')
        self.enqueue([spec])
        return self.job(spec['id'])

    def register_belt_candidate(self, target, reference_key, result, job_id=None):
        """Make a corrected generated still reviewable in the normal gallery."""
        if job_id is None and Path(target).resolve().parent != self.output_dir.resolve():
            return None
        with self.db() as db:
            parent = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone() if job_id else db.execute(
                "SELECT jobs.* FROM jobs, json_each(jobs.outputs) image WHERE image.value=? LIMIT 1",
                (Path(target).name,)).fetchone()
        if parent is None:
            return None  # Photo imports retain their ordinary belt files/report.
        spec = json.loads(parent['spec'])
        for key in ('pack_id', 'recipe', 'variant', 'version'):
            spec.pop(key, None)
        queued = job_id is not None
        job_id = job_id or secrets.token_hex(16)
        parent_id = spec.get('parent_job_id') if queued else parent['id']
        spec.update(id=job_id, operation='identity_belt', parent_job_id=parent_id,
                    reference=reference_key, identity_mode='reference',
                    belt_analysis=result.get('analysis'), belt_selected=result['selected'],
                    belt_measurement_checks_passed=result['accepted'])
        filename = f'{job_id}_1.png'
        source = self.belt_image(result['file'])
        destination = self.output_dir / filename
        shutil.copy2(source, destination)
        now = utcnow()
        card = {'schema': 'byrdhouse.studio.image.v1', 'job_id': job_id,
                'purpose': 'Corrected Carey still for visual likeness review',
                'created': now, 'file': filename, 'review_state': 'needs_review',
                'identity_verified': False, 'exact_replica': False, 'parent_job_id': parent_id,
                'source_image': Path(target).name, 'settings': spec,
                'belt_report': result['report'], 'selected': result['selected'],
                'measurement_checks_passed': result['accepted'], 'prompt_id': parent['prompt_id'] if queued else None}
        destination.with_suffix('.png.json').write_text(json.dumps(card, indent=2), encoding='utf-8')
        with self.db() as db:
            if queued:
                db.execute('UPDATE jobs SET spec=? WHERE id=?', (json.dumps(spec), job_id))
            else:
                db.execute('INSERT INTO jobs(id,state,created,started,finished,spec,outputs,seconds) VALUES(?,?,?,?,?,?,?,?)',
                           (job_id, 'needs_review', now, now, now, json.dumps(spec),
                            json.dumps([filename]), result.get('elapsed_seconds')))
        return job_id

    def belt_image(self, name):
        if not isinstance(name, str) or Path(name).name != name or not name.startswith("belt-") or not name.endswith(".png"):
            raise FileNotFoundError()
        path = (self.output_dir / name).resolve()
        if not path.is_relative_to(self.output_dir) or not path.is_file():
            raise FileNotFoundError()
        return path

    def job(self, job_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self.public_job(row) if row else None

    def recover_job(self, job_id):
        """Queue collection of an existing submission, never a new rendering request."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None or row['state'] != 'failed' or not row['prompt_id']:
                raise ValidationError('Recovery needs a failed job with a recorded ComfyUI submission.')
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running','recovering')").fetchone()[0]
            if count >= 64:
                raise ValidationError('The local queue is full. Wait for a render to finish.')
            db.execute("UPDATE jobs SET state='recovering',error=NULL,finished=NULL WHERE id=?", (job_id,))
        self.wake.set()
        return self.job(job_id)

    def create_mesh_cleanup(self, payload):
        from mesh_cleanup import freeze, MeshCleanupError
        from anime_view_review import reference_binding, VIEWS
        from anime_continuity import asset_root
        if not isinstance(payload, dict) or set(payload)-{'zone_file','view','denoise','seed'}:
            raise ValidationError('Mesh cleanup accepts an audited CPU bundle, approved view and conservative cleanup settings.')
        view=payload.get('view','three-quarter')
        if view not in VIEWS or view=='back': raise ValidationError('Choose a visible approved face view.')
        denoise=payload.get('denoise',0.18)
        seed=payload.get('seed',7124)
        if type(denoise) not in (int,float) or not math.isfinite(denoise) or not 0.05<=denoise<=0.30:
            raise ValidationError('Mesh cleanup denoise must be between 0.05 and 0.30.')
        if type(seed) is not int or not 0<=seed<2**63: raise ValidationError('Choose a valid seed.')
        checkpoint=self.config.get('anime_checkpoint')
        if checkpoint not in self.models().get('checkpoints',[]): raise ValidationError('Installed anime checkpoint is unavailable.')
        try:
            reference=reference_binding(asset_root(self.config),view)
            reference['selected_view']=view
            binding=freeze(self.config,payload.get('zone_file',''),reference)
        except (ValueError,OSError,KeyError,TypeError) as exc: raise ValidationError(str(exc)) from exc
        prompt='Clean cel shaded anime portrait of Carey, a Black man with brown skin, matching the provided face pixels, detailed brown eyes, clean beard and mustache, clear lips and teeth, consistent skin shading, crisp linework, preserve the reference facial features'
        spec={'id':secrets.token_hex(16),'operation':'mesh_cleanup','engine':'sdxl','preset':'anime',
              'identity_mode':'anime_mesh','reference':self.config.get('anime_reference_id','carey-anime-anchor'),
              'prompt':'Carey face mesh cleanup: '+view,'full_prompt':prompt,
              'negative':'pale skin, white man, blurred eyes, distorted teeth, extra earrings, warped mouth, text, watermark',
              'checkpoint':checkpoint,'denoise':float(denoise),'seed':seed,'aspect':'portrait',
              'mesh_binding':binding,'private_evaluation_only':True,'purpose':'Private reference-based Carey face cleanup trial'}
        self.enqueue([spec])
        return self.job(spec['id'])

    def create_anime_review(self, payload):
        from anime_view_review import VIEWS, reference_binding
        from anime_continuity import asset_root, freeze_inputs, illustrated
        from identity_belt import measurement_binding
        if not isinstance(payload, dict) or set(payload) - {'source_job_id', 'view', 'image_index'}:
            raise ValidationError('Likeness checking accepts an existing illustrated job and its visible angle.')
        parent_id = payload.get('source_job_id')
        if not isinstance(parent_id, str) or len(parent_id) != 32 or any(c not in '0123456789abcdef' for c in parent_id):
            raise ValidationError('Choose an existing Carey illustration or clip.')
        view = payload.get('view')
        if view not in VIEWS:
            raise ValidationError('Choose the visible front, side, rear or three-quarter angle.')
        image_index = payload.get('image_index', 0)
        if type(image_index) is not int or not 0 <= image_index < 4:
            raise ValidationError('Choose a valid still image index.')
        parent = self.job(parent_id)
        if (not parent or parent['state'] not in ('needs_review', 'approved', 'rejected')
                or parent.get('operation') in ('anime_review', 'source_mask')
                or not illustrated(parent, self.config.get('anime_reference_id', 'carey-anime-anchor'))):
            raise ValidationError('This check needs a completed illustrated Carey still or clip, not a photo or diagnostic report.')
        try:
            frames, files = freeze_inputs(self, parent, image_index)
            binding = reference_binding(asset_root(self.config), view)
        except (ValueError, OSError, KeyError, IndexError) as exc:
            raise ValidationError(str(exc)) from exc
        spec = {'id': secrets.token_hex(16), 'operation': 'anime_review',
                'source_job_id': parent_id, 'selected_view': view,
                'review_frames': frames, 'review_files': files, 'approved_view_binding': binding,
                'measurement_binding': measurement_binding(self.config),
                'prompt': f"Check Carey likeness: {view}, {len(frames)} saved frame(s)",
                'seed': 0, 'engine': 'cpu', 'preset': 'anime', 'reference': parent.get('reference'),
                'identity_mode': 'anime_continuity_review'}
        self.enqueue([spec])
        return self.job(spec['id'])

    def anime_review_report(self, job_id):
        from anime_continuity import work_dir, sha
        job = self.job(job_id)
        if not job or job.get('operation') != 'anime_review':
            raise FileNotFoundError()
        card = self.metadata(job_id)
        path = work_dir(self.config, job_id) / 'review.json'
        if sha(path) != card.get('review_report_sha256'):
            raise ValidationError('Saved continuity evidence changed; inspect it before trusting the report.')
        return json.loads(path.read_text(encoding='utf-8'))

    def anime_review_reference_path(self, job_id):
        from anime_view_review import reference_binding
        from anime_continuity import asset_root
        job = self.job(job_id)
        if not job or job.get('operation') != 'anime_review':
            raise FileNotFoundError()
        binding = reference_binding(asset_root(self.config), job['selected_view'])
        if binding != job['approved_view_binding']:
            raise ValidationError('The approved view changed; do not reuse the stale comparison.')
        return Path(binding['path'])

    def public_job(self, row):
        spec = json.loads(row["spec"])
        outputs = json.loads(row["outputs"])
        if spec.get('operation') == 'anime_review':
            from anime_continuity import work_dir
            if row['started'] and row['finished']:
                spec['review_wall_seconds'] = round((datetime.fromisoformat(row['finished'])
                                                    - datetime.fromisoformat(row['started'])).total_seconds(), 2)
            progress_path = work_dir(self.config, row['id']) / 'progress.json'
            if progress_path.is_file():
                try:
                    spec['review_progress'] = json.loads(progress_path.read_text(encoding='utf-8'))
                except (ValueError, OSError):
                    pass
        return {"id": row["id"], "state": row["state"], "created": row["created"],
                "started": row["started"], "finished": row["finished"], "error": row["error"],
                "seconds": row["seconds"], "prompt_id": row["prompt_id"], **spec,
                "seed": str(spec["seed"]),
                "images": [f"/images/{row['id']}/{i}" for i in range(len(outputs))],
                "video_url": f"/videos/{row['id']}" if outputs and spec.get('operation') in ('portrait_animation', 'scene_animation') else None,
                "metadata_url": f"/api/jobs/{row['id']}/metadata" if outputs else None}

    def jobs(self):
        with self.db() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created DESC, rowid DESC LIMIT 100").fetchall()
        return [self.public_job(row) for row in rows]

    def image_path(self, job_id, index):
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise FileNotFoundError()
        with self.db() as db:
            row = db.execute("SELECT outputs FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise FileNotFoundError()
        outputs = json.loads(row["outputs"])
        if not isinstance(index, int) or index < 0 or index >= len(outputs):
            raise FileNotFoundError()
        path = (self.output_dir / outputs[index]).resolve()
        if not path.is_relative_to(self.output_dir) or not path.is_file() or path.suffix != ".png":
            raise FileNotFoundError()
        return path

    def metadata(self, job_id):
        path = self.image_path(job_id, 0)
        card = path.with_suffix(".png.json").resolve()
        if not card.is_relative_to(self.output_dir):
            raise FileNotFoundError()
        return json.loads(card.read_text(encoding="utf-8"))

    def video_path(self, job_id):
        poster = self.image_path(job_id, 0)  # Reuse ID, output and containment checks.
        job = self.job(job_id)
        if job.get('operation') not in ('portrait_animation', 'scene_animation'): raise FileNotFoundError()
        path = (poster.parent / f'{job_id}.mp4').resolve()
        if not path.is_relative_to(self.output_dir) or not path.is_file(): raise FileNotFoundError()
        return path

    def saved_prompt_id(self, spec):
        """Recover the callback/SQLite crash window from an operation journal."""
        operation = spec.get('operation')
        if operation == 'identity_belt':
            path = self.output_dir / f"belt-{spec['id']}.submission.json"
        elif operation in ('portrait_animation', 'scene_animation'):
            path = self.output_dir.parent.parent / 'media/animation' / spec['id'] / 'submission.json'
        elif operation in ('source_mask', 'source_preserve'):
            from source_preserve import work_dir
            path = work_dir(self.config, spec['id']) / 'submission.json'
        else:
            path = self.submission_dir / (spec['id'] + '.json')
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            prompt_id = record.get('prompt_id')
            return prompt_id if isinstance(prompt_id, str) and prompt_id else None
        except (OSError, ValueError):
            return None

    def reconcile_prompt(self, prompt_id):
        """Only resume a known submission; missing history is not permission to POST."""
        try:
            if self.client.request('/history/' + urllib.parse.quote(prompt_id, safe='')).get(prompt_id):
                return
            queue = self.client.request('/queue')
        except BackendError as exc:
            raise ObservationPending(str(exc)) from exc
        if any(isinstance(item, list) and len(item) > 1 and item[1] == prompt_id
               for key in ('queue_running', 'queue_pending') for item in queue.get(key, [])):
            return
        # Completion can move the prompt from queue to history between reads.
        try:
            if self.client.request('/history/' + urllib.parse.quote(prompt_id, safe='')).get(prompt_id):
                return
        except BackendError as exc:
            raise ObservationPending(str(exc)) from exc
        raise BackendError('Saved submission is absent from ComfyUI queue and history. Inspect the saved artifacts; no duplicate was submitted.')

    def run_next(self):
        if not self.execution_lock.acquire(blocking=False):
            return False
        try:
            return self._run_next()
        finally:
            self.execution_lock.release()

    def verify_anime_canon_profile(self, reference_id, reference_path, reference_face):
        """Bind illustrated review to the owner-approved, measured anchor."""
        configured = self.config.get('anime_canon_profile')
        if not configured:
            return None
        path = Path(configured).resolve()
        try:
            raw = path.read_bytes()
            profile = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise BeltError(f'Canon profile is unreadable: {path}') from exc
        if (not isinstance(profile, dict)
                or profile.get('schema') != 'byrdhouse.carey-anime-canon-profile.v1'
                or profile.get('status') != 'measured_from_approved_anchor'
                or profile.get('reference_id') != reference_id):
            raise BeltError('Canon profile does not describe the approved Carey anime reference.')
        expected = profile.get('anchor_sha256')
        manifest_hash = self.references[reference_id].get('source_sha256')
        actual = hashlib.sha256(reference_path.read_bytes()).hexdigest()
        if (not isinstance(expected, str) or len(expected) != 64
                or expected != actual or manifest_hash != actual):
            raise BeltError('Canon profile, approved anchor, and Studio reference hashes differ.')
        measured = profile.get('metrics')
        if not isinstance(measured, dict):
            raise BeltError('Canon profile has no measured feature targets.')
        version = reference_face.metrics.get('measurement_version')
        if profile.get('measurement_version') != version:
            raise BeltError('Canon profile uses a different examiner version; measure the unchanged approved anchor separately.')
        if version:
            from identity_belt import measurement_binding
            if profile.get('measurement_binding') != measurement_binding(self.config):
                raise BeltError('Canon profile examiner code or model weights changed.')
        for feature in ('hairline_y_ratio', 'forehead_height_ratio',
                        'hair_width_ratio', 'hair_height_ratio', 'face_aspect_ratio'):
            baseline = measured.get(feature)
            current = reference_face.metrics.get(feature)
            if (not isinstance(baseline, (int, float))
                    or not isinstance(current, (int, float))
                    or abs(float(baseline) - float(current)) > 0.03):
                raise BeltError(f'Canon profile feature {feature} no longer matches the approved anchor.')
        return {'file': str(path), 'profile_sha256': hashlib.sha256(raw).hexdigest(),
                'anchor_sha256': actual, 'status': 'verified'}

    def analyze_generated_identity(self, spec, outputs):
        """Attach a read-only face/hair/outline review to PuLID stills.

        This deliberately performs no swap, restoration, or image edit. The
        report is evidence for a human likeness decision and uses one frozen
        Carey reference from the already pinned board.
        """
        if spec.get('identity_mode') not in ('pulid', 'anime_anchor') or not outputs:
            return None
        reference_id = (spec.get('pulid_reference_ids', [None])[0]
                        if spec.get('identity_mode') == 'pulid'
                        else self.config.get('anime_reference_id', 'carey-anime-anchor'))
        if not isinstance(reference_id, str) or reference_id not in self.references:
            raise ValidationError('Identity review is missing its locked Carey reference binding.')
        target = (self.output_dir / outputs[0]).resolve()
        if not target.is_relative_to(self.output_dir) or not target.is_file():
            raise ValidationError('Identity review target is outside the local image library.')
        if self.identity_belt is None:
            self.identity_belt = IdentityBelt(self.config, self.client)
        illustrated = spec.get('identity_mode') == 'anime_anchor'
        reference_path = self.reference_path(reference_id)
        reference = None
        profile = None
        try:
            reference = self.identity_belt.inspect(reference_path, illustrated=illustrated)
            if illustrated:
                profile = self.verify_anime_canon_profile(reference_id, reference_path, reference)
            candidate = self.identity_belt.inspect(target, illustrated=illustrated)
        except BeltError as exc:
            # The photoreal face detector has a legitimate blind spot on some
            # illustrated frames.  A detector failure is evidence that the
            # keyframe cannot pass its automated inspection, never a reason to
            # crash a completed render or treat it as approved.
            report = {
                'schema': 'byrdhouse.identity-belt.inspection.v1',
                'identity_mode': spec.get('identity_mode'),
                'purpose': 'Read-only local Carey still inspection; no pixel correction and no automatic likeness approval',
                'review_required': True, 'accepted': False,
                'reference': reference.public() if reference is not None else
                             {'file': str(reference_path), 'detected': False},
                'target': {'file': str(target), 'detected': False},
                'selected': {'file': target.name, 'similarity': None},
                'target_to_reference_similarity': None,
                'geometry_delta': {},
                'inspection_error': str(exc),
                'visual_review': {
                    'status': 'Automatic face inspection was inconclusive; reject this keyframe until a human review approves a corrected render.',
                    'findings': [{
                        'feature': ('Canon profile' if 'canon profile' in str(exc).lower()
                                    else 'Face detection'),
                        'difference': ('The approved canon profile or anchor changed: ' + str(exc)
                                       if 'canon profile' in str(exc).lower() else
                                       'The local review detector could not locate a usable face in the generated illustrated frame.'),
                        'correction': ('Restore the approved anchor/profile binding before reviewing this keyframe.'
                                       if 'canon profile' in str(exc).lower() else
                                       'Regenerate from the approved anchor with a larger, sharper face before considering animation.'),
                        'face_relative_point': [0.5, 0.5],
                    }],
                },
            }
            report_path = target.with_name(target.stem + '-identity-analysis.json')
            report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
            card_path = target.with_suffix('.png.json')
            card = json.loads(card_path.read_text(encoding='utf-8'))
            card['identity_belt_inspection'] = {
                'report': report_path.name, 'image': None, 'similarity': None,
                'geometry_delta': {}, 'automatic_gates_passed': False,
                'review_required': True, 'inspection_error': str(exc),
            }
            card_path.write_text(json.dumps(card, indent=2), encoding='utf-8')
            return card['identity_belt_inspection']
        similarity = self.identity_belt._similarity(reference, candidate)
        geometry = self.identity_belt._geometry(reference, candidate, illustrated=illustrated)
        reference_label = 'approved Carey anime anchor' if illustrated else 'real Carey reference'
        measures = [
            ('Face outline', 'face_outline_error', f'Compare jaw and cheek contour directly against the {reference_label}.'),
            ('Forehead / hairline height', 'forehead_height_ratio', f'Compare the hair-to-skin boundary and visible forehead height against the {reference_label}.'),
            ('Afro width', 'hair_width_ratio', f'Compare the outward curl silhouette and crown width against the {reference_label}.'),
            ('Afro height', 'hair_height_ratio', f'Compare crown height and shape against the {reference_label}.'),
            ('Hairline position', 'hairline_y_ratio', 'Compare the irregular natural curl boundary rather than accepting a smooth generated hairline.'),
            ('Skin brightness', 'skin_median_luma', 'Check skin tone under the scene lighting; reject an illustration that lightens Carey into a different person.'),
        ]
        findings = []
        same_view = geometry.get('review_scope') == 'same_view_illustrated_continuity'
        review_limits = {'face_outline_error': 0.05, 'forehead_height_ratio': 0.10,
                         'hair_width_ratio': 0.16, 'hair_height_ratio': 0.16,
                         'hairline_y_ratio': 0.10}
        feature_points = {'face_outline_error': [0.82, 0.72],
                          'forehead_height_ratio': [0.50, 0.25],
                          'hair_width_ratio': [1.28, 0.05],
                          'hair_height_ratio': [0.50, -0.35],
                          'hairline_y_ratio': [0.50, 0.02],
                          'skin_median_luma': [0.28, 0.55]}
        for label, key, correction in measures:
            value = geometry.get(key)
            if value is not None:
                needs_change = bool(illustrated and same_view and
                                    (geometry.get('skin_lightening_warning', False)
                                     if key == 'skin_median_luma' else
                                     value > review_limits.get(key, float('inf'))))
                if key == 'skin_median_luma':
                    difference = (f"Median skin brightness shift: {geometry.get('skin_luma_shift', 0):+.3f} "
                                  'on the 0–255 luminance scale; lighting-sensitive.')
                else:
                    difference = (f'Normalized feature difference: {value}. '
                                  'This is a review cue, not biometric proof.')
                findings.append({'feature': label,
                                 'difference': difference, 'needs_change': needs_change,
                                 'correction': correction,
                                 'face_relative_point': feature_points[key]})
        findings.sort(key=lambda item: not item['needs_change'])
        accepted = bool(spec.get('identity_mode') == 'pulid' and similarity >= 0.65
                        and geometry.get('forehead_within_gate') and geometry.get('hair_within_gate')
                        and geometry.get('outline_within_gate'))
        report = {
            'schema': 'byrdhouse.identity-belt.inspection.v1',
            'identity_mode': spec.get('identity_mode'),
            'purpose': 'Read-only local Carey still inspection; no pixel correction and no automatic likeness approval',
            'review_required': True, 'accepted': accepted,
            'reference': reference.public(), 'target': candidate.public(),
            'selected': {'face': candidate.public(), 'file': target.name, 'similarity': round(similarity, 6)},
            'target_to_reference_similarity': round(similarity, 6),
            'canon_profile': profile,
            'geometry_delta': geometry,
            'visual_review': {'status': ('automatic anime-anchor continuity cues only; visual human approval required'
                                         if spec.get('identity_mode') == 'anime_anchor'
                                         else 'automatic cues only; visual human approval required'), 'findings': findings},
        }
        report_path = target.with_name(target.stem + '-identity-analysis.json')
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        from render_belt_report import render
        image_path = render(report_path)
        card_path = target.with_suffix('.png.json')
        card = json.loads(card_path.read_text(encoding='utf-8'))
        card['identity_belt_inspection'] = {
            'report': report_path.name, 'image': image_path.name,
            'similarity': round(similarity, 6), 'geometry_delta': geometry,
            'automatic_gates_passed': accepted, 'review_required': True,
        }
        card_path.write_text(json.dumps(card, indent=2), encoding='utf-8')
        return card['identity_belt_inspection']

    def _run_next(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE state IN ('queued','recovering') ORDER BY CASE state WHEN 'recovering' THEN 0 ELSE 1 END, rowid LIMIT 1").fetchone()
            if row is None:
                return False
            db.execute("UPDATE jobs SET state='running', started=COALESCE(started,?), error=NULL WHERE id=?", (utcnow(), row["id"]))
        started = time.monotonic()
        spec = json.loads(row["spec"])
        prior_seconds = float(row['seconds'] or 0) if row['state'] == 'recovering' or spec.get('operation') == 'anime_review' else 0
        try:
            if row['state'] == 'recovering':
                self.reconcile_prompt(row['prompt_id'])
                outputs = self.generate(spec, resume_prompt_id=row['prompt_id'])
            else:
                outputs = self.generate(spec)
            try:
                inspection = self.analyze_generated_identity(spec, outputs)
            except Exception as exc:
                # The still remains available for review if the optional CPU
                # examiner is unavailable; retain the failure as provenance.
                inspection = {'review_required': True, 'error': str(exc)[:500]}
            if inspection is not None:
                spec['identity_belt_inspection'] = inspection
            if spec.get('operation') == 'anime_review':
                spec['review_summary'] = json.loads((self.output_dir / outputs[0]).with_suffix('.png.json').read_text(encoding='utf-8'))['review_summary']
            seconds = prior_seconds + time.monotonic() - started
            if spec.get('operation') == 'anime_review' and row['started']:
                # A killed CPU process cannot flush its final stopwatch. Keep
                # the original claimed time so restart gaps remain in the wall duration.
                seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(row['started'])).total_seconds()
            with self.db() as db:
                db.execute("UPDATE jobs SET state='needs_review', finished=?, outputs=?, seconds=?, spec=? WHERE id=?",
                           (utcnow(), json.dumps(outputs), round(seconds, 2), json.dumps(spec), row["id"]))
        except ReviewInterrupted:
            with self.db() as db:
                db.execute("UPDATE jobs SET state='queued', seconds=? WHERE id=?",
                           (round(prior_seconds+time.monotonic()-started, 2), row['id']))
            return False
        except ObservationPending as exc:
            with self.db() as db:
                db.execute("UPDATE jobs SET state='recovering', error=? WHERE id=?", (str(exc)[:2000], row['id']))
            return False
        except Exception as exc:
            with self.db() as db:
                recorded = db.execute('SELECT prompt_id FROM jobs WHERE id=?', (row['id'],)).fetchone()[0]
                journal_id = self.saved_prompt_id(spec) if not recorded else None
                recorded = recorded or journal_id
                uncertain = recorded and (self.stop.is_set() or 'Cannot reach local ComfyUI' in str(exc)
                                           or 'exceeded 20 minutes' in str(exc) or journal_id
                                           or isinstance(exc, sqlite3.OperationalError))
                db.execute("UPDATE jobs SET state=?, finished=?, error=?, seconds=?, prompt_id=? WHERE id=?",
                           ('recovering' if uncertain else 'failed', None if uncertain else utcnow(),
                            str(exc)[:2000], round(prior_seconds+time.monotonic()-started, 2), recorded, row["id"]))
                if uncertain:
                    return False
        return True

    def generate(self, spec, resume_prompt_id=None):
        def submitted(prompt_id):
            with self.db() as db:
                db.execute('UPDATE jobs SET prompt_id=? WHERE id=?', (prompt_id, spec['id']))
        if spec.get('operation') == 'mesh_cleanup':
            from mesh_cleanup import verify
            verify(self.config, spec['mesh_binding'])
        if spec.get('operation') == 'anime_review':
            from anime_continuity import run
            if self.identity_belt is None:
                self.identity_belt = IdentityBelt(self.config, None)
            return run(self.config, spec, self.identity_belt, self.stop)
        if spec.get('operation') == 'identity_belt':
            target = Path(spec['belt_target']).resolve()
            roots = (self.output_dir, self.photo_dir, self.reference_dir)
            if not any(target.is_relative_to(root) for root in roots):
                raise ValidationError('Correction target is outside the local library.')
            reference = self.reference_path(spec['reference'])
            if (hashlib.sha256(target.read_bytes()).hexdigest() != spec['belt_target_sha256']
                    or hashlib.sha256(reference.read_bytes()).hexdigest() != spec['belt_reference_sha256']):
                raise ValidationError('Correction source changed after queueing. Review the current photos before retrying.')
            if self.identity_belt is None:
                self.identity_belt = IdentityBelt(self.config, self.client)
            result = self.identity_belt.run(target, reference, spec['belt_label'], run_id=spec['id'],
                                            resume_prompt_id=resume_prompt_id, submitted=submitted, stop=self.stop)
            self.register_belt_candidate(target, spec['reference'], result, job_id=spec['id'])
            return [f"{spec['id']}_1.png"]
        if spec.get('operation') in ('portrait_animation', 'scene_animation'):
            from portrait_animation import animate
            source = self.animation_source(spec)
            return animate(self.config,self.client,spec,source,self.stop,submitted,
                           resume_prompt_id=resume_prompt_id)
        if spec.get('operation') in ('source_mask', 'source_preserve'):
            from source_preserve import run
            if spec['operation'] == 'source_preserve':
                parent = self.job(spec['mask_job_id'])
                if not parent or parent['state'] != 'approved':
                    raise ValidationError('Protection mask was rejected after queueing; review it before editing.')
            return run(self.config, self.client, spec, self.stop, submitted, resume_prompt_id)
        if spec.get('identity_mode') in ('reference', 'photo_edit', 'anime_anchor'):
            if not spec.get('reference_snapshot'):
                raise ValidationError('Legacy still has no frozen reference input. Inspect its saved output; create a new reviewed job instead of reusing mutable photos.')
            snapshot = reverify_reference(self.config, spec['reference_snapshot'], job_id=spec['id'])
            if snapshot['comfy_image'] != spec['reference_image']:
                raise ValidationError('Still workflow input differs from its frozen reference snapshot.')
        if spec.get('identity_mode') == 'anime_anchor':
            pose = reverify_reference(self.config, spec.get('anime_pose_snapshot'))
            if pose['comfy_image'] != spec.get('anime_pose_image'):
                raise ValidationError('Anime-anchor pose source changed after queueing.')
        if spec.get('identity_mode') == 'pulid':
            snapshots = spec.get('pulid_reference_snapshots')
            images = spec.get('pulid_reference_images')
            if not isinstance(snapshots, list) or len(snapshots) != 3 or not isinstance(images, list) or len(images) != 3:
                raise ValidationError('PuLID still is missing its frozen three-photo Carey reference board.')
            for snapshot, image in zip(snapshots, images):
                verified = reverify_reference(self.config, snapshot)
                if verified['comfy_image'] != image:
                    raise ValidationError('PuLID reference board changed after queueing.')
            pose = reverify_reference(self.config, spec.get('pulid_pose_snapshot'))
            if pose['comfy_image'] != spec.get('pulid_pose_image'):
                raise ValidationError('PuLID pose source changed after queueing.')
        graph = build_graph(self.config, spec)
        journal = self.submission_dir / (spec['id'] + '.json')
        settings_hash = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        saved = json.loads(journal.read_text(encoding='utf-8')) if journal.is_file() else None
        if saved:
            if saved.get('settings_sha256') != settings_hash or saved.get('job_id') != spec['id']:
                raise BackendError('Saved generation settings differ; refusing to submit or resume altered work.')
            graph = saved['workflow']
            if hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest() != saved['workflow_sha256']:
                raise BackendError('Saved generation workflow hash does not match.')
        elif resume_prompt_id:
            record = self.client.request('/history/' + urllib.parse.quote(resume_prompt_id, safe='')).get(resume_prompt_id, {})
            stored_prompt = record.get('prompt', [])
            if not (isinstance(stored_prompt, list) and len(stored_prompt) > 2 and isinstance(stored_prompt[2], dict)):
                raise BackendError('Saved generation workflow is missing. Inspect the legacy submission; no duplicate was submitted.')
            graph = stored_prompt[2]
        prompt_id = resume_prompt_id or (saved.get('prompt_id') if saved else None)
        if resume_prompt_id and saved and saved.get('prompt_id') != resume_prompt_id:
            raise BackendError('Saved generation prompt ID does not match the job.')
        def save_submission(record):
            temporary = journal.with_suffix('.json.part')
            temporary.write_text(json.dumps(record, indent=2), encoding='utf-8')
            temporary.replace(journal)
        if prompt_id is None:
            if saved:
                raise BackendError('Interrupted submission has no recorded ID. Inspect ComfyUI; no automatic resubmission.')
            saved = {'job_id': spec['id'], 'purpose': 'Resume the same local still submission',
                     'settings_sha256': settings_hash, 'workflow': graph,
                     'workflow_sha256': hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest(),
                     'prompt_id': None}
            save_submission(saved)
            response = self.client.request("/prompt", {"prompt": graph, "client_id": "byrdhouse-studio"})
            prompt_id = response.get("prompt_id")
            if not isinstance(prompt_id, str) or not prompt_id or response.get("node_errors"):
                raise BackendError(f"ComfyUI rejected the workflow: {json.dumps(response)[:1500]}")
            saved['prompt_id'] = prompt_id
            save_submission(saved)
        with self.db() as db:
            db.execute("UPDATE jobs SET prompt_id=? WHERE id=?", (prompt_id, spec["id"]))
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            try:
                history = self.client.request("/history/" + urllib.parse.quote(prompt_id, safe=""))
            except BackendError as exc:
                if "timed out" not in str(exc):
                    raise
                if self.stop.wait(0.8):
                    raise BackendError("Studio stopped while awaiting ComfyUI.") from exc
                continue
            record = history.get(prompt_id)
            if record:
                status = record.get("status", {})
                errors = [entry[1] for entry in status.get("messages", [])
                          if isinstance(entry, list) and len(entry) == 2 and entry[0] in ("execution_error", "execution_interrupted")]
                if errors or status.get("status_str") == "error":
                    detail = errors[0].get("exception_message", "Generation interrupted") if errors and isinstance(errors[0], dict) else "Generation failed"
                    raise BackendError(str(detail))
                if status.get("completed"):
                    if spec.get('reference_snapshot'):
                        reverify_reference(self.config, spec['reference_snapshot'], job_id=spec['id'])
                    images = record.get("outputs", {}).get("9", {}).get("images", [])
                    if not images:
                        raise BackendError("ComfyUI finished without a saved image.")
                    if len(images) > 4:
                        raise BackendError("Unexpected number of image outputs.")
                    names = []
                    for index, image in enumerate(images):
                        if image.get("type") != "output" or not isinstance(image.get("filename"), str):
                            raise BackendError("ComfyUI returned an invalid image record.")
                        query = urllib.parse.urlencode({key: image.get(key, "") for key in ("filename", "subfolder", "type")})
                        data = self.client.request("/view?" + query, binary=True)
                        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                            raise BackendError("The generated output was not a PNG image.")
                        filename = f"{spec['id']}_{index + 1}.png"
                        target = self.output_dir / filename
                        temporary = target.with_suffix(".png.part")
                        temporary.write_bytes(data)
                        temporary.replace(target)
                        card = {"schema": "byrdhouse.studio.image.v1", "job_id": spec["id"],
                                "purpose": "Local creative image preview for review", "created": utcnow(),
                                "checkpoint": self.config.get("flux_model") if spec.get("engine") == "flux" else graph["1"]["inputs"]["ckpt_name"],
                                "acceleration_lora": graph.get("3", {}).get("inputs", {}).get("lora_name") if spec.get("engine") != "flux" else None,
                                "identity_verified": False, "exact_replica": False, "review_state": "needs_review", "prompt_id": prompt_id,
                                "settings": spec, "negative": graph.get("5", {}).get("inputs", {}).get("text", ""), "sampler": graph["7"]["inputs"],
                                "width": ASPECTS[spec["aspect"]][0], "height": ASPECTS[spec["aspect"]][1],
                                "workflow": graph, "file": filename, "source": "local ComfyUI"}
                        if spec.get('operation') == 'mesh_cleanup':
                            from mesh_cleanup import finish
                            report=finish(self.config,spec,target)
                            card.update(width=report['width'],height=report['height'],mesh_composite=report,
                                        purpose=spec['purpose'],private_evaluation_only=True)
                        card_path = target.with_suffix(".png.json")
                        card_part = target.with_suffix(".png.json.part")
                        card_part.write_text(json.dumps(card, indent=2), encoding="utf-8")
                        card_part.replace(card_path)
                        names.append(filename)
                    return names
            if self.stop.wait(0.8):
                raise BackendError("Studio stopped while awaiting ComfyUI. Check ComfyUI before retrying.")
        raise BackendError("Generation exceeded 20 minutes. Check ComfyUI before retrying.")

    def review(self, job_id, state):
        if state not in ("approved", "rejected"):
            raise ValidationError("Review must be approved or rejected.")
        job = self.job(job_id)
        if not job or job["state"] not in ("needs_review", "approved", "rejected"):
            raise ValidationError("This image is not ready for review.")
        for index, _ in enumerate(job["images"]):
            path = self.image_path(job_id, index).with_suffix(".png.json")
            card = json.loads(path.read_text(encoding="utf-8"))
            card["review_state"] = state
            card["reviewed"] = utcnow()
            temp = path.with_suffix(".json.part")
            temp.write_text(json.dumps(card, indent=2), encoding="utf-8")
            temp.replace(path)
            if job.get('operation') in ('portrait_animation', 'scene_animation'):
                self.video_path(job_id).with_suffix('.mp4.json').write_text(json.dumps(card,indent=2),encoding='utf-8')
        with self.db() as db:
            db.execute("UPDATE jobs SET state=? WHERE id=?", (state, job_id))
        return self.job(job_id)

    def work(self):
        while not self.stop.is_set():
            if not self.run_next():
                self.wake.wait(1)
                self.wake.clear()

    def close(self):
        self.stop.set()
        self.wake.set()


def handler_class(studio):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ByrdHouseStudio/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def allowed_request(self):
            try:
                host = urllib.parse.urlsplit("http://" + self.headers.get("Host", ""))
                if host.hostname not in LOOPBACK or host.port != self.server.server_port or host.username or host.password or host.path:
                    return False
                origin = self.headers.get("Origin")
                if origin:
                    parsed = urllib.parse.urlsplit(origin)
                    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK or parsed.port != self.server.server_port or parsed.path or parsed.query or parsed.fragment or parsed.username:
                        return False
                return True
            except ValueError:
                return False

        def reply(self, code, payload, content_type="application/json"):
            raw = json.dumps(payload).encode("utf-8") if content_type == "application/json" else payload
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.allowed_request():
                return self.reply(403, {"error": "Only local Studio requests are allowed."})
            route = urllib.parse.urlsplit(self.path).path
            try:
                if route == "/api/state":
                    return self.reply(200, studio.state())
                if route == "/api/jobs":
                    return self.reply(200, {"jobs": studio.jobs()})
                if route == "/api/packs":
                    return self.reply(200, {"packs": studio.packs()})
                parts = route.strip("/").split("/")
                if len(parts) == 2 and parts[0] == "references":
                    return self.reply(200, studio.reference_path(parts[1]).read_bytes(), "image/png")
                if len(parts) == 3 and parts[:2] == ["api", "belt"]:
                    return self.reply(200, studio.belt_image(urllib.parse.unquote(parts[2])).read_bytes(), "image/png")
                if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                    job = studio.job(parts[2])
                    if not job:
                        raise FileNotFoundError()
                    return self.reply(200, job)
                if len(parts) == 3 and parts[:2] == ["api", "packs"]:
                    return self.reply(200, studio.pack(parts[2]))
                if len(parts) == 4 and parts[:2] == ["api", "packs"] and parts[3] == "download":
                    return self.reply(200, studio.export_pack(parts[2]), "application/zip")
                if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "metadata":
                    return self.reply(200, studio.metadata(parts[2]))
                if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "continuity":
                    return self.reply(200, studio.anime_review_report(parts[2]))
                if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "matched-reference":
                    return self.reply(200, studio.anime_review_reference_path(parts[2]).read_bytes(), 'image/png')
                if len(parts) == 4 and parts[:2] == ['api', 'jobs'] and parts[3] == 'source':
                    return self.reply(200, studio.snapshot_path(parts[2]).read_bytes(), 'image/png')
                if len(parts) == 3 and parts[0] == "images" and parts[2].isdigit():
                    return self.reply(200, studio.image_path(parts[1], int(parts[2])).read_bytes(), "image/png")
                if len(parts) == 2 and parts[0] == 'videos':
                    return self.reply(200, studio.video_path(parts[1]).read_bytes(), 'video/mp4')
                assets = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8")}
                if route in assets:
                    name, content_type = assets[route]
                    return self.reply(200, (HERE / name).read_bytes(), content_type)
                return self.reply(404, {"error": "Not found."})
            except ValidationError as exc:
                return self.reply(400, {"error": str(exc)})
            except (FileNotFoundError, ValueError, IndexError):
                return self.reply(404, {"error": "Image or metadata not found."})
            except Exception as exc:
                return self.reply(500, {"error": str(exc)[:500]})

        def do_POST(self):
            if not self.allowed_request() or self.headers.get("X-ByrdHouse-Studio") != "1":
                return self.reply(403, {"error": "Only local Studio requests are allowed."})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.reply(415, {"error": "Send application/json."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 16384 or self.headers.get("Transfer-Encoding"):
                    return self.reply(413, {"error": "Invalid request size."})
                payload = json.loads(self.rfile.read(length))
                route = urllib.parse.urlsplit(self.path).path
                if route == "/api/jobs":
                    return self.reply(201, studio.create_job(payload))
                if route == '/api/animations':
                    return self.reply(201, studio.create_animation(payload))
                if route == '/api/scene-animations':
                    return self.reply(201, studio.create_scene_animation(payload))
                if route == '/api/anime-reviews':
                    return self.reply(201, studio.create_anime_review(payload))
                if route == '/api/mesh-cleanups':
                    return self.reply(201, studio.create_mesh_cleanup(payload))
                if route == '/api/source-masks':
                    return self.reply(201, studio.create_source_mask(payload))
                if route == '/api/source-edits':
                    return self.reply(201, studio.create_source_edit(payload))
                if route == "/api/packs":
                    return self.reply(201, studio.create_pack(payload))
                if route == "/api/belt":
                    return self.reply(201, studio.run_identity_belt(payload))
                parts = route.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ['api', 'jobs'] and parts[3] == 'recover':
                    if payload != {}:
                        raise ValidationError('Recovery uses the saved submission and accepts no new settings.')
                    return self.reply(202, studio.recover_job(parts[2]))
                if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "review":
                    if not isinstance(payload, dict) or set(payload) != {"state"}:
                        raise ValidationError("Review requires a state.")
                    return self.reply(200, studio.review(parts[2], payload["state"]))
                return self.reply(404, {"error": "Not found."})
            except (ValidationError, BeltError, json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError) as exc:
                return self.reply(400, {"error": str(exc)[:1000]})
            except Exception as exc:
                return self.reply(500, {"error": str(exc)[:500]})

        def log_message(self, fmt, *args):
            # Never log user prompts or identity/photo paths.
            if not (self.path.startswith("/api/") and args and str(args[1]) == "200"):
                super().log_message(fmt, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    studio = Studio(config)
    server = ThreadingHTTPServer((config["studio_host"], config["studio_port"]), handler_class(studio))
    server.daemon_threads = True
    print(f"ByrdHouse Studio ready at http://127.0.0.1:{config['studio_port']}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        studio.close()
        server.server_close()


if __name__ == "__main__":
    main()
