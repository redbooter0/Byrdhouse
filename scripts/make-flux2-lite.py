#!/usr/bin/env python3
"""Derive the RTX 3070-safe Flux2 Lite API graph from the production graph."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(r"E:\ByrdHouse"))
    args = parser.parse_args()
    src = args.root / "Images" / "Workflows" / "byrdhouse_flux2_klein_real_to_gaming_api_v1.json"
    out = args.root / "Images" / "Workflows" / "byrdhouse_flux2_klein_lite_real_to_gaming_api_v1.json"
    graph = json.loads(src.read_text(encoding="utf-8-sig"))
    graph["92:80"]["inputs"]["megapixels"] = 1.0
    graph["92:85"]["inputs"]["megapixels"] = 2.0
    graph["115"]["inputs"]["value"] = 12
    graph["92:63"]["inputs"]["cfg"] = 0.7
    graph.pop("103", None)
    graph.pop("82", None)
    graph["126"]["inputs"]["filename_prefix"] = "ByrdHouse/Flux2Klein/lite/ByrdHouse_Flux2Klein_LITE"
    out.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Created {out}")


if __name__ == "__main__":
    main()
