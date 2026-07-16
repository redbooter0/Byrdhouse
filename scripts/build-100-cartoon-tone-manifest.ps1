$ErrorActionPreference = "Stop"

$outputRoot = "E:/ByrdHouse/profiles/me/references/generated_anime_cartoon"
$manifestPath = Join-Path $outputRoot "manifest.json"

$identityReferences = @(
    "E:/ByrdHouse/profiles/me/references/me_photo_01.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_03.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_04.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_08.jpg",
    "E:/ByrdHouse/profiles/me/references/me_photo_10.jpg"
)

$hairstyles = @(
    "short natural curls with a clean tapered fade, as shown in the early short-hair reference",
    "compact rounded natural afro with tapered sides",
    "large soft natural afro with visible coiled texture",
    "medium hanging braids or two-strand twists framing the face",
    "clean scalp cornrows continuing into short braids at the back"
)

$views = @(
    "tight front-facing head-and-shoulders character portrait with a relaxed neutral expression",
    "left three-quarter waist-up view with a subtle confident smile",
    "right three-quarter waist-up view with a focused serious expression",
    "clean left-side profile showing the full silhouette of nose, lips, jaw, beard, ear, and hairstyle",
    "clean right-side profile in motion with the face unobstructed",
    "low-angle three-quarter heroic view from mid-thigh upward",
    "slightly high-angle seated view with natural hand placement and an amused expression",
    "full-body front view in a show-native standing pose with both hands and feet visible",
    "full-body dynamic action view with readable face, hands, outfit, and silhouette",
    "over-the-shoulder turn toward camera, clearly showing the face and back of the hairstyle"
)

$paletteDirections = @(
    "cobalt blue, amber yellow, white, and charcoal",
    "burgundy, ivory, rose gold, and midnight blue",
    "crimson, black, electric blue, and cream",
    "violet, silver, charcoal, and warm white",
    "burnt orange, navy blue, cream, and copper",
    "turquoise blue, magenta, sunshine yellow, and black",
    "powder blue, coral, sand, and dark brown",
    "plum, gold, black, and pearl white",
    "scarlet, white, slate blue, and graphite",
    "indigo, copper, pale blue, and desert sand",
    "hot pink, midnight blue, pearl, and warm gray",
    "monochrome ink, deep red, parchment, and black"
)

$anime = @(
    "Dragon Ball Z", "Naruto", "One Piece", "Bleach", "My Hero Academia",
    "Demon Slayer", "Jujutsu Kaisen", "Attack on Titan", "Hunter x Hunter", "Fullmetal Alchemist: Brotherhood",
    "Cowboy Bebop", "Samurai Champloo", "Yu Yu Hakusho", "JoJo's Bizarre Adventure", "Pokemon",
    "Digimon Adventure", "Sailor Moon", "Neon Genesis Evangelion", "Gurren Lagann", "Mob Psycho 100",
    "One Punch Man", "Chainsaw Man", "Spy x Family", "Death Note", "Code Geass",
    "Inuyasha", "Trigun", "Black Clover", "Fairy Tail", "Soul Eater",
    "Fire Force", "Haikyuu!!", "Kuroko's Basketball", "Blue Lock", "Slam Dunk",
    "Akira", "Ghost in the Shell", "Afro Samurai", "Berserk"
)

$otherAnimation = @("The Simpsons")

$cartoonNetwork = @(
    "Adventure Time", "Regular Show", "Steven Universe", "The Powerpuff Girls", "Dexter's Laboratory",
    "Samurai Jack", "Courage the Cowardly Dog", "Ed, Edd n Eddy", "The Grim Adventures of Billy & Mandy", "Codename: Kids Next Door",
    "Ben 10", "Teen Titans", "Teen Titans Go!", "Foster's Home for Imaginary Friends", "Chowder",
    "The Marvelous Misadventures of Flapjack", "Johnny Bravo", "The Amazing World of Gumball", "We Bare Bears", "Craig of the Creek",
    "OK K.O.! Let's Be Heroes", "Infinity Train", "Over the Garden Wall", "Total Drama Island", "Generator Rex",
    "Sym-Bionic Titan", "Megas XLR", "Camp Lazlo", "My Gym Partner's a Monkey", "Robotboy"
)

$nickelodeon = @(
    "SpongeBob SquarePants", "Avatar: The Last Airbender", "The Legend of Korra", "Rugrats", "Hey Arnold!",
    "Rocko's Modern Life", "The Fairly OddParents", "Danny Phantom", "The Adventures of Jimmy Neutron", "Invader Zim",
    "Teenage Mutant Ninja Turtles", "The Loud House", "The Wild Thornberrys", "CatDog", "Rocket Power",
    "ChalkZone", "My Life as a Teenage Robot", "El Tigre", "The Angry Beavers", "Aaahh!!! Real Monsters",
    "As Told by Ginger", "Doug", "The Ren & Stimpy Show", "T.U.F.F. Puppy", "Fanboy & Chum Chum",
    "Rise of the Teenage Mutant Ninja Turtles", "Glitch Techs", "Harvey Beaks", "The Casagrandes", "Breadwinners"
)

$scenes = @(
    "a storm-lit rooftop above a sprawling city",
    "a moonlit ancient forest filled with mossy ruins",
    "a neon train platform during heavy rain",
    "a packed basketball arena during the final possession",
    "a windswept desert canyon at golden hour",
    "a glowing underwater city with glass walkways",
    "a quiet neighborhood street under cherry blossoms",
    "a futuristic spacecraft observation deck above a blue planet",
    "a colorful outdoor market on a sunny afternoon",
    "an abandoned amusement park at twilight",
    "a mountain shrine during the first snowfall",
    "a lively retro arcade filled with colored light",
    "a rooftop garden surrounded by futuristic towers",
    "a cozy apartment kitchen during a thunderstorm",
    "a dramatic tournament entrance with spotlights and cheering crowds",
    "a hidden crystal cavern beneath a waterfall",
    "a coastal highway beside a glowing sunset ocean",
    "a mysterious old library where pages float in the air",
    "a city park alive with fireflies at dusk",
    "a colossal mechanical hangar with sparks falling in the distance",
    "a vibrant graffiti-covered basketball court after rain",
    "a small sailboat moving through clouds and constellations",
    "an overgrown post-apocalyptic boulevard reclaimed by nature",
    "a whimsical hilltop village filled with warm lanterns",
    "a subway car rushing through a luminous tunnel"
)

$identityContract = @"
Every supplied image is a reference of the same adult Black male. Preserve his key identity anchors: his perceived complexion and Black identity, age, masculine presentation, relatively narrow face, eye spacing, brow angle, nose width, full-lip shape, jaw line, smile shape, facial-hair boundary, earrings, hairline, and one of his supplied hairstyles. Fully redraw every facial feature in the named program's own shape language, including eyes, nose, lips, jaw, beard, hair, highlights, and shadows. Simplify those features without averaging them into a generic handsome cartoon man. His skin must use that show's native rendering method and native character palette--flat cel fill, show-specific skin color, simplified painted color, halftone, clay, pixel clusters, or other appropriate treatment--while preserving the identity cues from the references. Do not preserve photographic pores, realistic skin shading, or high-detail facial rendering when the show is simplified. Do not paste a realistic face onto a cartoon body. Native-cast test: if he stood in the same room beside a main character from the named show, he must look designed from the same model sheets, with matching anatomy, proportions, line weight, skin treatment, palette, shading, texture, and detail level, while still being recognizably himself. Render him as a human adult male even when the program contains nonhuman characters. Keep one subject only, with his face visible and readable. Never replace him with a generic character. Style priority is 70 percent named-show animation language and 30 percent reference-specific facial geometry, with zero photoreal surface detail.
"@.Trim()

function ConvertTo-Slug([string]$value) {
    $slug = $value.ToLowerInvariant() -replace "[^a-z0-9]+", "-"
    return $slug.Trim("-")
}

$catalog = [System.Collections.Generic.List[object]]::new()
foreach ($title in $anime) { $catalog.Add([ordered]@{ group = "anime"; title = $title }) }
foreach ($title in $otherAnimation) { $catalog.Add([ordered]@{ group = "other-animation"; title = $title }) }
foreach ($title in $cartoonNetwork) { $catalog.Add([ordered]@{ group = "cartoon-network"; title = $title }) }
foreach ($title in $nickelodeon) { $catalog.Add([ordered]@{ group = "nickelodeon"; title = $title }) }

$items = [System.Collections.Generic.List[object]]::new()
for ($i = 0; $i -lt $catalog.Count; $i++) {
    $entry = $catalog[$i]
    $id = "{0:D3}" -f ($i + 1)
    $slug = ConvertTo-Slug $entry.title
    $scene = $scenes[$i % $scenes.Count]
    $hairstyle = $hairstyles[$i % $hairstyles.Count]
    $view = $views[$i % $views.Count]
    $palette = $paletteDirections[$i % $paletteDirections.Count]
    $filename = "${id}_${slug}.png"

    $medium = switch ($entry.group) {
        "anime" { "a polished Japanese anime character scene using the broad visual tone, line language, color rhythm, and cinematic energy associated with the named series" }
        "other-animation" { "a polished Western television-cartoon scene using the broad model-sheet anatomy, flat palette, line language, and sitcom staging associated with the named series" }
        "cartoon-network" { "a polished Western television-cartoon scene using the broad shape language, color design, timing energy, and background mood associated with the named Cartoon Network series" }
        default { "a polished Western television-cartoon scene using the broad shape language, color design, comic energy, and background mood associated with the named Nickelodeon series" }
    }

    $prompt = @"
Use case: identity-preserve and style-transfer
Asset type: reusable cartoon-tone identity reference for the ByrdHouse application
Primary request: Reimagine the referenced man as an original human character in the broad animated visual tone of $($entry.title).
Input images: all supplied images are identity references of the same male subject; they are not scenery references.
Scene/backdrop: $scene.
Subject: the same recognizable adult Black male from the references, alone in the scene.
Hairstyle: $hairstyle. Translate that real hairstyle into the named show's native drawing language.
Style/medium: $medium. Capture the production-era feel and animation vocabulary while creating an original composition. Strongly prioritize the named show's characteristic face simplification, silhouette, line weight, proportions, cel-shading method, palette, and background design. The result must look like a frame from that animation language, not a realistic portrait with themed scenery.
Character design: make him an actual native character in that show world with an original role, show-appropriate outfit, purposeful pose or action, and scene-specific accessories. Do not default to a plain black T-shirt, ordinary selfie posture, or generic model pose unless that program's story context specifically calls for it.
Palette direction: use $palette for the character wardrobe and major accents, translated through the named show's own color system. Do not default to military green, olive tactical clothing, or the same palette as neighboring entries.
Composition/framing: vertical 4:5 image; $view. The chosen view must be obvious, useful as a character reference, and different from neighboring entries. Keep the face readable even during action.
Constraints: $identityContract Do not include any existing character from $($entry.title), and do not copy a signature costume, logo, title card, symbol, or exact shot from the program.
Avoid: photorealism, semi-realistic portraiture, realistic skin pores, photographic facial highlights, generic modern-anime rendering, pasted photographic face, second person, existing franchise characters, copyrighted logos, text, watermark, identity drift, light-skinned reinterpretation, changed ethnicity, feminine features, generic replacement face, malformed hands, duplicate limbs, obstructed face, social-media interface.
"@.Trim()

    $items.Add([ordered]@{
        id = $id
        group = $entry.group
        tone_reference = $entry.title
        scene = $scene
        hairstyle = $hairstyle
        view = $view
        palette = $palette
        filename = $filename
        prompt = $prompt
        status = $(if (Test-Path (Join-Path $outputRoot $filename)) { "generated" } else { "pending" })
        local_path = $(if (Test-Path (Join-Path $outputRoot $filename)) { Join-Path $outputRoot $filename } else { $null })
    })
}

$manifest = [ordered]@{
    version = 2
    title = "ByrdHouse 100 Anime, Cartoon Network, and Nickelodeon Tone References"
    count = $items.Count
    distribution = [ordered]@{ anime = $anime.Count; other_animation = $otherAnimation.Count; cartoon_network = $cartoonNetwork.Count; nickelodeon = $nickelodeon.Count }
    identity_references = $identityReferences
    identity_contract = $identityContract
    output_root = $outputRoot
    generator = "Codex cloud image generation"
    items = $items
}

New-Item -ItemType Directory -Force $outputRoot | Out-Null
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 $manifestPath
Write-Output "Wrote $($items.Count) prompts to $manifestPath"
