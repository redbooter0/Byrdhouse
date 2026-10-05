# Current Machine Inventory

Living document (handoff deliverable). Two kinds of entries:

- **CONFIRMED** — verified in the repo or in prior recorded runs.
- **VERIFY** — from the 2026-07-15 handoff or older notes; must be re-checked
  by running `scripts\byrdhouse-preflight.ps1` on the machine before being
  treated as current. Paste each machine's preflight summary into its section
  and flip the labels.

## Current single-PC Windows restoration (2026-10-02)

2026-10-04 video update: native Wan 2.2 5B, UMT5 scaled FP8 and Wan 2.2 VAE
are verified and installed on D:, total 18,144,966,705 bytes. A 384x576,
33-frame Carey anchor video rendered in 472.68 s. Live startup persists
`--cache-ram 4 8 --disable-async-offload --disable-dynamic-vram`; MIOpen
remains at Comfy's default disabled behavior after a slower local experiment.
The launcher uses trusted Python 3.13.15 with the existing venv site-packages
via config, avoiding the observed venv-launcher App Control block. Native
Torch/runtime versions are unchanged. See
[the measured qualification](reviews/2026-10-04-native-wan-amd-qualification.md).

Confirmed locally: Intel i9-10850K (10 cores / 20 threads), 32 GB RAM,
AMD Radeon RX 7900 XT (20,464 MiB), and attached 2 TB D: data HDD with
approximately 1.96 TB free. Current root is `D:\ByrdHouse`, independent of
the disconnected/erased former E: installation. The mini PC is deferred by owner.

ComfyUI 0.38.0, Python 3.13.15, PyTorch 2.13.0+rocm10.0.0; ComfyUI reports
the RX 7900 XT as its active device. The local Studio and ComfyUI bind to
loopback only; addresses and model paths live in `byrdhouse-local.json`.
FLUX.2 Klein 4B BF16 reference editing and SDXL LoRA + IP-Adapter routes
have both completed actual local image jobs. Blender 5.2.2 is installed locally.

The inventories below describe the older two-PC deployment; their CONFIRMED
labels reflect those historical runs, not this newly restored hardware.

## Historical BYRD-GAMING (GPU worker)

| Item | Value | Status |
|---|---|---|
| Root | `E:\ByrdHouse` (`%BYRDHOUSE_ROOT%`) | CONFIRMED |
| GPU | NVIDIA RTX 3070, 8 GB VRAM | CONFIRMED (U0/Face Lab runs) |
| CPU | Intel i9-10850K (20 threads; belt uses ≤16 for training) | CONFIRMED |
| RAM | 32 GB DDR4 | VERIFY (preflight records installed memory) |
| ComfyUI | `http://byrd-gaming:8188` (`/system_stats`), portable install under `Generators/` | CONFIRMED (config `services.comfyui`) |
| LM Studio | `http://byrd-gaming:1234/v1` — unload before heavy ComfyUI passes (GPU mode ritual) | CONFIRMED |
| Roles | image/video generation worker, LM Studio operator, future Godot/Unreal worker | CONFIRMED |
| SDXL throughput | ~15.7–18.5 s/image after tuning | VERIFY (historical; re-measure via benchmark runner) |

## BYRD-MINI (orchestration)

| Item | Value | Status |
|---|---|---|
| Root | `D:\ByrdHouse` | CONFIRMED |
| CPU | Ryzen 5 6600H | VERIFY |
| RAM | 8 GB reported | VERIFY (preflight records installed memory) |
| Router/dashboard | `http://byrd-mini:8787` (`/health`) | CONFIRMED (config `services.router`) |
| Qdrant | Docker `byrdhouse-qdrant`, `http://byrd-mini:6333/readyz` | CONFIRMED |
| SQLite ops DB | `D:\ByrdHouse\db\byrdhouse.db` (WAL) | CONFIRMED |
| Memory DB | `D:/ByrdHouse/db/byrdhouse_memory.db` (memory MCP) | CONFIRMED (DECISIONS 2026-07-10) |
| GPU | none (status yellow is expected/non-blocking) | CONFIRMED |

## Network / addressing

| Item | Value | Status |
|---|---|---|
| Hostnames | Tailscale MagicDNS: `byrd-gaming`, `byrd-mini`, `byrd-vault` | CONFIRMED (config `hosts`; hard rule: no hardcoded IPs) |
| Exposure | Tailnet only; nothing public | CONFIRMED (hard rule) |
| `15.2.2.5` conflict (handoff §2.2) | Which machine (if any) owns this address | VERIFY — preflight resolves both hostnames' IPv4 on each machine; record results here |

## Preflight results

Paste the summary block (or attach `preflight.json`) from each run:

### BYRD-GAMING — last run: (never)

*(pending — run `scripts\byrdhouse-preflight.ps1`)*

### BYRD-MINI — last run: (never)

*(pending — run `scripts\byrdhouse-preflight.ps1`)*
