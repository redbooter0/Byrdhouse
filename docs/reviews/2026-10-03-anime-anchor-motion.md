# Carey Anime Canon Anchor v1 motion test — 2026-10-03

## Purpose

Validate whether the owner-approved Carey anime anchor can receive a small
amount of motion without changing the visual identity used for ByrdHouse social
shorts. This is an animation test, not a new-scene or new-pose generation.

## Locked source

- Source: `D:\ByrdHouse\assets\characters\carey-anime\anchor-v1.png`
- SHA256: `2f85df9f6efa92915b57d666dbd2c3e3467ae91e540f603156bc4084c0ff4640`
- Studio reference ID: `carey-anime-anchor`
- Permission: only this explicitly approved illustrated canon anchor is allowed
  to enter the portrait-animation route. Other generated images remain blocked
  unless a reviewed still is approved first.

## Render evidence

| Field | Value |
|---|---|
| Studio job | `0cf48a1d6a53295f53b4727bd0efb4e7` |
| ComfyUI prompt | `0e33445f-78d9-46fc-9491-5939258c788a` |
| Method | Existing local AdvancedLivePortrait route, gentle blink + slight head motion |
| Output | `D:\ByrdHouse\media\images\0cf48a1d6a53295f53b4727bd0efb4e7.mp4` |
| Frames / duration | 44 frames / 2.933333 seconds |
| Render time | 205.72 seconds |
| Current review state | `needs_review` |

## Visual spot check

Frames 0000, 0013, and 0022 were inspected. The large irregular afro
silhouette, high forehead, thick brows, beard, white shirt, rich brown skin
palette, and linework stayed visually stable. The observed movement is mainly
a blink and very small head/eye change. No approval was automatic: Carey must
watch the MP4 before it becomes a reusable episode motion asset.

## Next gate

If approved, use this clip as a baseline for character-idle posts and intro
cards. It does **not** establish that the same motion route can safely animate
new scene keyframes, dialogue, broad turns, or body actions. Those require an
approved anime anchor kit and per-shot review.
