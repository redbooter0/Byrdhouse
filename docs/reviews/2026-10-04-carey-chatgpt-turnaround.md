# Carey anime turnaround and wardrobe candidates — 2026-10-04

## Carey approval update

Carey reviewed the generated models in this chat and said, “ALL THE MODALS
ARE CORRECT AND LOOK EXACTLY LIKE ME.” The three sheets were copied to stable
`-v1.png` filenames and hash-locked in
`D:\ByrdHouse\assets\characters\carey-anime\turnaround-v1.json` as the
**approved illustrated multi-view likeness**. Carey separately said he does
not like the outfits; the white-shirt and burgundy looks are **wardrobe
placeholders**, not costume canon. This approval is a visual character-design
decision, not evidence of a trained LoRA, editable rig, clean alpha cutout, or
automatic identity fidelity in new frames. The extra stud noted below is a
continuity detail for future frame work; it does not negate Carey's expressed
likeness approval of the model sheets.

## Purpose and status

Carey asked for a fully recognizable Carey model from front, back, and both
sides that can be animated and dressed differently. These are **2D image
generation candidates**, not an approved character rig or a trained likeness
model. The owner-approved `anchor-v1.png` remains the only show canon. Do not
train on, animate into an episode, or silently replace the canon with these
generated sheets before Carey checks the face at full size.

## Saved assets

| Asset | SHA256 | Resolution | Review |
|---|---|---|---|
| `D:\ByrdHouse\assets\characters\carey-anime\turnaround-base-v1-candidate.png` | `21c03bf12f9f0a54fe38a2c65f4815a13044f29be09c92e8eb34fe38086c0b2d` | 1536×1024 | Needs Carey likeness review |
| `D:\ByrdHouse\assets\characters\carey-anime\turnaround-burgundy-v1-candidate.png` | `e604de821effdee2c55ff0133b78b7d8456df3df9f2bd3832ae8809ca05855eb` | 1536×1024 | Needs Carey likeness review |
| `D:\ByrdHouse\assets\characters\carey-anime\head-turnaround-v1-candidate.png` | `2feb5de44653c93b5a399dd9ef843284eca4f790514fcd47339267cf82a311df` | 2172×724 | **Continuity flaw:** front has two ear studs, unlike canon's one. Do not use as final. |
| `D:\ByrdHouse\assets\characters\carey-anime\rejected\head-turnaround-earring-edit-v2-rejected.png` | `e733cbd557e7169e760b29b2de4731c9b57c3788fc130e1a154239dbdb482641` | 2172×724 | Rejected: a targeted edit failed to remove the extra stud. |
| `D:\ByrdHouse\assets\characters\carey-anime\rejected\front-alpha-glow-v1-rejected.png` | `61ef9683b6a8a8289e24670e1eb8f97cc1da8316964c3c2d99774c3a2115e674` | 1024×1536 | Rejected animation sprite: transparency exists but a glow/soft fringe extends beyond the body, and the face has an extra ear stud. |
| `D:\ByrdHouse\assets\characters\carey-anime\rejected\front-alpha-glow-v2-rejected.png` | `3f69a8fafb5ee222417bb7dc29c27830f51c5da5a319421d63e0291a16bc7e6e` | 1024×1536 | Rejected: targeted transparent-cutout edit did not remove glow or extra stud. |

Image panels are ordered front, facing right, back, facing left. A side label
must describe where Carey faces on-screen; anatomical left/right can be
ambiguous without a verified ear/shoulder guide. Both full-body sheets use the
same scale and near-identical pose. The second changes a plain white T-shirt,
charcoal pants, and sneakers to a burgundy zip hoodie, black shirt, indigo
jeans, and the same sneakers. At the top 180 pixels of the four matching
panels, mean absolute RGB difference between outfits was 3.83, 2.86, 2.60,
and 2.83 on a 0–255 scale. That is a continuity cue, **not** proof that every
face pixel or facial feature stayed identical.

No actual rear-view photo was supplied. Back-of-head and back-of-body details
are inferred by image generation and require Carey confirmation.

## Inputs and source of generation

- [OpenAI imagegen skill](C:/Users/carey/.codex/skills/.system/imagegen/SKILL.md)
  and built-in ChatGPT image generation were used for all artwork. This did
  **not** run on the local RX 7900 XT.
- Approved anime anchor: `D:\ByrdHouse\assets\characters\carey-anime\anchor-v1.png`,
  SHA256 `2f85df9f6efa92915b57d666dbd2c3e3467ae91e540f603156bc4084c0ff4640`.
- Real face/smile photo: `C:\Users\carey\.codex\codex-remote-attachments\01a0c685-4a89-7132-97bb-776f22f50f46\08DF5AF7-1D63-493F-A567-5069F1224749\7-Photo-7.jpg`,
  SHA256 `3b19302773ca2d262f0b5ef33f019a060f9c486ed8d9ad010083a05cfd139391`.
- Real full-body pose photo: `C:\Users\carey\.codex\codex-remote-attachments\01a0c685-4a89-7132-97bb-776f22f50f46\08DF5AF7-1D63-493F-A567-5069F1224749\10-Photo-10.jpg`,
  SHA256 `e6a7a03c94634a1fd5ff45ead9186a8707f4be754b036bc6fdc6e29a39f5c5b5`.

## Reusable prompt set

Base turnaround: use the approved closeup as the exact illustration/face/hair
anchor and the two real photos for facial structure and full-body proportions.
Generate one consistent adult Black Carey in four full-body orthographic
standing views (front, facing right, back, facing left), equal scale, full feet,
plain white T-shirt, charcoal pants, dark sneakers, neutral sheet background.
Hold the wide irregular afro, high natural forehead, warm medium-brown skin,
long-oval face, distinctive brows/eyes/nose/smile, and connected close beard.

Wardrobe variant: edit the base turnaround, keep the four panels, Carey identity,
pose, scale, face, afro, skin, hands, and shoes as unchanged as possible. Change
**only** the clothes to an open deep-burgundy zip hoodie, black crew-neck shirt,
and dark indigo jeans. Use both the base turnaround and approved closeup as
references. One imagegen call per distinct outfit; keep each output with its
source and hash. Never feed an unreviewed outfit variant back as a primary
identity reference.

Head turnaround: use the approved closeup as stronger identity reference than
the base sheet and the real smiling photo for anatomy. Four large head-and-
shoulder views, same hairstyle/skin/face and dark shirt. The first result is
visually useful for comparing afro and facial profile, but the extra ear stud
is a concrete failure. A follow-up one-change edit did not correct it.

Transparent sprite trial: the full-body front panel and approved closeup were
used to ask imagegen for a truly transparent, single Carey cutout. The generated
PNGs do contain an alpha channel, but both show a perceptible exterior glow on
dark preview and the face acquired a second ear stud. The cleanup edit failed.
These files are retained only under `rejected`, not as production layers.

## What the images do and do not establish

The base and outfit sheets provide a stable *view + garment* recipe. They are
not an editable skeleton, mesh, clean transparent cutout, layered garment file,
or LoRA. Clothing changes
currently require another identity-preserving image edit and a human likeness
check. For animation, next make clean, approved per-view keyframes and an
expression/mouth sheet, then rig or interpolate only after continuity review.
The earlier 2.93-second anchor motion is a separate preview and remains
`needs_review`; no new turnaround animation has been qualified.

Carey should compare the front closeup with the locked anchor and real photos,
especially forehead height, face length/outline, nose bridge, eyes, smile,
mustache, beard line, and afro volume. Fix the ear stud and any feature drift
before promoting a sheet to canon or training an anime LoRA.
