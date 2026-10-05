# ByrdHouse — animated-short show bible

**Production direction, 2026-10-03.** ByrdHouse is an original adult animated
sitcom for vertical social shorts. It uses a recognizable town, a recurring
ensemble, and quick side-story cutaways. The structure may carry the energy of
classic adult sitcoms, but the setting, characters, dialogue, artwork, jokes,
and episode plots are original to ByrdHouse.

## 1. The show promise

Each 15–45 second short begins with an ordinary problem in the town of
**Brambleton**, escalates through a surprising memory or side-story, and lands
on a reversal that can stand alone in a feed while also building the series.

The show should feel warm, sharp, a little chaotic, and grounded in Black
friendship, neighborhood life, work ambitions, music, sports, family, and
creative hustle. It never turns Carey into a generic Black character or swaps
his identity for a stock face.

## 2. Canon lead — Carey

The owner-supplied illustrated source is the visual canon at:

`D:\ByrdHouse\assets\characters\carey-anime\anchor-v1.png`

SHA256: `2f85df9f6efa92915b57d666dbd2c3e3467ae91e540f603156bc4084c0ff4640`

It is also registered locally as `carey-anime-anchor`. It defines the lead’s
illustrated appearance for episode work:

| Feature | Canon rule |
|---|---|
| Skin | Rich medium-brown skin with warm dimensional cel shading; never lighten or substitute it. |
| Hair | Large natural black afro, wide and irregular at the silhouette; preserve the high forehead and natural curl boundary. |
| Face | Long-oval face, thick dark brows, warm almond-shaped brown eyes, narrow rounded nose, broad smiling mouth. |
| Facial hair | Neat short mustache and connected close beard that frames the jaw. |
| Detail | Small silver stud in the left ear. |
| Line/color language | Clean dark ink lines, two-to-three tone cel shading, strong readable silhouette, warm off-white or story-driven backgrounds. |

The anchor is a **character reference**, not proof that a new frame is a perfect
real-life replica. New frames must be checked against it before they become
episode assets.

Carey approved the generated front/facing-right/back/facing-left body sheet
and enlarged head sheet on 2026-10-04 as an illustrated likeness of himself.
Their stable files and hashes are in
`D:\ByrdHouse\assets\characters\carey-anime\turnaround-v1.json`.
The white-shirt and burgundy outfits shown on those sheets are placeholders:
Carey dislikes them and wants the wardrobe changed later. Retain the approved
face, afro, hairline, skin and body proportions while changing clothing.
The sheets are not yet a rig or a trained identity model.

## 3. Brambleton — the recognizable town

The town gives every short a home base. Reuse these locations, camera views,
and color cues so viewers recognize ByrdHouse before a character speaks.

| Location | Screen function | Recurring visual cue |
|---|---|---|
| ByrdHouse stoop | Opening arguments, arrivals, neighbor interruption | Brick rowhouse, teal front door, crooked gold house number, potted plant. |
| The Stoplight Bodega | Rumors, snacks, fast setup scenes | Yellow awning, buzzing red-blue OPEN sign, cramped counter. |
| Kestrel Court | Basketball, late-night talks, challenges | Faded mural, chain net, city lights behind the hoop. |
| The Loop bus stop | Transit jokes and chance meetings | Blue circular route sign, bench ads, rain reflections. |
| Auntie Lila’s lounge | Family and advice scenes | Green velvet chairs, framed local photos, warm lamps. |
| Brambleton Overlook | Emotional button or skyline cutaway | Hilltop rail, river lights, recognizable tower antenna. |

## 4. Original recurring ensemble

These are starting roles, not copies of any existing television cast:

| Character | Role in the short |
|---|---|
| Carey | The creative lead: confident idea-starter whose plans run one step ahead of reality. |
| Nia Vale | Practical producer and neighbor who turns vague ideas into actual plans. |
| Mo Rivers | Carey’s competitive friend; every minor event becomes a championship. |
| Auntie Lila | The neighborhood truth-teller, warm until someone ignores obvious advice. |
| Dev Kim | Bodega owner and accidental information hub with calm, dry reactions. |

Every character needs a separate approved reference sheet before recurring
episode generation. Do not train a group LoRA from unreviewed generations.

## 5. Short-form episode grammar

1. **0–2 s — Town stamp.** A recognizable Brambleton location plus Carey’s
   silhouette.
2. **2–8 s — Simple premise.** One clear want or disagreement.
3. **8–18 s — Escalation.** A friend reframes the problem.
4. **18–28 s — ByrdFlash cutaway.** A 2–5 second imagined memory, absurd
   comparison, or alternate outcome that directly exposes the joke.
5. **28–40 s — Return and reversal.** Back to the original location; the
   cutaway creates the payoff.
6. **Last 1–2 s — Visual tag.** A repeatable Brambleton detail, reaction, or
   sound cue that can bridge into the next short.

The cutaway is always motivated by the current conversation. It must have its
own original setup and punchline; never reproduce a specific scene, character,
or joke from another show.

## 6. First five social-short themes

| Short | Premise | ByrdFlash cutaway | Main location |
|---|---|---|---|
| The Perfect Hook | Carey tries to find the perfect first second for a video. | A fake focus group made of his future selves disagrees. | ByrdHouse stoop |
| Court of Public Opinion | A harmless basketball debate turns into a town tribunal. | Mo imagines himself accepting a trophy for “Most Correct.” | Kestrel Court |
| Bodega Loyalty Points | Dev explains a rewards system that makes no sense. | Carey visualizes the points as a heist map. | Stoplight Bodega |
| Rain Check | The Loop bus is late, so everybody tells a different version of why. | Each version appears as a different weather disaster. | Loop bus stop |
| The Overlook | A motivational photo shoot gets derailed by a very honest group chat. | The group chat appears as a tiny stage production. | Brambleton Overlook |

## 7. Local asset pipeline

1. Start from the locked Carey anime anchor, then make an **approved anchor
   kit**: front close-up, 3/4 left, 3/4 right, profile, full body, expression
   sheet, and outfit sheet.
2. Generate one controlled keyframe per shot with a dedicated pose reference;
   keep the Carey anchor, prompt identity block, model, seed, and pose source
   in its metadata.
3. Run the read-only belt: similarity cue plus forehead/hairline/jaw-outline
   overlays. Reject frames with a changed afro silhouette, flattened forehead,
   generic face, softened eyes, or altered beard/mouth.
4. Repair face detail only on a reviewed winner. A full-body frame with a small
   face is never animation-ready without crop-scale inspection.
5. Animate only approved keyframes. Keep the original keyframe and animation
   side-by-side; reject motion that changes the face or hair design.
6. Export vertical 1080×1920 masters and derive the feed crop from that master.

## 8. Current technical decision

The tested PuLID/RealVisXL photo route remains a private research route and is
rejected for ByrdHouse production: its latest result measured 0.365440 against
the real Carey reference and visibly genericized the face. Anime production
will use a dedicated SDXL anime checkpoint plus the owner-supplied illustrated
anchor, pose control, crop-scale face review, and a future approved anime
character LoRA. The existing fast photoreal checkpoint is not the art-directing
base for episodes.
