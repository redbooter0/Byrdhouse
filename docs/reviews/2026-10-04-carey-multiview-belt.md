# Carey approved turnaround: view-aware local review

2026-10-04, current Windows PC. Carey approved the illustrated likeness in
the front, facing-right, back, and facing-left model sheets, then explicitly
said he dislikes the outfits. The garments are placeholders. This record
covers identity continuity, not wardrobe approval or proof that a new frame
is an exact replica.

## Locked inputs

`D:\ByrdHouse\assets\characters\carey-anime\turnaround-v1.json` binds the
approved base sheet, burgundy variant, enlarged head sheet, and original
close-up anchor to SHA256 hashes. The head sheet is `head-turnaround-v1.png`,
SHA256 `2feb5de44653c93b5a399dd9ef843284eca4f790514fcd47339267cf82a311df`.
Diagnostic crops are defined in `views-v2\manifest-v2.json`. The first
equal-quarter crop layout cut off profile faces and is **not** used. Version
2 keeps each approved face complete, though its side crops retain a small
strip of a neighboring drawing at one edge. Those strips are outside the
detected face boxes in the present measurements.

## Actual local measurements

`views-v2\inspection-v1.json` is the complete CPU examiner output. The
approved front crop was detected with confidence `0.827181` and had a
`0.868309` embedding similarity cue to the original approved close-up. The
facing-right and facing-left crops were also detected, with confidence
`0.662079` and `0.565687`. Their embedding cues **against the front close-up**
were only `0.428393` and `0.416813`. That comparison changes viewpoint, so it
does not mean Carey disapproved or that the approved profiles are wrong. The
rear view has no face to score; review its hair and body visually.

The new read-only `windows-local/studio/anime_view_review.py` takes an explicit
`--view` and compares a proposed image with the matching approved head view,
or with the original approved close-up for a three-quarter portrait.
It verifies the full head-sheet and crop hashes before inspecting the target;
it records the target hash, matched reference, feature deltas, and review
scope. It excludes the placeholder clothes and never edits pixels or grants
automatic approval. A same-file technical sanity check of the facing-right
crop returned similarity `1.0`, as expected, with
`automatic_approval: false`. That validates matching-reference selection,
not performance on a new generated scene. All `158` Studio tests passed,
including the five new matching-view tests.

The earlier scene swap `a3b1a4a04a2e2d7d7458e75a5f058ca3_1.png` exposed
why that distinction matters. It is a three-quarter close-up whose protected
hair/face pixels match the approved anchor. Comparing it to the head sheet's
straight-front drawing gave a `0.882618` similarity cue but falsely marked
afro width outside the review range (`0.197084` normalized difference).
Comparing the exact same still to the approved **three-quarter** anchor gave
`0.925440` and passed the hair/forehead/outline review screens; hair-width
difference fell to `0.014215`. Its thin light compositing edge remains a
visual flaw, and the still remains `needs_review`.

Run a view-specific check with the installed Python runtime, after choosing
the visible view of the proposed still:

```powershell
$env:PYTHONPATH='C:\Users\carey\Documents\ByrdHouse\runtime\venv\Lib\site-packages;D:\ByrdHouse\repo\windows-local\studio'
& 'C:\Users\carey\Documents\ByrdHouse\runtime\python\cpython-3.13.15-windows-x86_64-none\python.exe' 'D:\ByrdHouse\repo\windows-local\studio\anime_view_review.py' --target 'D:\ByrdHouse\media\images\YOUR_STILL.png' --view facing-right
```

The command writes `YOUR_STILL-anime-view-review.json` alongside the still.
Choose `front`, `facing-right`, `facing-left`, `back`, or `three-quarter`.
Select the **visible angle** rather than the nearest convenient file. A back check has no
face similarity number. This is an operator review aid; it is **not yet wired
into the Studio browser's automatic still job report**. Existing Studio
anchor reports remain front-anchor comparisons and must not reject a new side
profile solely for low front similarity.

## Next production gate

Use the approved views as identity/pose references for a local new-scene
keyframe. Preserve the illustrated face and afro while giving clothing a
separate editable treatment. An image model can copy garment pixels from a
reference, so isolate identity from wardrobe when qualifying that graph.
Examine a full-resolution still against its matching approved view and have
Carey review it before animation. The existing anchor-motion clip is a
technical test and still awaits visual approval. No rig, transparent sprite,
new-pose match, or trained Carey LoRA is claimed by this milestone.
