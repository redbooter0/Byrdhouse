# ByrdHouse lightweight social face-insertion workflows

These workflows are the fast local path for turning an imported social, game, or promotional image into a ByrdHouse post image. They use ReActor `inswapper_128.onnx`; they do not load the 9B FLUX.2 Klein model.

Inputs:

- Target image: the social/game image being edited.
- Face source: `E:\ByrdHouse\profiles\me\references\me_photo_08.jpg` by default, copied into ComfyUI input as `REFERENCE_1_SUBJECT.jpg`.

Saved variants:

- `social_main_head_fast`: fastest, face restoration off, target index `0`.
- `social_main_head_polished`: GFPGAN restoration, target index `0`.
- `social_group_main_only`: main detected person only, target index `0`.
- `social_group_all_heads_same_face`: opt-in all-head mode, target indices `0,1,2,3`.
- `game_character_main_head`: main-head replacement on a gaming-style target.
- `social_main_head_zoom_manual`: the ComfyUI loop `face swap → crop → upscale → save`; adjust the crop node to make the selected person larger.

To process an image through the ByrdHouse local runner:

```powershell
python E:\ByrdHouse\scripts\run-byrdhouse-face-workflow.py `
  --target "C:\path\to\your\target.jpg" `
  --workflow "E:\ByrdHouse\Images\Workflows\byrdhouse_face_swap_social\byrdhouse_social_main_head_fast_api_v1.json" `
  --face-index 0
```

The runner uploads the target and face source to local ComfyUI, executes the saved API workflow, and archives the result under `E:\ByrdHouse\Images\Library` with a JSON sidecar describing the source, target, workflow, and selected face index.

For the zoom loop, use:

```powershell
python E:\ByrdHouse\scripts\run-byrdhouse-face-workflow.py `
  --target "C:\path\to\your\target.jpg" `
  --workflow "E:\ByrdHouse\Images\Workflows\byrdhouse_face_swap_social\byrdhouse_social_main_head_zoom_manual_api_v1.json" `
  --face-index 0 `
  --crop-x 120 --crop-y 350 --crop-width 360 --crop-height 650 `
  --output-width 768 --output-height 1387
```

The crop values are ordinary ComfyUI `ImageCrop` node controls. Move the crop rectangle around the intended person; this is the part that makes your face more visible without changing the whole scene.

Face indices follow ReActor's `large-small` detection order, not necessarily left-to-right order. Start with `--face-index 0`, inspect the result, and try `1` or `2` if the wrong person was selected. In the supplied Nightcap example 1, the front-center person is index `2`. Use `0,1,2` only when you explicitly want the same source face applied to multiple heads.

Use only your own face or faces for which you have permission, and label edited/deepfake content when posting where required.
