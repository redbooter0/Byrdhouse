# Carey identity LoRA staging

`profiles/me/references/` is the authoritative private reference library. Do
not manually reorganize it. The helper below stages only a small, reproducible
subset into this folder for training, and this whole staged-image area is
ignored by Git.

## Source folders

- `../references/me_photo_*.jpg` - real Carey photos. These are the identity
  anchor and must remain the dominant training signal.
- `../references/ai_identity_*.png` - generated studio-angle identity renders.
  These are never treated as real anchors; the current hybrid diagnostic uses
  them only as a lower-weight support bucket for pose coverage.
- `../references/generated_anime_cartoon/` - Carey-only generated anime and
  cartoon scenes. The hybrid diagnostic uses only a visually reviewed subset
  of the anime lane at the lowest repeat weight; it never uses targets,
  `rejected/`, or the whole library at once.

The supplied Gojo, Vegeta, and Luffy target images are evaluation targets.
They must never be added to either training folder.

## Current safe sequence

1. Keep adding clear real photos to `../references/`: front, both three-quarter
   views, profile, neutral, and smile. Aim for 12-16 trainable real photos and
   keep 4 separate photos for evaluation. Face should be large, uncovered, and
   sharp.
2. When ready, stage the real-photo identity set:

   ```powershell
   $env:BYRDHOUSE_ROOT = 'E:\ByrdHouse'
   & 'E:\ByrdHouse\Generators\ComfyUI\.venv\Scripts\python.exe' `
     .\scripts\prepare-carey-lora-dataset.py --mode identity --replace
   ```

   For the compact starter set, add local face crops before the diagnostic run.
   This does not alter any source photo; it only creates git-ignored 512px
   close-portrait copies in the staging folder:

   ```powershell
   & '.\scripts\train-carey-meina-lora.ps1' -Mode identity -FaceCrops -PrepareOnly -ReplaceDataset
   ```

   Train the diagnostic with the text encoder enabled. The custom
   `careybh person` trigger needs this association; U-Net-only candidates were
   technically valid but did not hold Carey likeness in local target tests.

   ```powershell
   & '.\scripts\train-carey-meina-lora.ps1' -Mode identity -FaceCrops -TrainTextEncoder -Steps 900 -StopComfy -ReplaceDataset
   ```

   The current eight-real-photo diagnostic is still rejected. Treat 12-16
   clear, distinct real photos as the next minimum for another identity pass;
   do not keep retraining the same small set.

3. The current local experiment is a geometry-first `studio-core` candidate:
   24 real/crop pairs at repeat 5 and 18 clean studio-view/crop pairs at
   repeat 6. It intentionally removes the looser anime scenes after the
   hybrid candidate only produced broad features. It is a private preview only
   and still must visibly pass all four targets before any promotion.

   ```powershell
   & '.\scripts\train-carey-meina-lora.ps1' `
     -Mode studio-core -FaceCrops -TrainTextEncoder -Steps 1200 -StopComfy -ReplaceDataset
   ```

4. Use `scripts/validate-carey-anime-lora.py` to render fixed-seed Gojo,
   Vegeta, and both Luffy targets from a candidate. The helper copies only an
   explicitly named `_preview` file into ComfyUI and never changes the deployed
   recipe model.

The trigger phrase in every caption is `careybh person`. Do not rename it
between training and generation.
