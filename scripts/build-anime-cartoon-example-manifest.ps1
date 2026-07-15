$ErrorActionPreference = "Stop"

$outputRoot = "E:/ByrdHouse/profiles/me/references/generated_anime_cartoon"
$manifestPath = Join-Path $outputRoot "manifest.json"

$identityReferences = @(
    "E:/ByrdHouse/profiles/me/references/me_photo_02.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_03.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_04.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_08.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_10.jpg"
)

$identityContract = @"
All identity reference images show the same adult Black male. Preserve his recognizable facial structure, deep-brown skin tone, age, masculine features, natural facial proportions, and overall identity. Keep him clearly male. Use the references only for his identity and appearance; do not add a second person. Keep the face visible and unobstructed. Maintain natural skin texture and avoid lightening or changing his ethnicity. No female traits, no generic replacement face, no text, no logos, no watermark, and no social-media interface.
"@.Trim()

$families = @(
    [ordered]@{ slug = "modern-shonen"; style = "modern cinematic shonen-inspired 2D anime, crisp linework, dynamic cel shading, dramatic effects"; scenes = @(
        "standing on a storm-lit rooftop as wind moves his jacket, distant city towers and electric clouds",
        "charging forward through a shattered canyon with energy ribbons and flying stone fragments",
        "calmly facing a giant moon above a mountain shrine, heroic low-angle composition",
        "training alone beside a roaring waterfall in a lush hidden valley",
        "walking through a lantern-lit tournament entrance with the arena glowing behind him"
    )},
    [ordered]@{ slug = "retro-90s-anime"; style = "hand-painted 1990s cel anime, inked outlines, analog film grain, painted backgrounds"; scenes = @(
        "waiting at a neon train platform at midnight while rain reflects colored signs",
        "driving a compact futuristic coupe along a coastal highway at sunset",
        "inside an old video arcade surrounded by glowing cabinets and checkerboard flooring",
        "leaning against a motorcycle above a sprawling night city",
        "watching meteor trails from a quiet apartment balcony"
    )},
    [ordered]@{ slug = "fantasy-anime"; style = "high-detail fantasy adventure anime illustration, elegant linework, painterly scenery, cinematic light"; scenes = @(
        "as a green-cloaked swordsman in an ancient moonlit forest with mossy ruins",
        "crossing a crystal bridge above a glowing blue ravine",
        "standing before a colossal sealed temple door covered in vines",
        "riding through golden grasslands beneath floating islands",
        "resting beside a campfire in a misty enchanted woodland"
    )},
    [ordered]@{ slug = "cyberpunk-anime"; style = "cyberpunk anime key art, sharp graphic silhouettes, luminous neon, detailed rainy city atmosphere"; scenes = @(
        "wearing a black tech jacket in a crowded neon alley after rain",
        "overlooking a megacity from a glass skybridge with holographic traffic below",
        "sitting inside a high-speed transit car with violet and cyan window light",
        "walking through a night market filled with drones and glowing umbrellas",
        "standing in a rooftop garden surrounded by futuristic towers and low clouds"
    )},
    [ordered]@{ slug = "mecha-anime"; style = "polished sci-fi mecha anime, technical detail, bold cel shading, cinematic scale"; scenes = @(
        "as a pilot in a hangar before a towering blue-and-gold machine",
        "inside a luminous cockpit with starfields reflected across the canopy",
        "crossing a lunar base runway while giant machines launch behind him",
        "standing on a carrier deck above a planet's atmosphere",
        "in a maintenance bay holding his helmet while sparks fall in the background"
    )},
    [ordered]@{ slug = "supernatural-noir"; style = "supernatural noir anime, moody shadows, restrained color, expressive ink lines, cinematic mystery"; scenes = @(
        "investigating an abandoned subway tunnel lit by floating blue spirits",
        "beneath a streetlamp in heavy rain as shadow creatures gather far behind",
        "inside an old library where glowing symbols drift from an open book",
        "walking through a fog-covered cemetery at dawn",
        "standing in a candlelit hotel corridor with impossible doors"
    )},
    [ordered]@{ slug = "slice-of-life-anime"; style = "warm contemporary slice-of-life anime, clean linework, soft cel shading, richly observed everyday scenery"; scenes = @(
        "enjoying coffee by a large window during a gentle morning rain",
        "shopping at a colorful outdoor market under summer sunlight",
        "reading beneath cherry blossoms beside a quiet river",
        "cooking dinner in a cozy apartment kitchen at golden hour",
        "walking home through a neighborhood as fireflies appear at dusk"
    )},
    [ordered]@{ slug = "sports-anime"; style = "high-energy sports anime illustration, athletic motion, speed lines, vivid stadium lighting"; scenes = @(
        "dribbling a basketball through defenders in a packed indoor arena",
        "launching from the starting blocks on a rain-slick track",
        "training with battle ropes in a dramatic modern gym",
        "celebrating under stadium lights after a championship play",
        "running alone through city streets before sunrise"
    )},
    [ordered]@{ slug = "samurai-anime"; style = "historical samurai anime drama, expressive brush textures, detailed period clothing, atmospheric landscapes"; scenes = @(
        "wearing dark indigo robes on a bamboo path in drifting mist",
        "standing on a wooden bridge beneath red autumn leaves",
        "walking through a mountain village during the first snow",
        "resting beside a temple bell at sunrise",
        "crossing a windswept field beneath a stormy sky"
    )},
    [ordered]@{ slug = "post-apocalyptic-anime"; style = "post-apocalyptic anime concept art, weathered detail, dramatic skies, cinematic cel-painted finish"; scenes = @(
        "exploring an overgrown city boulevard with abandoned vehicles",
        "standing atop a ruined tower while birds circle distant green skyscrapers",
        "crossing a desert highway beside a rugged solar-powered vehicle",
        "inside a reclaimed subway station lit by gardens and lanterns",
        "walking through a flooded museum where sunlight enters through the roof"
    )},
    [ordered]@{ slug = "western-action-cartoon"; style = "premium western 2D action cartoon, bold shapes, clean linework, expressive posing, cinematic color design"; scenes = @(
        "leaping between rooftops above a colorful coastal city",
        "discovering an underground crystal cavern with an adventurous grin",
        "driving a desert buggy through a canyon chase",
        "standing in a secret headquarters surrounded by glowing maps",
        "facing a thunderstorm from the bow of an airship"
    )},
    [ordered]@{ slug = "graphic-novel"; style = "contemporary graphic novel illustration, strong ink work, halftone accents, dramatic panel-like composition"; scenes = @(
        "walking alone through a rain-soaked downtown intersection",
        "standing beneath a fire escape with hard afternoon shadows",
        "on a subway platform as an express train blurs past",
        "inside a boxing gym wrapping his hands before training",
        "on a rooftop at sunrise with the city rendered in bold silhouettes"
    )},
    [ordered]@{ slug = "saturday-morning-cartoon"; style = "bright Saturday-morning adventure cartoon, playful proportions, energetic poses, colorful painted backgrounds"; scenes = @(
        "discovering a jungle temple with a glowing map in hand",
        "surfing across clouds on a small magical board",
        "piloting a cheerful compact spaceship through an asteroid field",
        "exploring a candy-colored alien village",
        "escaping a crumbling castle across a rope bridge"
    )},
    [ordered]@{ slug = "animated-feature-3d"; style = "high-end stylized 3D animated feature character, expressive but recognizable face, cinematic global illumination"; scenes = @(
        "standing in a luminous forest filled with oversized blue flowers",
        "walking through a bustling fantasy port at sunset",
        "inside a cozy observatory beneath a rotating star map",
        "crossing a snowy village square with warm windows glowing",
        "on a cliff overlooking an ocean filled with floating lanterns"
    )},
    [ordered]@{ slug = "claymation"; style = "handcrafted claymation character and miniature set, tactile fingerprints, stop-motion lighting, charming realism"; scenes = @(
        "in a tiny greenhouse tending enormous colorful plants",
        "waiting at a miniature roadside diner during a thunderstorm",
        "exploring a handcrafted cardboard spaceship interior",
        "walking through a clay forest covered in autumn leaves",
        "standing in a whimsical workshop filled with gears and tools"
    )},
    [ordered]@{ slug = "watercolor-storybook"; style = "expressive watercolor-and-ink storybook illustration, textured paper, luminous washes, gentle linework"; scenes = @(
        "crossing stepping stones through a quiet misty river",
        "sitting beneath an enormous old tree filled with small lanterns",
        "walking toward a hilltop village at sunrise",
        "sailing a small boat through clouds and constellations",
        "resting beside a field of wildflowers under a vast blue sky"
    )},
    [ordered]@{ slug = "chibi-anime"; style = "polished chibi anime character art, compact proportions, recognizable facial traits, colorful detailed environment"; scenes = @(
        "running a tiny ramen shop during the evening rush",
        "exploring a miniature fantasy dungeon with an oversized lantern",
        "playing basketball on a bright neighborhood court",
        "camping beside a sparkling lake beneath the stars",
        "piloting a comically small robot through a futuristic city"
    )},
    [ordered]@{ slug = "rubber-hose-cartoon"; style = "vintage 1930s-inspired rubber-hose cartoon, black-and-cream ink, film texture, lively hand-drawn motion"; scenes = @(
        "dancing down a musical city street as buildings bounce to the rhythm",
        "steering a tiny riverboat through exaggerated waves",
        "running through a surreal clock factory",
        "serving pies in a lively old-fashioned cafe",
        "exploring a moon made of theatrical painted scenery"
    )},
    [ordered]@{ slug = "pixel-art"; style = "high-detail 16-bit pixel art portrait scene, carefully limited palette, readable sprite-like character, layered parallax scenery"; scenes = @(
        "standing at the entrance to a glowing forest dungeon",
        "on a neon rooftop above a cyber city",
        "inside a cozy inn beside a crackling fireplace",
        "crossing a frozen mountain pass during snowfall",
        "on a basketball court during a dramatic final possession"
    )},
    [ordered]@{ slug = "urban-graffiti-cartoon"; style = "bold urban graffiti cartoon illustration, energetic linework, spray-paint textures, saturated color, stylish character design"; scenes = @(
        "posing beside a vibrant mural beneath an elevated train",
        "skating through a colorful city plaza at sunset",
        "performing on a rooftop surrounded by speaker stacks and painted walls",
        "walking through a tunnel covered in luminous abstract murals",
        "standing on an outdoor basketball court after rain with city lights reflected on the ground"
    )}
)

$items = [System.Collections.Generic.List[object]]::new()
$index = 1

foreach ($family in $families) {
    $sceneIndex = 1
    foreach ($scene in $family.scenes) {
        $id = "{0:D3}" -f $index
        $filename = "${id}_$($family.slug)_$('{0:D2}' -f $sceneIndex).png"
        $prompt = @"
Use case: identity-preserve
Asset type: reusable anime/cartoon scene example for the ByrdHouse application
Primary request: Transform the referenced man into a finished illustrated character scene.
Input images: all supplied images are identity references of the same male subject.
Scene/backdrop: $scene.
Subject: the same recognizable adult Black male from the references, alone in the scene.
Style/medium: $($family.style).
Composition/framing: polished vertical 4:5 character portrait, waist-up or three-quarter view unless the action requires full body; face remains clearly readable.
Constraints: $identityContract
Avoid: identity drift, lighter skin, changed ethnicity, feminine facial features, extra people, duplicate body parts, malformed hands, unreadable face, photographic social-media framing, text, logos, watermark.
"@.Trim()

        $items.Add([ordered]@{
            id = $id
            family = $family.slug
            scene_number = $sceneIndex
            filename = $filename
            prompt = $prompt
            status = "pending"
        })
        $sceneIndex++
        $index++
    }
}

$manifest = [ordered]@{
    version = 1
    title = "ByrdHouse Anime and Cartoon Identity Examples"
    count = $items.Count
    identity_references = $identityReferences
    identity_contract = $identityContract
    output_root = $outputRoot
    generator = "OpenAI built-in image generation"
    items = $items
}

New-Item -ItemType Directory -Force $outputRoot | Out-Null
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 $manifestPath
Write-Output "Wrote $($items.Count) prompts to $manifestPath"
