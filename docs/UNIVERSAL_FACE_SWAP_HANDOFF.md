# Universal Face Swap Handoff

Date: 2026-07-18 (last updated 19:40 EDT)

## Outcome

The one-click `image.faceswap` auto route now goes through the audited CPU face-zone belt instead of the legacy YOLO/FaceDetailer rectangle route. The dashboard can keep sending `payload.route = "auto"`; the worker still calls `byrdimage.facezone_auto`, but that function now resolves a reviewed recipe/preset and delegates to `edit_face_zone`.

This fixes the class of failures seen on Vegeta and Luffy: the mask must be a closed head/ear/neck authority with protected target linework, not a detector box.

## Fail-Closed Auto Route

`facezone_auto` is now fail-closed against every silent-stall class of bug:

- **Missing ComfyUI venv python** — falls back to `sys.executable` so test roots (and any caller without a full ComfyUI drop) still consult the CPU examiner instead of erroring out with `FileNotFoundError`.
- **Subprocess exceptions** — `FileNotFoundError` and `OSError` are caught and routed through `_facezone_auto_unavailable`, which writes a `bbox/facezone-auto-refused` card with `detector`/`denoise`/`face_zone` fields and the verbatim reason. No more swallowed exceptions.
- **No-face / tiny face / failed closed-head traversal** — produces a `needs_review` card the same way instead of a half-finished workflow.

The card surface is identical whether the CPU examiner refused, the subprocess could not run, or the inputs were unsolvable. That means the founder can spot a refusal from a single glance at the artifact kind and route field on the dashboard.

## Test Contract

`tests/integration_test.py` accepts both `mesh_geometry_fit_mode == "target-landmarks"` and `"target-landmarks-core"` for the 478-point mesh seed check. The exact label can shift with the v3 mesh-fit path; the contract is the union of accepted labels, not a single string.

## Target Routing

Known immutable targets route by SHA-256, not filename:

| Target | SHA-256 | Recipe | Preset | Face index | Notes |
| --- | --- | --- | --- | ---: | --- |
| `anime_game_2.jpg` | `067a9eef44eefbb8c592364711bc9df6557274d8ae5b83bdbe9d9110c8e5fcd0` | `anime_face_zone_edit@3` | `luffy_close` | 2 | Multi-face sheet; use the close grin face. |
| `anime_game_3.jpg` | `8398872a4a7cb53532cd0b753325c347d3da530dbe2307b4113face1dd5cf598` | `anime_face_zone_edit@1` | `gojo` | 0 | Founder-approved smooth skin/closed lip calibration. |
| `anime_game_4.jpg` | `eaf9ac218ec00ff42734293e48b3ec851ca7f163c6bcda732c65815614a0b436` | `anime_face_zone_edit@3` | `vegeta` | 0 | Hard anime: preserve target feature ink and transfer connected Carey complexion. |

Unknown targets still use `anime_face_zone_edit@3` with preset `auto`, but must pass the CPU examiner. No operable face, tiny face, or failed closed head traversal means stop and review instead of guessing.

## Recipe Split

`anime_face_zone_edit` must remain the broad quality lane. A Vegeta-only experiment was moved to `anime_face_zone_hard_edit@1` so bare `anime_face_zone_edit` resolves to the universal v3 recipe again.

Do not put single-character experimental calibrations at the highest version of the generic recipe. That is how Gojo and Luffy drifted away from known-good settings.

## Mold Library

`scripts/build_head_mold_library.py` builds a local SHA-keyed target mold cache from reviewed `face_zone.json` manifests. It stores masks, anchors, cards, and variants only; it does not copy RGB target art.

The default `standard48` profile emits 48 bounded variants per target:

- 4 skin insets
- 3 hairline guards
- 2 neck policies
- 2 feather radii

Seven reviewed targets therefore produce 336 reusable mask geometries. This is the right way to get a large interchangeable library without downloading copyrighted anime character cutouts.

Commands:

```powershell
python scripts/build_head_mold_library.py build --target Images\Targets\anime_games\anime_game_4.jpg --zone-manifest artifacts\face_zones\2026-07\JOB\face_zone.json --library-root artifacts\head_molds
python scripts/build_head_mold_library.py verify --mold-dir artifacts\head_molds\TARGET_SHA256
python -m unittest tests.test_head_mold_library
```

## Commercial-Safe Stack

Allowed/open components for the funded lane after local verification:

| Component | License posture | Use |
| --- | --- | --- |
| OpenCV | Apache-2.0 | Connected components, color families, morphology, line protection. |
| MediaPipe face mesh | Apache-2.0 | 478-point inner face anchors. |
| SAM 2.1 tiny | Apache-2.0 | Prompted outer head/ear/neck envelope when installed. |
| IP-Adapter Plus Face SD1.5 | Apache-2.0 | Real Carey photo identity conditioning without InsightFace. |
| ControlNet Canny SD1.5 | OpenRAIL | Preserve target linework during anime redraw. |
| Blender | GPL app; output artwork is not restricted by Blender license | Future 3D head/pose helper. |
| GIMP | GPL app; output artwork may be used commercially | Future manual/automated finishing helper. |
| Google Cartoon Set | CC BY 4.0 | Optional synthetic geometry dataset with attribution. |

Blocked or private-only:

- InsightFace / inswapper / FaceID checkpoints: noncommercial or InsightFace-dependent.
- InstantID: research-only dependency chain.
- ParseNet fallback: private evaluation only until license is cleared or replaced.
- Random popular-character PNG hair/eyes/ears packs: usually not commercially cleared, even if the file is easy to download.

## Vegeta Rule

For Vegeta-class hard anime, success comes from two authorities:

- Full semantic head/ear/neck outline owns complexion coverage. It must attack connected pale/orange target skin components inside the head mold while protecting hair, armor, background, eye whites, target ink, and independent hairline.
- Inner landmarks own likeness only around eyes, nose, mouth, beard line, and lower face. Never stretch the 478-point mesh to fill Vegeta's whole forehead or hairline.

The accepted direction is: keep Vegeta's head shape and ink, make all exposed skin Carey-brown, then inject Carey likeness into the inner face without moving the silhouette.

## Bounded Verification Used

Passed on 2026-07-18:

```powershell
python -m py_compile scripts\byrdimage.py scripts\byrdfacezone.py scripts\build_head_mold_library.py tests\integration_test.py
python -m unittest tests.test_head_mold_library
$env:BYRDHOUSE_ROOT='E:\ByrdHouse'; python scripts\byrdimage.py --swap-target Images\Targets\anime_games\anime_game_4.jpg --auto --project careyrpg --purpose "auto route smoke" --dry-run
$env:BYRDHOUSE_ROOT='E:\ByrdHouse'; python scripts\byrdimage.py --swap-target Images\Targets\anime_games\anime_game_3.jpg --auto --project careyrpg --purpose "auto route smoke" --dry-run
$env:BYRDHOUSE_ROOT='E:\ByrdHouse'; python scripts\byrdimage.py --swap-target Images\Targets\anime_games\anime_game_2.jpg --auto --project careyrpg --purpose "auto route smoke" --dry-run
python tests\integration_test.py
```

Final integration suite result: **ALL CHECKS PASSED (167/167)**. The code adds 90-second bounds to face-zone analyzer/prepare subprocesses to prevent the prior class of stalls.