# Carey is the subject

Every new character generation in this installation requires a local Carey photo.
Carey is a Black man; preserve the reference's skin tone and facial geometry,
natural hair, and facial hair. A racial description is not a substitute for likeness.
Scene direction may change pose, expression, clothing, environment, and art style.

The Studio offers two separate local routes:

- SDXL Exact photo edit is the default. It encodes the original portrait after an
  aspect-correct scale and uses conservative denoise to keep facial geometry intact.
- FLUX.2 Klein 4B photo editing encodes the actual reference image into the graph.
  It uses four steps for more aggressive scene changes. SDXL LoRAs are excluded.
- SDXL Carey v2 LoRA is available as an explicit creative-variation route. The old
  full-image IP-Adapter route is retired because it copied reference lighting and
  produced warped faces.

Neither route automatically verifies likeness. Inspect the face against the original,
including skin tone, nose, eyes, lips, jaw, hairline, and facial hair before keeping it.
Reject candidates that change ethnicity or identity. Rejected files are retained but
hidden from the default gallery and omitted from pack exports.

Recipes cover expressions, camera angles, outfits, cinematic animation stills, and
anime character concepts. Each candidate receives its own seed and metadata card.
These are independent stills, not consecutive frames of a coherent action sequence.

Downloaded packs include PNGs, metadata, and a Blender builder. The resulting .blend
packs all source images and contains editable camera motion. Facial/body animation
requires a subsequent animation workflow and approved stills.
