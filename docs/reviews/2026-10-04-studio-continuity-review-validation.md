# Studio matching-view and complete-frame Carey checks

2026-10-04, Windows RX 7900 XT / 32 GB RAM. This extends the existing
matching-view examiner into the existing SQLite Studio queue and gallery.
It does not create a new image generator, train a model, edit the source
pixels, or approve likeness.

## What is deployed

An illustrated still or completed illustrated Carey clip now has a **visible
angle** selector and **Check likeness** button. Choices reuse the approved
front, facing-right, facing-left, rear and three-quarter references. The
three-quarter check uses the approved close-up; side checks use the head-sheet
profiles. Rear views have no face score and remain visually inconclusive.

`POST /api/anime-reviews` queues a CPU `anime_review` in the shared worker.
It reuses `anime_view_review.py`, `IdentityBelt` and `render_belt_report.py`;
`anime_continuity.py` only binds inputs, resumes reports, summarizes findings
and creates the separate diagnostic card. No new model, runtime, GPU graph,
CUDA package or custom-node pack was installed. Existing upstream source and
model provenance remains in the [native Wan record](2026-10-04-native-wan-amd-qualification.md),
[matching-view record](2026-10-04-carey-multiview-belt.md), and model manifest.

Video checking uses **every collected PNG**, not a frame glob or a five-frame
sample. It requires matching video/collection metadata, complete sequential
frame names, recorded hashes and the movie hash. It pins the approved sheet,
view, lock and manifest before queueing. Changed frames, video, reference or
cached reports fail closed. Review inputs are bound again before publishing.
The current bounded limit is 240 collected frames; live qualification here is
33 frames. Unknown photos and diagnostic reports cannot enter this anime
comparison; diagnostic images cannot become animation sources even if their
own report job is marked approved. Original job approval stays unchanged.

Each saved report includes outline, forehead, afro width/height, hairline and
lighting-sensitive skin brightness. Missing confidence or changed-angle cues
remain **inconclusive**. The gallery shows per-feature counts and a marked
diagnostic; **Complete frame findings** opens the hash-checked full report.
The enlarged comparison uses the selected approved view. Numbered markers
are clamped into the image canvas; gold boundaries are explicitly estimated.

## Actual local results

| Source | Review job | Result |
| --- | --- | --- |
| Wan Carey clip `3d6490df1abea740c499afcbca8befe7` | `ec685277f2aca0dc79e6c19d535bb06b` | All 33 frames examined against the approved three-quarter view. Afro width flagged at zero-based frames **5 and 7**; other five feature screens had no change flags or detection gaps. |
| Rejected new-scene still `15a745b5272cda3fe8c73f8b0ed41003` | `d595f02fa71fefc62b4aea9e967e5728` | Browser-button check completed in **8.08 s** warm. All six measured feature groups flagged; source remains rejected. |

The Wan width differences were `0.162619` and `0.166566` of face width,
just beyond the existing `0.16` review range. These are borderline cues that
can include segmentation/framing variation; they are not established identity
changes. The earlier five sampled frames missed these two flags. The rejected
still had outline error `0.068722`, forehead difference `0.143354`, hairline
difference `0.187111`, afro width/height differences `0.259480`/`0.241650`,
and median parsed skin brightness shift **+53.285** on the 0–255 scale.
Visual inspection agrees that it changed Carey's features and lightened him.

Both diagnostics were visually inspected at full size. The motion example
still has softer teeth/mouth and color fringing. Gold points also touch some
brow regions, exposing semantic-parser uncertainty: do not treat every point
as a precise hairline. Eyes, beard, tooth design and mouth sharpness are not
qualified by these six geometry/brightness screens. Automatic approval and
`identity_verified` remain false throughout. Clothes are excluded from this
likeness check; the previously approved sheets remain canon.

Stable artifacts:

- Full clip report: `D:\ByrdHouse\media\anime-reviews\ec685277f2aca0dc79e6c19d535bb06b\review.json`
- Clip diagnostic: `D:\ByrdHouse\media\images\ec685277f2aca0dc79e6c19d535bb06b_1.png`
- Rejected-still diagnostic: `D:\ByrdHouse\media\images\d595f02fa71fefc62b4aea9e967e5728_1.png`
- Each reviewed frame's full examiner output and SHA checkpoint are beside the report.
- Format-only revised diagnostics have `visualization_revision` metadata;
  original gallery diagnostics and cards remain as `gallery-visual-v1.*`.

## Live restart proof and timing

The full clip check was interrupted with **10** completed, hash-checkpointed
frame reports. Studio restarted through the saved launcher. The same job
resumed; all ten prior report hashes stayed identical and the remaining 23
frames completed. It never acquired a Comfy prompt ID. Comfy PID **24148**
remained unchanged and its GPU queue stayed empty. This proves **CPU review
restart**, not a live mid-render GPU restart.

The complete test spanned **298 seconds** between original claimed and
finished timestamps, including the forced restart. The prototype stopwatch
stored 194.46 s for the post-restart segment; that historical value is retained
in evidence. The deployed queue now includes the original claimed time after
CPU resumption, and the gallery displays separately computed wall duration.
Do not advertise a 194-second end-to-end benchmark. The parser stayed at
approximately 1.8 GB process working set during observed review samples;
this is an observation, not a peak or whole-system RAM benchmark.

Before/after proofs and both metadata cards are saved in
`D:\ByrdHouse\external\workflows\comfy-wan22-5b\full-clip-review-validation.json`
and `full-clip-restart-before.json`. This full check adds several minutes for
this short clip, so it is an explicit review action rather than an automatic
delay on every generation.

## Validation and remaining work

The full Studio suite passes **173 tests**. Eight new integration tests cover
all-frame collection, view/photo/index limits, source/reference/movie changes,
rear-view/no-face limits, unchanged source approval/pixels, no Comfy requests,
CPU restart caching, elapsed-time carryover and tampered-cache refusal. JS
syntax passes. Browser verified the angle selector, check button, queued
progress, completed feature counts, report links, loaded diagnostic images
and absence of keep/animate actions on diagnostics. The matched-reference
endpoint returns the approved view. Source/deployed copies match.

Next: improve estimated hairline localization where brow points leak in,
then use the existing mesh/semantic face-zone lane to qualify target-aligned
edits. Exact regenerated poses, sharp eye/mouth/beard detail, clean afro scene
edges, accepted motion and a finished episode remain unqualified. Do not
reinstall the runtime or repeat the rejected new-scene settings to advance.
