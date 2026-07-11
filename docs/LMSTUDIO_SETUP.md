# LM Studio — one-time setup so it boots reliably

The "LM Studio fails on the first attempt / I have to re-enable the local
connection" problem is LM Studio dropping its server settings when a model is
swapped. Two halves: settings that must persist, and the belt not thrashing it.

## The belt's half (already fixed in code)

The worker no longer force-swaps models. GPU modes: IMAGE unloads everything to
free the 3070's VRAM (required); OPERATOR now uses whatever text model is
already loaded instead of forcing a reload; the judge only loads its model if
it isn't already up. So a single loaded model (even a VL model) serves chat,
judging, and prompt-enhancement without a single disruptive reload.

## Your half — LM Studio settings (Developer tab, set once)

1. **Server** → turn ON, port **1234**.
2. **Serve on Local Network** → ON (so `byrd-gaming:1234` is reachable, not just
   localhost).
3. **CORS** → ON / "Enable CORS". This is the setting that gets knocked off — with
   it on, the dashboard and router can call the model from another machine.
4. **Just-In-Time model loading** → ON. Lets `/v1/models` report what's available
   and auto-load on first request, so a cold server still answers.
5. Load your model and, in its settings, **GPU offload = MAX**, and consider
   pinning it (keep loaded) so it survives idle.

## Match the config to what you actually run

`byrdhouse.config.json` on GAMING has `gpu.operator_model` and `gpu.judge_model`.
The belt is now interchangeable — if the configured name isn't loaded it uses
whatever IS loaded — but the cleanest setup for a single-model rig:

- Running **one** model (e.g. a Qwen-VL): set BOTH
  `"operator_model"` and `"judge_model"` to that model's exact id (copy it from
  LM Studio's model list), OR leave them and the belt will use the loaded one.
- A VL (vision) model judges images AND chats fine — you do not need a separate
  text model unless you want one.

## Verify

From the mini (or any verified private-network machine):
`http://byrd-gaming:1234/v1/models` in a browser should return JSON listing the
loaded model. If it does, `byrd-status.ps1` will show `svc_lmstudio` green and
chat/judge will work on the first try.
