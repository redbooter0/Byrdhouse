"""Submit the private PhotoMaker V1 target-edit smoke workflow to local ComfyUI.

This runner deliberately does not create a router job or alter an application
recipe.  Its only job is to prove whether the local 8 GB worker can load and
sample the official V1 adapter with dynamic VRAM.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import byrdimage


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--workflow",
        type=Path,
        default=root / "workflows" / "sdxl_photomaker_v1_target_smoke_api.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    workflow_path = args.workflow.resolve()
    graph = json.loads(workflow_path.read_text(encoding="utf-8-sig"))
    graph.pop("_comment", None)
    cfg = byrdimage.load_json(root / "byrdhouse.config.json")
    job_id = f"photomaker_v1_smoke_{datetime.now():%Y%m%d_%H%M%S}"
    card = {
        "recipe": "private_photomaker_v1_smoke",
        "purpose": "private local 8 GB PhotoMaker V1 fit and identity smoke",
        "workflow": str(workflow_path.relative_to(root)).replace("\\", "/"),
        "checkpoint": "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors",
        "identity_mode": "PhotoMaker V1 direct reference",
        "identity_source": "profiles/me/references/ai_identity_front_v1.png",
        "status_note": "private experimental only; not routed to the ByrdHouse app",
        "seed": 7124,
        "steps": 12,
        "cfg": 5.5,
        "denoise": 0.50,
    }
    outputs = byrdimage.run_graph(root, cfg["services"]["comfyui"].rstrip("/"), graph, job_id, "image_lab", card)
    for path, _ in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
