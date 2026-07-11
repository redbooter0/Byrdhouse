# Good morning — update prompts (2026-07-11)

Both machines are behind main. Paste these exactly, in order.

## 1. BYRD-MINI (PowerShell)

```powershell
cd C:\Users\Byrdh\byrdhouse
git fetch origin
git reset --hard origin/main
powershell -ExecutionPolicy Bypass -File scripts\setup-mini.ps1
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
powershell -ExecutionPolicy Bypass -File D:\ByrdHouse\scripts\start-byrdhouse.ps1
powercfg /change standby-timeout-ac 0
```

## 2. BYRD-GAMING (PowerShell, from its repo clone)

```powershell
git fetch origin
git reset --hard origin/main
powershell -ExecutionPolicy Bypass -File scripts\setup-gaming.ps1
powershell -ExecutionPolicy Bypass -File scripts\tune-gaming.ps1
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*worker.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
powershell -ExecutionPolicy Bypass -File E:\ByrdHouse\scripts\start-byrdhouse.ps1
powercfg /change standby-timeout-ac 0
```

(`git reset --hard origin/main` because the machines fell behind and may hold
local edits — the repo is the source of truth for the kit. Machine configs at
`D:\ByrdHouse` / `E:\ByrdHouse` are NOT touched by this.)

## 3. Rotate the admin token (once — the old one leaked into git history)

```powershell
-join ((48..57)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
```
Put the output in `auth.admin_token` in BOTH machines' `byrdhouse.config.json`,
restart the router (mini) and worker (GAMING), re-paste the token on your
iPad/phone dashboards.

## 4. What's new since the machines last pulled (PRs #8–#12)

- Recipes v3/v4 (game-anchored, full-body framing) + freeform + version-pinned
  recipe dropdown (what you pick is what runs; the card tag proves it)
- Viral compositor (banner / accent styles) + thumbnails from YOUR screenshots
  (Source image field) + reference library (upload thumbnails you love; the
  judge grades against them)
- Refine pipeline: ⬆ upscale and ≈ riff buttons on every card; aspect presets
  (9:16 TikTok, 2:3 portrait, …); LoRA field; ✨ prompt enhancement
- Operator Chat with TOOLS: ask it for an image and it queues a real job;
  it can check status/artifacts/events. Fallback slot for a small model on
  the mini (`lmstudio_fallback`) = chat answers even mid-generation
- Interchangeable models: whatever's loaded in LM Studio judges/chats;
  whatever checkpoints are installed generate; `--gpu max` loads
- New look: your logo in the app, room icons, glow pass

## 5. First flight after update

1. Open `http://byrd-mini:8787` → hard refresh → the hawk logo should be in
   the sidebar. Paste the NEW token.
2. Operator Chat → "make me a 16:9 palworld thumbnail, base raid chaos" →
   watch the 🔧 queue_image bubble → Image Studio shows it generating.
3. Pick the best card → ≈ riff → pick again → ⬆ upscale → approve.
4. Upload your 4 favorite viral thumbnails to the reference library
   (tags: palworld / general) so the judge learns your bar.

## 6. When you have 10 minutes

- LM Studio on the MINI: load Qwen2.5-3B-Instruct Q4, serve on 1234, set
  `"lmstudio_fallback": "http://localhost:1234/v1"` in the mini's config →
  always-on chat.
- On GAMING, download one stylized SDXL checkpoint (Animagine XL 4.0 or
  DreamShaper XL) into `Generators\ComfyUI\models\checkpoints` → type its
  name in the Checkpoint field for Palworld/Pokémon-style runs.
