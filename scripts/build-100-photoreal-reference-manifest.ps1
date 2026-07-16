param(
    [string]$OutputRoot = 'E:\ByrdHouse\profiles\me\references\generated_real_photos'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

$identityReferences = @(
    'E:\ByrdHouse\profiles\me\references\me_photo_21.jpg',
    'E:\ByrdHouse\profiles\me\references\me_photo_22.jpg',
    'E:\ByrdHouse\profiles\me\references\me_photo_01.jpg',
    'E:\ByrdHouse\profiles\me\references\me_photo_04.jpg',
    'E:\ByrdHouse\profiles\me\references\me_photo_10.jpg'
)

$rows = @'
studio-gray-front|a neutral gray professional portrait studio|white crewneck, charcoal trousers, silver stud earrings
white-seamless-fashion|a bright white seamless fashion studio|cobalt overshirt, white tee, black trousers
black-backdrop-profile|a matte black studio with a single rim light|burgundy mock-neck top and dark tailored trousers
gel-light-editorial|a color-gel editorial studio with cyan and magenta light|cream bomber jacket, black tee, dark denim
window-light-portrait|a quiet loft beside a large north-facing window|soft blue knit sweater and tan trousers
concrete-studio-full-body|an industrial concrete photography studio|rust-orange jacket, ivory tee, navy trousers
daylight-loft-seated|a sunlit loft with simple wooden furniture|plum cardigan, pale shirt, charcoal pants
beauty-dish-closeup|a clean beauty portrait set with a large soft reflector|black turtleneck and small diamond-like studs
contact-sheet-candid|a working photo studio between test frames|scarlet zip jacket, cream tee, slate trousers
backstage-between-takes|a backstage portrait area with folded stands and curtains|midnight-blue overshirt, white tee, copper watch
morning-coffee-kitchen|a real apartment kitchen in soft morning light|heather-gray tee and navy lounge pants
cooking-pasta-home|a warm home kitchen while dinner cooks|brick-red apron over a cream shirt, dark jeans
reading-sofa|a comfortable living room with books and afternoon light|powder-blue sweatshirt and charcoal joggers
watering-houseplants|a plant-filled apartment corner by a bright window|coral tee, sand chinos, simple watch
folding-laundry|a tidy bedroom with a basket of clean laundry|violet hoodie and black sweatpants
home-office-video-edit|a practical home editing desk with dual monitors showing abstract color only|navy cardigan, white tee, dark trousers
balcony-sunrise|a city apartment balcony at sunrise|burnt-orange windbreaker, cream shirt, black pants
tying-sneakers-entryway|a bright apartment entryway before heading outside|cobalt athletic jacket, gray tee, navy joggers
listening-vinyl|a cozy listening room beside a turntable and record shelves|burgundy overshirt, black tee, tan trousers
doorway-coat|an apartment doorway in cool evening light|camel overcoat, midnight shirt, charcoal trousers
rainy-crosswalk|a downtown crosswalk during light rain|deep-red rain shell, black jeans, clear umbrella
subway-platform|a clean city subway platform with a train arriving|indigo bomber, cream tee, slate trousers
rooftop-sunset|a city rooftop at golden sunset|copper jacket, white shirt, black jeans
neon-alley|a wet neon-lit alley at night|electric-blue coat, charcoal layers, silver chain
cafe-patio|a relaxed sidewalk cafe patio in late morning|coral polo, cream trousers, dark watch
indie-bookstore|a warm independent bookstore aisle|plum sweater, pale-blue collared shirt, dark jeans
farmers-market|a busy outdoor produce market in natural daylight|mustard overshirt, white tee, navy trousers
bus-stop-blue-hour|a glass city bus shelter at blue hour|scarlet varsity jacket, gray hoodie, black jeans
parking-garage|an open-air parking deck with strong geometric shadows|white denim jacket, black shirt, cobalt trousers
mural-block|a colorful neighborhood street beside a large abstract mural|violet windbreaker, cream tee, charcoal pants
forest-trail|a shaded forest hiking trail after rain|cobalt trail jacket, sand shirt, dark hiking trousers
lakeside-dock|a quiet wooden dock on a clear lake|ivory henley, navy trousers, brown boots
windy-beach|a wide beach with windblown surf and pale sky|rust wind shirt, white tee, charcoal shorts
mountain-overlook|a high mountain overlook in crisp daylight|burgundy fleece, cream base layer, black trail pants
desert-hike|a sunlit desert trail among red rock formations|powder-blue sun shirt, tan trousers, dark boots
waterfall-trail|a misty trail near a tall waterfall|deep-red waterproof shell, charcoal shirt, navy pants
wildflower-meadow|a broad wildflower meadow at golden hour|white linen shirt, plum trousers, brown belt
snowy-woods|a quiet snowy woodland path|midnight parka, coral scarf, charcoal pants
campsite-dawn|a simple campsite at dawn beside a small tent|amber fleece, black thermal shirt, slate cargo pants
botanical-greenhouse|a glass botanical conservatory filled with tropical plants|cream overshirt, cobalt tee, dark trousers
basketball-court|an outdoor basketball court under bright afternoon sun|scarlet sleeveless jersey, black shorts, white sneakers
track-jog|a running track in cool early-morning light|cobalt running top, charcoal shorts, bright white shoes
gym-dumbbells|a modern gym beside a dumbbell rack|black athletic tee, burgundy shorts, gray trainers
boxing-heavy-bag|a gritty but clean boxing gym|navy sleeveless training top, red wraps, charcoal shorts
city-bicycle|a protected city bike lane on a clear day|electric-blue cycling shell, black pants, white helmet carried at his side
tennis-serve|an outdoor tennis court in midday light|white polo, cobalt shorts, coral wristbands
pool-deck|a quiet outdoor pool deck after a swim|cream towel over a navy athletic shirt and black shorts
hiking-backpack|a rocky ridge trail with distant hills|rust-orange technical jacket, slate hiking pants, dark backpack
yoga-stretch|a bright minimalist exercise studio|plum performance top and charcoal training pants
soccer-field|a neighborhood soccer field at sunset|deep-red athletic shirt, navy shorts, white socks
tailored-suit-lobby|a modern hotel lobby with warm architectural lighting|midnight-blue tailored suit, ivory shirt, no tie
wedding-guest-garden|an elegant garden reception in daylight|burgundy suit, cream shirt, rose-gold watch
gallery-opening|a contemporary art gallery with abstract paintings|black tailored jacket, white tee, cobalt trousers
jazz-lounge|an intimate jazz lounge with amber table light|plum velvet blazer, black shirt, charcoal trousers
rooftop-dinner|a refined rooftop dinner setting at dusk|cream dinner jacket, midnight shirt, black trousers
theater-lobby|an ornate theater lobby before a performance|deep-red double-breasted suit, pale shirt, dark loafers
award-night|a tasteful event entrance with soft flashes and rope barriers|charcoal tuxedo, white shirt, burgundy bow tie
holiday-party|a warmly decorated apartment party without visible guests|cobalt knit sweater, cream trousers, silver watch
weekend-brunch|a bright restaurant brunch table by a window|coral knit polo, sand trousers, dark bracelet
black-tie-studio|a formal dark studio portrait set|black tuxedo, pearl-white shirt, satin bow tie
photographer-workshop|a working photography studio with cameras and stands|navy utility overshirt, white tee, charcoal jeans
music-studio|a professional music production room with acoustic panels|burgundy hoodie, black tee, silver headphones
podcast-booth|a compact podcast booth with a studio microphone|powder-blue jacket, cream shirt, dark trousers
mural-painting|an outdoor wall with a colorful abstract mural in progress|white coveralls with cobalt and coral paint marks
fashion-fitting|a clothing design studio with racks and fabric swatches|plum overshirt, black fitted tee, tan trousers
woodshop-project|a bright woodshop beside a half-built stool|rust work shirt, cream tee, dark denim, protective glasses raised
coffee-roastery|a small coffee roastery with sacks and polished equipment|deep-red apron, pale-blue shirt, charcoal trousers
record-shop|an independent record shop with colorful album spines|violet jacket, white tee, black jeans
library-research|a grand public library reading room|cobalt cardigan, ivory shirt, brown trousers
maker-lab|a clean community maker lab with tools and small electronics|coral work jacket, charcoal tee, navy trousers
airport-terminal|a bright modern airport terminal beside large windows|camel jacket, white shirt, black travel trousers
train-window|a passenger train seat beside a rain-streaked window|burgundy sweater, cream tee, charcoal pants
hotel-balcony|a high hotel balcony overlooking a coastal city|pale-blue linen shirt, white trousers, dark watch
coastal-boardwalk|a lively coastal boardwalk in late afternoon|scarlet windbreaker, navy tee, tan shorts
old-town-street|a quiet stone old-town street in warm evening light|plum overshirt, cream shirt, charcoal trousers
ferry-deck|an open ferry deck with wind and distant skyline|cobalt marine jacket, white tee, black trousers
roadside-diner|a classic roadside diner booth by a large window|rust bomber jacket, ivory tee, dark jeans
mountain-cabin|a wood cabin porch with misty mountains behind|navy flannel overshirt, cream thermal, brown trousers
desert-gas-station|a remote desert service station at sunset|coral work jacket, black tee, sand trousers
luggage-arrival|a hotel arrival area with a compact suitcase|midnight overcoat, powder-blue shirt, charcoal trousers
umbrella-rain-night|a city sidewalk under heavy nighttime rain|violet waterproof coat, black layers, silver umbrella
golden-hour-field|an open field under rich golden-hour light|white linen shirt, navy trousers, brown boots
blue-hour-bridge|a pedestrian bridge during deep blue hour|scarlet jacket, charcoal shirt, black jeans
snowfall-morning|a residential street during gentle morning snowfall|cobalt parka, cream scarf, charcoal trousers
foggy-pier|a wooden pier disappearing into morning fog|burgundy peacoat, pale shirt, dark trousers
storm-window|an interior portrait beside a window during a thunderstorm|sand knit sweater, midnight trousers, silver watch
summer-noon|a sunlit city plaza at high summer noon|powder-blue short-sleeve shirt, white trousers, dark belt
autumn-leaves|a tree-lined walkway filled with autumn leaves|deep-red wool jacket, cream sweater, navy trousers
spring-blossoms|a park path beneath spring blossoms|plum bomber, white tee, sand chinos
candlelit-room|a quiet room lit by candles and warm practical lamps|black mock-neck shirt, burgundy trousers, gold watch
driving-car-day|the driver seat of a parked modern car in daylight|cream tee, cobalt overshirt, dark trousers
passenger-seat-night|the passenger seat of a parked car beneath city lights|charcoal jacket, burgundy shirt, silver chain
grocery-aisle|a bright grocery aisle with colorful packaging kept unreadable|navy hoodie, white tee, tan trousers
laundromat|a clean neighborhood laundromat with spinning machines|coral jacket, cream tee, black jeans
elevator-candid|a modern elevator with brushed metal walls and no mirror duplication|plum overcoat, pale-blue shirt, charcoal trousers
barbershop-chair|a classic barbershop chair beneath warm window light|white cape over a black shirt, small stud earrings visible
arcade-night|a colorful retro arcade with glowing cabinets and unreadable screens|electric-blue bomber, black tee, burgundy trousers
bowling-alley|a bowling lane during a casual evening game|cream polo, cobalt trousers, coral bowling shoes
museum-hall|a large natural-history museum hall in soft daylight|rust blazer, white tee, charcoal trousers
night-food-truck|a city food-truck plaza under string lights at night|scarlet overshirt, cream tee, midnight trousers
'@.Trim() -split "`r?`n"

if ($rows.Count -ne 100) {
    throw "Expected 100 scene rows but found $($rows.Count)."
}

$hairstyles = @(
    'the large natural afro shown in the two primary studio references, with real individual coils and authentic volume',
    'short natural curls with a clean tapered fade, matching the supplied short-hair references',
    'medium hanging braids or two-strand twists framing the face, matching the supplied braided references',
    'clean scalp cornrows continuing into short braids at the back, matching the supplied cornrow references',
    'a medium freeform natural afro with visible coiled texture and a soft asymmetric silhouette'
)

$views = @(
    'tight eye-level front-facing head-and-shoulders portrait, 85mm portrait lens',
    'left three-quarter waist-up photograph, 50mm lens, face fully readable',
    'right three-quarter waist-up photograph, 50mm lens, face fully readable',
    'strict left-side profile photograph, 85mm lens, full facial silhouette visible',
    'strict right-side profile photograph, 85mm lens, full facial silhouette visible',
    'eye-level full-body front photograph, 35mm lens, hands and feet visible',
    'full-body candid action photograph, 35mm lens, face sharp and unobstructed',
    'slightly high-angle seated photograph, 50mm lens, natural hands and posture',
    'low-angle mid-thigh-up environmental portrait, 35mm lens',
    'over-the-shoulder turn toward camera, 50mm lens, face and rear hairstyle visible'
)

$expressions = @(
    'relaxed neutral expression',
    'subtle closed-mouth confident smile',
    'natural warm smile with teeth visible',
    'focused serious expression',
    'genuine mid-laugh expression',
    'calm contemplative expression',
    'determined but relaxed expression',
    'slightly amused expression',
    'soft candid expression while concentrating on the activity',
    'easy half-smile while glancing back toward the camera'
)

$items = for ($index = 0; $index -lt $rows.Count; $index++) {
    $parts = $rows[$index] -split '\|', 3
    $id = 101 + $index
    $slug = $parts[0]
    $scene = $parts[1]
    $wardrobe = $parts[2]
    $hairstyle = $hairstyles[$index % $hairstyles.Count]
    $view = $views[$index % $views.Count]
    $expression = $expressions[$index % $expressions.Count]
    $filename = ('{0:D3}_{1}.png' -f $id, $slug)
    $localPath = Join-Path $OutputRoot $filename

    $prompt = @"
Use case: identity-preserve
Asset type: reusable photoreal identity-reference photograph for the ByrdHouse application
Primary request: Create a new, convincingly real photograph of the same adult Black man shown in all five supplied identity references.
Input images: Images 1 and 2 are the primary high-clarity facial identity and large-afro references. Images 3 through 5 are secondary references for his real facial geometry, complexion, lean athletic build, smile, earrings, and alternate supplied hairstyles. Every input depicts the same person. They are identity references only, never scenery or wardrobe references.
Scene/backdrop: $scene.
Subject: the same recognizable adult Black male, alone in the image. Preserve his actual perceived age, complexion, masculine presentation, relatively narrow oval face, relaxed slightly hooded dark eyes and exact spacing, thick mildly angled eyebrows, medium-width rounded nose, full lips with a fuller lower lip, narrow jaw and chin, close mustache and beard boundary, hairline, small stud earrings, lean athletic build, and characteristic expression. Do not average him into a generic model.
Hairstyle: $hairstyle.
Wardrobe: $wardrobe. Keep the clothing realistic, well fitted, scene-appropriate, and free of logos or readable branding.
Composition/framing: $view. Use natural body proportions, physically plausible hands, an authentic candid or editorial pose, and a clearly readable face.
Expression: $expression.
Style/medium: premium photorealistic natural photography, true camera optics, believable skin texture, realistic pores without exaggeration, accurate hair strands and coils, real fabric behavior, practical environmental detail, and coherent perspective. This must look like a genuine photograph rather than illustration, animation, 3D render, beauty-filter portrait, or synthetic game character.
Lighting/mood: lighting must arise naturally from the named environment, with realistic shadow direction, skin response, catchlights, depth of field, and color temperature. Avoid plastic highlights and over-smoothed skin.
Constraints: Generate a genuinely new photograph and pose rather than copying any source photo. Keep one person only. Match identity more strongly than wardrobe or scenery. Keep his Black identity and complexion consistent under the scene lighting. Maintain the selected supplied hairstyle faithfully. Face must remain unobstructed and useful for future identity conditioning.
Avoid: identity drift, generic replacement face, changed ethnicity, lightened complexion, widened jaw, narrowed lips, altered nose, enlarged eyes, feminine features, age change, bodybuilder proportions, duplicate person, extra face, deformed hands, duplicate limbs, warped earrings, face occlusion, sunglasses, hat, heavy makeup, tattoos not in the references, text, logo, watermark, social-media interface, illustration, anime, cartoon, CGI, painterly rendering, waxy skin, excessive retouching, fake bokeh, or impossible lighting.
"@

    [pscustomobject]@{
        id = ('{0:D3}' -f $id)
        slug = $slug
        scene = $scene
        hairstyle = $hairstyle
        view = $view
        expression = $expression
        wardrobe = $wardrobe
        filename = $filename
        prompt = $prompt.Trim()
        status = if (Test-Path -LiteralPath $localPath) { 'generated' } else { 'pending' }
        local_path = $localPath
    }
}

$manifest = [ordered]@{
    version = 1
    title = 'ByrdHouse 100 Additional Photoreal Identity References'
    count = 100
    id_range = '101-200'
    output_root = $OutputRoot
    generator = 'Codex built-in image generation'
    identity_references = $identityReferences
    identity_contract = 'Use only real photographs of the same adult Black male as identity references. Never use a generated cartoon or prior generated scene as an identity source.'
    diversity_contract = 'One hundred unique scenarios with rotating camera views, expressions, hairstyles, wardrobe, lighting, activities, and environments.'
    items = $items
}

$manifestPath = Join-Path $OutputRoot 'manifest.json'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
$manifestPath
