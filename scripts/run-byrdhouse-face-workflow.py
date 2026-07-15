from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path


ROOT = Path(r"E:\ByrdHouse")
COMFY_ROOT = ROOT / "Generators" / "ComfyUI"
DEFAULT_WORKFLOW = ROOT / "Images" / "Workflows" / "byrdhouse_face_swap_social" / "byrdhouse_social_main_head_fast_api_v1.json"
DEFAULT_SOURCE = ROOT / "profiles" / "me" / "references" / "ai_identity_front_v1.png"
ARCHIVE = ROOT / "Images" / "Library"


def post_multipart(url: str, field: str, path: Path) -> dict:
    boundary = ("----ByrdHouse" + uuid.uuid4().hex).encode("ascii")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = path.read_bytes()
    body = b"--" + boundary + b"\r\n"
    body += f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'.encode()
    body += f"Content-Type: {content_type}\r\n\r\n".encode()
    body += data + b"\r\n"
    body += b'--' + boundary + b'\r\n'
    body += b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
    body += b'--' + boundary + b'--\r\n'
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}", "Content-Length": str(len(body))},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def input_name(upload_result: dict) -> str:
    name = upload_result.get("name") or upload_result.get("filename")
    subfolder = upload_result.get("subfolder") or ""
    if not name:
        raise RuntimeError(f"ComfyUI did not return an uploaded filename: {upload_result}")
    return f"{subfolder}/{name}" if subfolder else name


def upload_if_needed(comfy: str, path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    result = post_multipart(f"{comfy}/upload/image", "image", path)
    return input_name(result)


def find_node(graph: dict, class_type: str | None = None, title_part: str | None = None) -> tuple[str, dict]:
    matches = []
    for node_id, node in graph.items():
        if class_type and node.get("class_type") != class_type:
            continue
        title = str(node.get("_meta", {}).get("title", ""))
        if title_part and title_part.lower() not in title.lower():
            continue
        matches.append((node_id, node))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one node class={class_type!r} title={title_part!r}, found {len(matches)}")
    return matches[0]


def queue(comfy: str, graph: dict) -> str:
    body = json.dumps({"prompt": graph, "client_id": f"byrdhouse-face-{uuid.uuid4()}"}).encode("utf-8")
    request = urllib.request.Request(
        f"{comfy}/prompt", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("node_errors"):
        raise RuntimeError(f"ComfyUI rejected the workflow: {result['node_errors']}")
    return result["prompt_id"]


def wait_for_result(comfy: str, prompt_id: str, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with urllib.request.urlopen(f"{comfy}/history/{prompt_id}", timeout=30) as response:
            history = json.loads(response.read().decode("utf-8"))
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status, ensure_ascii=False))
            return entry
        time.sleep(2)
    raise TimeoutError(f"ComfyUI did not finish prompt {prompt_id} within {timeout_seconds} seconds")


def output_paths(entry: dict) -> list[Path]:
    paths = []
    for node_output in entry.get("outputs", {}).values():
        for image in node_output.get("images", []):
            folder = COMFY_ROOT / "output"
            if image.get("subfolder"):
                folder /= image["subfolder"]
            paths.append(folder / image["filename"])
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a ByrdHouse local face-insertion workflow.")
    parser.add_argument("--target", required=True, type=Path, help="Social/game image to edit")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Your face reference photo")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW, help="Saved API workflow JSON")
    parser.add_argument("--face-index", default="0", help="Target face index, e.g. 0 or 0,1,2")
    parser.add_argument("--crop-x", type=int, help="Override ImageCrop x when using the zoom workflow")
    parser.add_argument("--crop-y", type=int, help="Override ImageCrop y when using the zoom workflow")
    parser.add_argument("--crop-width", type=int, help="Override ImageCrop width when using the zoom workflow")
    parser.add_argument("--crop-height", type=int, help="Override ImageCrop height when using the zoom workflow")
    parser.add_argument("--output-width", type=int, help="Override final ImageScale width")
    parser.add_argument("--output-height", type=int, help="Override final ImageScale height")
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    comfy = args.comfy_url.rstrip("/")
    graph = json.loads(args.workflow.read_text(encoding="utf-8-sig"))
    target_name = upload_if_needed(comfy, args.target.resolve())
    source_name = upload_if_needed(comfy, args.source.resolve())

    _, target_node = find_node(graph, "LoadImage", "TARGET IMAGE")
    _, source_node = find_node(graph, "LoadImage", "FACE SOURCE")
    _, reactor_node = find_node(graph, "ReActorFaceSwap")
    target_node["inputs"]["image"] = target_name
    source_node["inputs"]["image"] = source_name
    reactor_node["inputs"]["input_faces_index"] = args.face_index

    crop_values = {
        "x": args.crop_x,
        "y": args.crop_y,
        "width": args.crop_width,
        "height": args.crop_height,
    }
    if any(value is not None for value in crop_values.values()):
        if not all(value is not None for value in crop_values.values()):
            raise ValueError("Use all four crop overrides together: --crop-x --crop-y --crop-width --crop-height")
        crop_nodes = [node for node in graph.values() if node.get("class_type") == "ImageCrop"]
        if len(crop_nodes) != 1:
            raise RuntimeError("Crop overrides require exactly one ImageCrop node in the selected workflow")
        crop_nodes[0]["inputs"].update(crop_values)

    scale_values = {"width": args.output_width, "height": args.output_height}
    if any(value is not None for value in scale_values.values()):
        if not all(value is not None for value in scale_values.values()):
            raise ValueError("Use both output overrides together: --output-width --output-height")
        scale_nodes = [node for node in graph.values() if node.get("class_type") == "ImageScale"]
        if len(scale_nodes) != 1:
            raise RuntimeError("Output overrides require exactly one ImageScale node in the selected workflow")
        scale_nodes[0]["inputs"].update(scale_values)

    prompt_id = queue(comfy, graph)
    entry = wait_for_result(comfy, prompt_id, args.timeout)
    paths = [path for path in output_paths(entry) if path.exists()]
    if not paths:
        raise RuntimeError(f"ComfyUI completed but returned no local image files: {entry}")

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived = []
    for index, path in enumerate(paths, start=1):
        destination = ARCHIVE / f"byrdhouse_face_{stamp}_{index}{path.suffix.lower()}"
        shutil.copy2(path, destination)
        archived.append(destination)
        sidecar = destination.with_suffix(".json")
        sidecar.write_text(
            json.dumps(
                {
                    "prompt_id": prompt_id,
                    "workflow": str(args.workflow),
                    "target": str(args.target.resolve()),
                    "source": str(args.source.resolve()),
                    "face_index": args.face_index,
                    "comfy_output": str(path),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    for path in archived:
        print(path)


if __name__ == "__main__":
    main()
