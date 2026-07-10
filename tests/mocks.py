"""Mock ComfyUI + LM Studio servers for belt testing (no GPU, no models)."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 64x64 red PNG so the compositor has real pixels to work with.
import base64
import io
import struct
import zlib


def _tiny_png(w=64, h=64, rgb=(180, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


PNG = _tiny_png()
JUDGE_VERDICT = json.dumps({"score": 4.2, "scores": {"readability": 4, "contrast": 5},
                            "tags": ["portal", "dark-gold"], "caption": "A test verdict."})
PACKAGE = json.dumps({"titles": ["T1", "T2", "T3", "T4", "T5"],
                      "tags": ["last epoch", "tier list"],
                      "description": "Two paragraphs.\n\n00:00 intro",
                      "pinned_comment": "What build should I break next?"})


class Comfy(BaseHTTPRequestHandler):
    graphs = {}

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        pid = f"mock-{len(Comfy.graphs)}"
        Comfy.graphs[pid] = payload["prompt"]
        self._json({"prompt_id": pid})

    def do_GET(self):
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[1]
            graph = Comfy.graphs.get(pid)
            if not graph:
                return self._json({})
            batch = next((n["inputs"]["batch_size"] for n in graph.values()
                          if n.get("class_type") == "EmptyLatentImage"), 1)
            prefix = next(n["inputs"]["filename_prefix"] for n in graph.values()
                          if n.get("class_type") == "SaveImage")
            images = [{"filename": f"{prefix}_{i:05d}_.png", "subfolder": "", "type": "output"}
                      for i in range(batch)]
            return self._json({pid: {"status": {"status_str": "success"},
                                     "outputs": {"9": {"images": images}}}})
        if self.path.startswith("/view"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            return self.wfile.write(PNG)
        self._json({"system": "mock"})


class Lms(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json({"data": [{"id": "mock-vl"}]})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        vision = "image_url" in body
        content = JUDGE_VERDICT if vision else PACKAGE
        self._json({"choices": [{"message": {"content": content}}]})


def start(comfy_port: int, lms_port: int):
    for srv in (ThreadingHTTPServer(("127.0.0.1", comfy_port), Comfy),
                ThreadingHTTPServer(("127.0.0.1", lms_port), Lms)):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
