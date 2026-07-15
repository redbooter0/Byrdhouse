$ErrorActionPreference = "Stop"

$outputRoot = "E:/ByrdHouse/profiles/me/references/generated_anime_cartoon"
$manifestPath = Join-Path $outputRoot "manifest_101_200.json"
$existingManifestPath = Join-Path $outputRoot "manifest.json"

$identityReferences = @(
    "E:/ByrdHouse/profiles/me/references/me_photo_21.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_22.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_01.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_04.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_10.jpg"
)

$anime = @(
    "Solo Leveling",
    "Dandadan",
    "Frieren: Beyond Journey's End",
    "The Apothecary Diaries",
    "Vinland Saga",
    "Tokyo Ghoul",
    "Tokyo Revengers",
    "Sword Art Online",
    "Re:ZERO -Starting Life in Another World-",
    "Steins;Gate",
    "Dr. Stone",
    "Assassination Classroom",
    "The Seven Deadly Sins",
    "Parasyte: The Maxim",
    "Blue Exorcist",
    "Noragami",
    "Bungo Stray Dogs",
    "Mashle: Magic and Muscles",
    "Kaiju No. 8",
    "Hell's Paradise",
    "The Promised Neverland",
    "Made in Abyss",
    "Delicious in Dungeon",
    "Cyberpunk: Edgerunners",
    "Castlevania",
    "Record of Ragnarok",
    "Baki",
    "Initial D",
    "Rurouni Kenshin",
    "Hellsing Ultimate",
    "Fate/stay night: Unlimited Blade Works",
    "Fate/Zero",
    "Puella Magi Madoka Magica",
    "Cardcaptor Sakura",
    "Food Wars! Shokugeki no Soma",
    "The Disastrous Life of Saiki K.",
    "Monster",
    "Black Lagoon",
    "Psycho-Pass",
    "Ranking of Kings",
    "Beastars",
    "Saint Seiya",
    "Mobile Suit Gundam Wing",
    "Beyblade",
    "Yu-Gi-Oh!",
    "Case Closed",
    "Doraemon",
    "Lupin the Third",
    "Captain Tsubasa",
    "Astro Boy"
)

$westernAnimation = @(
    "Family Guy",
    "South Park",
    "Futurama",
    "Bob's Burgers",
    "Rick and Morty",
    "BoJack Horseman",
    "Archer",
    "King of the Hill",
    "American Dad!",
    "The Boondocks",
    "Invincible",
    "Arcane",
    "Star Wars: The Clone Wars",
    "Batman: The Animated Series",
    "Batman Beyond",
    "Justice League Unlimited",
    "X-Men '97",
    "Spider-Man: The Animated Series",
    "Static Shock",
    "Phineas and Ferb",
    "Gravity Falls",
    "Kim Possible",
    "The Proud Family",
    "DuckTales",
    "Darkwing Duck",
    "Gargoyles",
    "Bluey",
    "Looney Tunes",
    "Scooby-Doo, Where Are You!",
    "Tom and Jerry",
    "The Flintstones",
    "The Jetsons",
    "Peanuts",
    "Garfield",
    "The Smurfs",
    "He-Man and the Masters of the Universe",
    "ThunderCats",
    "Transformers: Prime",
    "My Little Pony: Friendship Is Magic",
    "Miraculous: Tales of Ladybug & Cat Noir",
    "Toy Story",
    "The Incredibles",
    "Frozen",
    "Moana",
    "The Lion King",
    "Shrek",
    "Spider-Man: Into the Spider-Verse",
    "Despicable Me",
    "Kung Fu Panda",
    "How to Train Your Dragon"
)

$hairstyles = @(
    "short natural curls with a clean tapered fade",
    "compact rounded natural afro with tapered sides",
    "large soft natural afro with individually readable coiled texture",
    "medium hanging two-strand twists framing both sides of the face",
    "clean scalp cornrows continuing into short braids at the back"
)

$views = @(
    "tight front-facing head-and-shoulders reaction shot, supporting cast layered behind him",
    "left three-quarter waist-up conversational view with hands naturally gesturing",
    "right three-quarter waist-up action-ready view with the face fully readable",
    "clean left-side profile during dialogue, preserving nose, lips, jaw, beard, ear, and hair silhouette",
    "clean right-side profile while walking through the group, with readable facial landmarks",
    "low-angle three-quarter heroic group view from mid-thigh upward",
    "slightly high-angle seated ensemble view with natural hands and eye lines",
    "full-body front ensemble view with both hands and feet visible",
    "full-body dynamic action view with a clear face, outfit, silhouette, and interaction",
    "over-the-shoulder turn toward camera while the supporting cast reacts in depth",
    "wide environmental group shot with Carey closest to camera and unmistakably primary",
    "intimate two-shot at eye level with expressive but natural body language",
    "ground-level upward action angle with Carey leading the cast through the setting",
    "bird's-eye ensemble composition with Carey's face tilted clearly toward camera",
    "medium close-up through foreground characters, using depth without blocking his face",
    "candid side-angle group laugh with Carey's smile and facial geometry unobstructed",
    "centered symmetrical team lineup with varied poses and distinct silhouettes",
    "tracking-style three-quarter walking shot with the group moving through the environment",
    "dramatic backlit silhouette-break shot with enough fill to preserve Carey's face",
    "close ensemble tableau with Carey performing a theme-native task while others assist"
)

$aspects = @(
    "vertical 4:5 portrait",
    "landscape 3:2 cinematic frame",
    "square 1:1 ensemble frame",
    "vertical 2:3 full-character frame",
    "wide 16:9 establishing frame"
)

$roles = @(
    "a quick-thinking field investigator",
    "a rival team captain with dry humor",
    "a calm field medic coordinating the group",
    "a charismatic musician solving a backstage crisis",
    "an inventive chef improvising under pressure",
    "an experienced teacher guiding a chaotic exercise",
    "a gifted mechanic repairing a strange machine",
    "a reluctant mage learning to control a new power",
    "an elite athlete reading the decisive play",
    "an explorer decoding a dangerous route",
    "a courier protecting an unusual package",
    "a street reporter covering an impossible event",
    "an engineer testing a prototype with the team",
    "a detective reconstructing a clue",
    "a pilot preparing the crew for departure",
    "a performer moments before taking the stage",
    "a strategist briefing allies around a map",
    "a shopkeeper handling a supernatural customer rush",
    "a guardian negotiating peace between two groups",
    "a scientist demonstrating a discovery to skeptical colleagues"
)

$scenes = @(
    "a bustling city crossroads at blue hour transformed by the franchise's native world rules",
    "the interior of a show-native headquarters during an urgent team briefing",
    "a crowded night market packed with franchise-appropriate stalls, props, and creatures",
    "a rain-soaked transit platform during a sudden supernatural interruption",
    "a cliffside overlook above an unmistakably theme-native city at sunrise",
    "a high-energy tournament floor with an original adult crowd and dramatic lighting",
    "a cozy apartment gathering where a strange object has just activated",
    "a vast workshop filled with franchise-native machinery, tools, and glowing interfaces",
    "a forest ruin where the cast discovers a hidden threshold",
    "a rooftop celebration interrupted by an impossible event in the skyline",
    "a neighborhood restaurant during a fast-moving comic misunderstanding",
    "a grand library where maps, pages, or holograms reveal a secret route",
    "a waterfront boardwalk crowded with original adult residents at sunset",
    "a backstage corridor seconds before a major performance or mission",
    "a dramatic vehicle interior racing through a theme-native landscape",
    "a public festival with architecture, decorations, and crowd design native to the franchise",
    "a secluded training hall during a tense partner exercise",
    "an observation deck above a franchise-native world or city",
    "an underground passage lit by the world's signature technology or magic",
    "a busy command center where several original adult specialists coordinate a response",
    "a windswept coastal village rebuilt through the named franchise's shape language",
    "a crowded museum or archive after a mysterious exhibit comes alive",
    "a moonlit courtyard where the group debates its next move",
    "a bright daytime plaza during an elaborate chase or rescue",
    "a warm living-room reunion with theme-native furniture, props, and visual comedy"
)

$palettes = @(
    "cobalt blue, amber yellow, white, and charcoal",
    "burgundy, ivory, rose gold, and midnight blue",
    "crimson, black, electric blue, and cream",
    "violet, silver, charcoal, and warm white",
    "burnt orange, navy blue, cream, and copper",
    "turquoise, magenta, sunshine yellow, and black",
    "powder blue, coral, sand, and dark brown",
    "plum, antique gold, black, and pearl white",
    "scarlet, warm white, slate blue, and graphite",
    "indigo, copper, pale blue, and desert sand",
    "hot pink, midnight blue, pearl, and warm gray",
    "emerald, cream, oxblood, and brushed brass",
    "teal, rust orange, smoky violet, and ivory",
    "royal blue, cherry red, parchment, and black",
    "lavender, cyan, peach, and deep navy",
    "golden yellow, ultramarine, terracotta, and charcoal",
    "ice blue, wine red, silver, and near-black",
    "sunset orange, turquoise, cream, and chocolate brown",
    "ruby, sapphire, white, and dark plum",
    "monochrome ink, deep red, parchment, and black"
)

$identityContract = @"
Every supplied image is a real identity reference of the same adult Black male, Carey. Preserve his perceived complexion and Black identity, masculine presentation, relatively narrow face, eye spacing, brow angle, nose width, full-lip shape, jaw line, smile shape, facial-hair boundary, earrings, hairline, and the selected supplied hairstyle. Fully redraw every facial feature in the named franchise's native shape language, including eyes, nose, lips, jaw, beard, hair, highlights, and shadows. Simplify without averaging him into a generic handsome cartoon man. His skin and face must use that franchise's native rendering method--flat cel fill, simplified painted color, halftone, clay-like CGI material, graphic shadow shapes, or another appropriate method--with no photographic pores or pasted realistic face. Native-cast test: Carey must look created from the same model sheets as the rest of the scene, matching anatomy, line weight, proportions, skin treatment, palette, shading, texture, and detail level while remaining recognizably himself. Keep Carey as an adult male. If a franchise normally uses nonhuman characters, translate him into a theme-native anthropomorphic form only when necessary, retaining his face geometry, complexion or color analogue, hair silhouette, beard boundary, and earrings. Carey is the only identity target; supporting characters must have clearly different faces, hair, body types, clothing, and skin tones. Never clone Carey into the supporting cast.
"@.Trim()

function ConvertTo-Slug([string]$value) {
    $slug = $value.ToLowerInvariant() -replace "[^a-z0-9]+", "-"
    return $slug.Trim("-")
}

$catalog = [System.Collections.Generic.List[object]]::new()
foreach ($title in $anime) { $catalog.Add([ordered]@{ group = "anime"; title = $title }) }
foreach ($title in $westernAnimation) { $catalog.Add([ordered]@{ group = "western-animation"; title = $title }) }

if ($catalog.Count -ne 100) { throw "Expected 100 themes, found $($catalog.Count)." }
if (($catalog.title | Sort-Object -Unique).Count -ne 100) { throw "Theme catalog contains duplicates." }

if (Test-Path $existingManifestPath) {
    $existing = Get-Content -LiteralPath $existingManifestPath -Raw | ConvertFrom-Json
    $overlap = @($catalog.title | Where-Object { $_ -in @($existing.items.tone_reference) })
    if ($overlap.Count -gt 0) { throw "New catalog overlaps the first 100: $($overlap -join ', ')" }
}

$items = [System.Collections.Generic.List[object]]::new()
for ($i = 0; $i -lt $catalog.Count; $i++) {
    $entry = $catalog[$i]
    $number = $i + 101
    $id = "{0:D3}" -f $number
    $slug = ConvertTo-Slug $entry.title
    $filename = "${id}_${slug}.png"
    $castSize = 2 + ($i % 4)
    $supportingCount = $castSize - 1
    $hairstyle = $hairstyles[$i % $hairstyles.Count]
    $view = $views[$i % $views.Count]
    $aspect = $aspects[$i % $aspects.Count]
    $role = $roles[$i % $roles.Count]
    $scene = $scenes[$i % $scenes.Count]
    $palette = $palettes[$i % $palettes.Count]

    $medium = if ($entry.group -eq "anime") {
        "a polished anime or anime-inspired production frame using the named title's broad character design, line language, color rhythm, effects vocabulary, and cinematic staging"
    } else {
        "a polished Western animation production frame using the named title's broad model-sheet anatomy, shape language, color design, material treatment, comedic or dramatic staging, and background construction"
    }

    $prompt = @"
Use case: identity-preserve and style-transfer
Asset type: multi-character animation identity reference for ByrdHouse LoRA testing
Primary request: Reimagine the referenced man, Carey, as an original lead character in the unmistakable broad animated visual language of $($entry.title), surrounded by an original supporting cast.
Input images: every supplied image is a real identity reference of Carey; none is a scenery or style reference. Do not use any previously generated image as an identity source.
Scene/backdrop: $scene. Make the entire background native to $($entry.title): architecture, sky treatment, vegetation, props, vehicles, furniture, crowd design, texture, color script, lighting, effects, and perspective must all follow that franchise's animation vocabulary. It must not look like generic scenery with a themed character pasted on top.
Lead subject: Carey as $role, actively participating in the scene rather than posing for a portrait.
Hairstyle: $hairstyle, translated into the franchise's native drawing or rendering language.
Cast: exactly $castSize adult characters total--Carey plus exactly $supportingCount original adult supporting character(s). Carey must remain the clear visual lead. Give every supporting character a distinct identity, silhouette, hairstyle, outfit, expression, and role. Arrange believable eye lines and physical interaction between them. Do not duplicate Carey's face onto anyone else.
Style/medium: $medium. Capture the production-era feel and visual vocabulary while making a new composition. Strongly prioritize show-native face simplification, silhouette, line weight, proportions, cel-shading or material method, palette, effects, and environmental design. The result must look like a real frame from that animation language, not a realistic portrait with themed scenery.
Character integration: redesign Carey's face, skin, beard, hair, body proportions, hands, costume, and accessories through the same native rules as the supporting cast. Give him an original theme-appropriate costume with layered, specific details and colors. Do not default to a plain black shirt, military-green tactical clothing, generic superhero armor, ordinary selfie posture, or fashion-model pose.
Palette direction: $palette for Carey's costume and major scene accents, translated through the named franchise's own color system. Neighboring entries must not share the same costume.
Composition/framing: $aspect; $view. Make this camera angle obvious and useful for identity/LoRA testing. Carey's complete face must remain readable, with hands and body visible whenever the framing allows.
Identity constraints: $identityContract
Franchise constraints: use only the broad visual language and world-building grammar of $($entry.title). Create original adult supporting characters and an original scene. Do not include, imitate, or copy any existing named character, signature costume, logo, title card, copyrighted text, or exact canonical shot.
Avoid: photorealism, semi-realistic portraiture when the franchise is flat or simplified, realistic skin pores, pasted photographic face, generic modern-anime rendering, cloned Carey faces, duplicate people, child characters, fewer or more than $castSize total characters, obstructed lead face, identity drift, light-skinned reinterpretation, changed ethnicity, generic replacement face, malformed hands, duplicate limbs, logos, readable brand text, watermark, social-media interface.
"@.Trim()

    $localPath = Join-Path $outputRoot $filename
    $items.Add([ordered]@{
        id = $id
        group = $entry.group
        tone_reference = $entry.title
        cast_size = $castSize
        supporting_characters = $supportingCount
        role = $role
        scene = $scene
        hairstyle = $hairstyle
        view = $view
        aspect = $aspect
        palette = $palette
        filename = $filename
        prompt = $prompt
        status = $(if (Test-Path $localPath) { "generated" } else { "pending" })
        local_path = $(if (Test-Path $localPath) { $localPath } else { $null })
    })
}

$manifest = [ordered]@{
    version = 1
    title = "ByrdHouse Recognizable Animation Themes 101-200"
    count = $items.Count
    id_range = "101-200"
    distribution = [ordered]@{
        anime = $anime.Count
        western_animation = $westernAnimation.Count
        cast_2 = @($items | Where-Object cast_size -eq 2).Count
        cast_3 = @($items | Where-Object cast_size -eq 3).Count
        cast_4 = @($items | Where-Object cast_size -eq 4).Count
        cast_5 = @($items | Where-Object cast_size -eq 5).Count
    }
    selection_basis = "Cross-generational recognizability, current global demand, franchise reach, visual distinctiveness, and non-overlap with the first 100 themes."
    identity_references = $identityReferences
    identity_contract = $identityContract
    output_root = $outputRoot
    generator = "Codex built-in cloud image generation"
    items = $items
}

New-Item -ItemType Directory -Force $outputRoot | Out-Null
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 $manifestPath
Write-Output "Wrote $($items.Count) prompts to $manifestPath"
