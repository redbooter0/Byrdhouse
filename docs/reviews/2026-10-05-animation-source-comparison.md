# Existing animation systems for the ByrdHouse show

Reviewed 2026-10-05 at Carey's request: investigate where existing animation
source code succeeds and fails, with Family Guy / Rick and Morty as the creative
reference for recognizable characters, recurring sets and comic cutaways.

## Production recommendation

Use a reusable 2D character rig for the repeatable dialogue scenes, with separate
mouth, eyes, brows, hair, hands, clothing and body controls. Keep the approved
Carey drawing as the character standard. Use the ChatGPT artwork already saved
on disk; the latest instruction requires all future production to be local,
with no subscriptions or paid services. Use local animation and compositing.
Continue Blender for editable assets, sets, cameras and the separate 3D-body goal.
Reserve diffusion video for optional short cutaways after frame-by-frame review.
This is an engineering recommendation, not a completed rig or speed benchmark.

There is no verified public source-code package for the named television shows
in this review. Toon Boom's own account describes Rick and Morty production with
Storyboard Pro and Harmony. Harmony is a useful production reference rather
than the open-source engine we should rebuild. Its documented character-rig
hierarchies, deformation and drawing substitutions are the reusable ideas.
Sources: [Toon Boom production account](https://www.toonboom.com/rick-and-morty-wins-its-first-emmy-and-the-case-for-2d-animation-series),
[Harmony rigging documentation](https://docs.toonboom.com/help/harmony-24/advanced/rigging/about-rig.html).

## Comparison

| Existing system | Where it succeeds | Where it fails or needs work for us | Decision |
|---|---|---|---|
| Blender Grease Pencil / armatures | Editable drawings in 3D space; local camera, scene and animation environment; already installed here | A PNG reference is not an articulated drawing. Parts, weights, turn drawings and expressions still need authoring. A flat sprite is not a full 3D Carey body. | First reuse candidate for the existing Blender lane. Verify actual installed API before scripting. |
| OpenToonz Plastic | Deforms a drawing through a mesh and skeleton; supports multiple skeletons for different drawings and keyframe timing | Deformation cannot invent hidden body surfaces or a convincing new head view. Large rotations need alternate drawings. Face stretching can alter likeness. | Strong existing 2D alternative; evaluate a short Carey blink/gesture before adding another main application. |
| Rhubarb Lip Sync | Produces mouth-cue timing from audio; Windows build, JSON/TSV/XML and OpenToonz-compatible switch output | It does not draw the mouth, provide emotional acting or guarantee correct phonemes. Requires prepared mouth art and review. | Preferred small lip-sync component after the mouth library exists. |
| ToonCrafter + existing Comfy wrapper | Interpolates between two cartoon keyframes; upstream offers sketch-guided examples | Upstream reports 16 frames at 512x320; base implementation ~24–27 GB, community variants lower. No verified RX 7900 XT result here. Identity and in-between quality are not guaranteed. | Optional experiment, not the dialogue production foundation. |
| Existing local Wan 2.2 5B | Already rendered a Carey image-to-video preview on this Radeon | Our 33-frame 384x576 test took 472.68 seconds and still has mouth softness / continuity flags | Keep for reviewed cutaways; not yet a fast, approved episode pipeline. |

Sources for the first four rows:
- [Blender Grease Pencil overview](https://www.blender.org/features/grease-pencil/)
  and [Grease Pencil armature documentation](https://docs.blender.org/manual/en/5.0/grease_pencil/modifiers/deform/armature.html).
  Search results exposed these official feature descriptions; direct page retrieval
  returned an error in this session, so no claim about a new 5.2 API is made.
- [OpenToonz Plastic documentation](https://opentoonz.readthedocs.io/en/latest/create_animations_using_plastic_tool.html)
  and [source repository](https://github.com/opentoonz/opentoonz).
- [Rhubarb source and usage](https://github.com/DanielSWolf/rhubarb-lip-sync).
- [ToonCrafter upstream](https://github.com/Doubiiu/ToonCrafter)
  and [existing ComfyUI wrapper](https://github.com/kijai/ComfyUI-DynamiCrafterWrapper).
  No AMD compatibility statement was found in the wrapper README checked here;
  absence of documentation is not proof it cannot run. No package was installed.
- Local Wan results: [native qualification](2026-10-04-native-wan-amd-qualification.md).

## Concrete first-shot acceptance test

Build a 6-second reaction shot at the existing ByrdHouse stoop: closed-mouth
idle, one blink, skeptical eyebrow lift, a small hand gesture and a held reaction.
Use the original Brambleton teal door / brick / potted plant cues. Keep wardrobe
independent so rejected costumes can be replaced without repainting the face.

Check that the face is crisp at delivery size, afro silhouette and forehead do
not wobble, eye spacing and nose shape do not drift, skin color stays stable,
mouth closes properly, and garment replacement leaves head/body identity intact.
Record actual render time and RAM/VRAM, then replay the same project offline.
Treat these as pass/fail review observations, never an invented similarity score.

For dialogue, author six basic mouth drawings plus useful optional F/V, L and
rest poses following Rhubarb's documented cue set; map cues to original Carey
art. Timing analysis can be automatic, while acting and facial continuity still
need review. The new six-expression sheet is not a phoneme/viseme library yet.

## Avoid repeating past failures

- Do not diffuse a replacement face on every frame of a dialogue shot.
- Do not claim a LoRA fixes hair, teeth, eyes and performance without a tested clip.
- Do not stretch one front drawing through a full turn; use the approved views.
- Do not call still-image camera motion facial animation or a rigged 3D body.
- Do not introduce a new CUDA-only stack into the functioning ROCm environment.
- Keep rejected generations out of training and approved-asset libraries.

The rigidity of a reusable rig can limit extreme action; use alternate drawings
or separately reviewed action shots for those moments. That tradeoff is preferable
for dialogue where recognizable Carey expressions matter more than arbitrary motion.
