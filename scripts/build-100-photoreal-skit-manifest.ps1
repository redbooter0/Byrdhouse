param(
    [string]$OutputRoot = 'E:\ByrdHouse\profiles\me\references\generated_real_skit_scenes'
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
201|coffee-shop-wrong-order|a busy neighborhood cafe in clear morning daylight|solo|he notices the wrong order on the counter and gives the camera a dry amused look|casual
202|elevator-button-mixup|a modern office elevator during late afternoon|duo|he and a coworker reach for the same button and exchange an awkward laugh|work
203|sidewalk-lost-map|a downtown sidewalk in bright midday sun|group|he leads two friends in a playful debate over a folded tourist map|travel
204|street-festival-arrival|a crowded street festival under colorful night lighting|crowd|he arrives through the crowd, spots someone off camera, and reacts with an excited grin|party
205|missed-bus-sprint|a city bus stop in crisp morning light|solo|he has just missed the bus and bends forward catching his breath with comic disbelief|casual
206|parking-meter-confusion|a curbside parking meter on a sunny afternoon|duo|a friendly stranger explains the meter while he listens with a skeptical half smile|casual
207|rooftop-group-selfie|a rooftop at warm sunset with skyline behind|group|he organizes a selfie with three adult friends while remaining closest to the camera|party
208|house-party-doorway|the entrance to a lively apartment party at night|crowd|he pauses in the doorway as the room notices his arrival and cheers|party
209|kitchen-smoke-alarm|a bright apartment kitchen during daytime|solo|he waves a dish towel beneath a sounding smoke alarm after slightly overcooking dinner|casual
210|roommate-last-slice|a living room coffee table late at night|duo|he and a roommate both reach for the final pizza slice and freeze in mock rivalry|casual

211|game-night-rule-dispute|a warm living room during evening game night|group|he explains a disputed rule to three amused friends with expressive but natural hands|casual
212|backyard-cookout-toast|a busy backyard cookout in afternoon sunlight|crowd|he raises a cup in a relaxed toast while guests mingle behind him|party
213|wardrobe-mirror-decision|a bedroom dressing area in soft morning light|solo|he compares two jackets and studies the choice with exaggerated seriousness|smart
214|barbershop-joke|a neighborhood barbershop in window light|duo|he sits in the chair laughing at a barber's joke before the haircut begins|casual
215|birthday-surprise-reaction|a decorated apartment living room at night|group|three friends reveal a small surprise and he reacts with genuine shock and delight|party
216|wedding-dance-floor|an elegant wedding reception dance floor at night|crowd|he dances confidently in the foreground while adult guests celebrate around him|party
217|rainy-ride-cancelled|a storefront awning during heavy nighttime rain|solo|he checks a cancelled ride on his phone and looks up with patient frustration|outdoor
218|umbrella-sharing|a wet city sidewalk beneath streetlights at night|duo|he shares a clear umbrella with one friend as both laugh about the weather|outdoor
219|late-train-platform|an outdoor train platform at blue hour|group|he checks the arrival board with two tired friends and reacts to another delay|travel
220|rush-hour-subway|a crowded but orderly subway car during morning commute|crowd|he stands clearly in the foreground holding a rail while commuters fill the background|travel

221|library-wrong-aisle|a grand public library in daylight|solo|he holds an obviously oversized stack of books and scans the shelves with mild confusion|smart
222|museum-guide-question|a natural-history museum gallery in afternoon light|duo|he asks an adult guide a curious question while both face a large exhibit|smart
223|study-group-debate|a university-style study room in early evening|group|he makes a thoughtful point to three adult study partners around a table|work
224|gallery-opening-crowd|a contemporary gallery opening at night|crowd|he turns toward camera in the foreground while guests discuss abstract art behind him|smart
225|gym-last-rep|a bright modern gym during daytime|solo|he finishes a final controlled dumbbell repetition and exhales with determined focus|athletic
226|basketball-one-on-one|an outdoor basketball court in late afternoon|duo|he squares up playfully against one adult friend while keeping his face visible|athletic
227|bowling-team-cheer|a colorful bowling alley at night|group|he celebrates a strike with three teammates in a spontaneous group reaction|athletic
228|stadium-concourse|a busy stadium concourse under evening lights|crowd|he walks toward camera carrying a snack while fans stream around him|casual
229|grocery-list-forgotten|a bright grocery produce aisle during daytime|solo|he stares into his empty cart after realizing the shopping list is missing|casual
230|checkout-line-kindness|a grocery checkout lane in afternoon light|duo|he helps another adult pick up a dropped item and shares a friendly smile|casual

231|market-taste-test|an outdoor farmers market at midday|group|he reacts thoughtfully to a sample while two friends wait for his verdict|casual
232|holiday-shopping-crowd|a bustling indoor shopping arcade at night|crowd|he carries simple unbranded bags in the foreground as shoppers move behind him|smart
233|airport-gate-change|a bright airport terminal during daytime|solo|he studies a phone update and pivots with luggage after a sudden gate change|travel
234|rental-car-counter|an airport rental counter in afternoon light|duo|he listens to an attendant explain an unexpected upgrade with pleased surprise|travel
235|roadtrip-gas-stop|a roadside service station at sunset|group|he and three friends stretch beside a parked car during a road-trip break|travel
236|airport-arrivals-crowd|a crowded airport arrivals hall at night|crowd|he recognizes someone beyond the camera and moves forward smiling through the crowd|travel
237|hotel-key-not-working|a quiet hotel hallway at night|solo|he tries the room key again and gives the camera a tired comedic stare|travel
238|restaurant-reservation|a stylish restaurant host stand at night|duo|he calmly explains a reservation mix-up to an adult host|smart
239|rooftop-dinner-laughter|a rooftop dinner table at dusk|group|he laughs naturally with three adult friends as city lights appear|party
240|nightclub-entrance|a tasteful nightclub entrance with colorful practical lighting|crowd|he approaches the entrance confidently while a lively adult crowd queues behind|party

241|office-presentation-prep|a conference room in clear morning daylight|solo|he rehearses beside a blank presentation screen with focused concentration|work
242|copier-jam-teamup|an office copy room during daytime|duo|he and a coworker inspect a harmless paper jam and exchange an amused look|work
243|brainstorm-whiteboard|a creative office studio in afternoon light|group|he leads three coworkers around a whiteboard containing only abstract shapes|work
244|company-mixer|a modern office mixer during early evening|crowd|he speaks with confidence in the foreground while adult colleagues mingle behind|smart
245|podcast-mic-check|a compact recording booth in daytime|solo|he adjusts his distance from a studio microphone and tests it with a playful expression|work
246|camera-audition|a small video studio with soft lights|duo|he performs a short audition while an adult camera operator watches from the side|work
247|rehearsal-table-read|a rehearsal room during evening|group|he reads a scene with three adult performers and reacts in character|work
248|film-set-background|a practical nighttime film set on a city block|crowd|he stands as the featured performer in sharp foreground while adult extras cross behind|work
249|park-bench-phone-call|a quiet park in late morning|solo|he receives unexpectedly good news on the phone and breaks into a genuine smile|casual
250|dog-leash-tangle|a neighborhood park path in afternoon light|duo|he and an adult dog walker laugh while calmly untangling two crossed leashes|casual

251|picnic-card-game|a sunny park picnic blanket|group|he reveals a winning card to three friends and enjoys their surprised reactions|casual
252|outdoor-concert|an outdoor music concert after dark|crowd|he enjoys the performance in the foreground with a dense adult audience behind|party
253|laundromat-missing-sock|a clean laundromat in early evening|solo|he holds one unmatched sock and looks into an empty dryer with comic suspicion|casual
254|neighbor-package-swap|an apartment hallway during daytime|duo|he and a neighbor exchange accidentally swapped packages and laugh|casual
255|moving-day-stairwell|an apartment stairwell in afternoon light|group|he coordinates two friends carrying light moving boxes up the stairs|casual
256|apartment-rooftop-party|a city apartment rooftop party at night|crowd|he tells a funny story in the foreground while guests react around him|party
257|car-flat-tire-plan|a safe roadside pull-off at sunset|solo|he studies a parked car's flat tire and calmly plans the next step|travel
258|rideshare-wrong-car|a well-lit curb at night|duo|he and an adult driver realize the pickup name does not match and share an awkward laugh|travel
259|roadside-diner-jukebox|a classic diner beside a jukebox at night|group|he chooses a song while three friends give competing suggestions|casual
260|city-block-power-outage|a city sidewalk during a harmless nighttime power outage|crowd|he lights his face with a phone while neighbors gather calmly in the background|outdoor

261|hiking-wrong-turn|a forest trail in bright daytime|solo|he studies a paper map at a fork and gives a self-aware grin|outdoor
262|campsite-tent-poles|a campsite at dusk|duo|he and one friend compare tent poles and laugh at their assembly mistake|outdoor
263|cabin-board-game|a warm cabin interior at night|group|he makes a bold move in a board game with three friends|casual
264|fireworks-park-crowd|a public park during a distant nighttime fireworks display|crowd|he looks upward in the foreground as an adult crowd watches safely behind|party
265|beach-wind-towel|a windy beach in bright afternoon sun|solo|he tries to fold a beach towel in the wind and laughs at the struggle|outdoor
266|paddleboard-balance|a calm lakeshore during daytime|duo|he and one adult friend steady paddleboards at the water's edge|athletic
267|boardwalk-arcade-win|a seaside arcade at blue hour|group|he shows a small prize to three friends after a playful game|casual
268|beach-festival-crowd|a lively beach festival at sunset|crowd|he walks in sharp foreground while dancers and vendors fill the background|party
269|snow-day-first-step|a snow-covered front walkway in morning light|solo|he tests the deep snow with one cautious step and a surprised expression|outdoor
270|snowball-truce|a snowy park in daylight|duo|he and one friend lower harmless snowballs and agree to a laughing truce|outdoor

271|cabin-hot-cocoa|a mountain cabin living room in evening|group|he warms his hands around a mug while three friends share a relaxed conversation|casual
272|ice-rink-crowd|an outdoor ice rink at night|crowd|he stands steadily at the rail in foreground while adult skaters move behind|outdoor
273|food-truck-choice|a row of food trucks at lunchtime|solo|he studies two menu boards kept unreadable and struggles to choose|casual
274|waiter-dropped-menu|a casual restaurant during early evening|duo|he helps an adult server retrieve a dropped menu and smiles reassuringly|smart
275|cooking-class|a bright teaching kitchen in daytime|group|he tastes a sauce while three adult classmates await his verdict|casual
276|night-market-crowd|a busy open-air night market under string lights|crowd|he carries a small food tray in sharp foreground amid moving shoppers|casual
277|thrift-store-jacket|a colorful thrift store during afternoon|solo|he tests a bold jacket in a mirror-free aisle and gives an approving nod|casual
278|sneaker-store-comparison|a modern shoe store in daytime|duo|he and one friend compare two unbranded sneakers with mock seriousness|casual
279|fitting-room-verdict|a clothing boutique fitting area in afternoon light|group|he models a jacket while three friends deliver playful reactions|smart
280|fashion-pop-up-crowd|a busy fashion pop-up event at night|crowd|he moves through the foreground in a distinctive outfit while guests browse behind|smart

281|queue-number-waiting|a clean public-service waiting room in daytime|solo|he checks his queue ticket and notices the number is still far away|smart
282|lost-and-found-counter|a transit lost-and-found desk in afternoon light|duo|he describes a missing bag to an attendant using restrained comic gestures|travel
283|community-meeting|a neighborhood meeting room in early evening|group|he offers a thoughtful suggestion to three adult neighbors|work
284|town-hall-lobby|a civic building lobby during a busy daytime event|crowd|he stands clearly in foreground as adult attendees circulate behind|smart
285|sunrise-rooftop-monologue|a quiet rooftop just after sunrise|solo|he practices an expressive skit monologue toward camera with a natural serious look|casual
286|sunset-photo-challenge|a scenic overlook at sunset|duo|he and one friend compare photographs on two cameras and debate the winner|travel
287|harmless-scare-prank|a living room at night|group|two friends reveal a harmless prank and he laughs after the initial surprise|casual
288|midnight-diner-crowd|a busy late-night diner|crowd|he sits in a foreground booth while a lively adult crowd fills the room|casual
289|first-date-arrival|a restaurant table near a window at dusk|solo|he waits with calm anticipation and checks the doorway without looking at a phone|smart
290|blind-date-mixup|a cafe entrance in early evening|duo|he and another adult realize they approached the wrong tables and laugh politely|smart

291|double-date-laughter|a warm restaurant patio at night|group|he laughs with three adult companions during an easy conversation|smart
292|anniversary-party|an elegant private celebration at night|crowd|he delivers a brief toast in the foreground while adult guests listen behind|party
293|karaoke-stage-fright|a small empty karaoke stage in evening light|solo|he grips the microphone, takes one steadying breath, and smiles at the challenge|party
294|dance-lesson-two-step|a bright dance studio in daytime|duo|he learns a two-step with one adult instructor while keeping his face visible|athletic
295|rehearsal-backstage|a theater backstage area before a show|group|he reviews the next entrance with three adult performers|work
296|dance-floor-party|a colorful party dance floor at night|crowd|he dances in crisp foreground while a full adult crowd moves behind|party
297|final-scene-bus-stop|a nearly empty city bus stop late at night|solo|he sits beneath the shelter light and delivers a quiet reflective look toward camera|outdoor
298|apology-doorstep|an apartment doorstep in soft afternoon light|duo|he offers a sincere apology to one adult friend and receives a warm response|casual
299|group-reveal-living-room|a living room during evening|group|three friends reveal unexpected good news and he processes it with growing excitement|casual
300|city-square-finale|a large city square during a nighttime public celebration|crowd|he stands centered and recognizable in the foreground as the adult crowd celebrates behind|party
'@.Trim() -split "`r?`n" | Where-Object { $_.Trim() }

if ($rows.Count -ne 100) {
    throw "Expected 100 scene rows but found $($rows.Count)."
}

$expectedIds = @(201..300)
$rowIds = @($rows | ForEach-Object { [int](($_ -split '\|', 2)[0]) })
$missingIds = @($expectedIds | Where-Object { $_ -notin $rowIds })
$duplicateIds = @($rowIds | Group-Object | Where-Object { $_.Count -gt 1 })
if ($missingIds.Count -gt 0 -or $duplicateIds.Count -gt 0) {
    throw "Scene IDs must cover 201-300 exactly once. Missing: $($missingIds -join ', ')"
}

$hairstyles = @(
    'the large natural afro shown in the two primary studio references, with real individual coils and authentic volume',
    'short natural curls with a clean tapered fade, matching the supplied short-hair references',
    'medium hanging braids or two-strand twists framing the face, matching the supplied braided references',
    'clean scalp cornrows continuing into short braids at the back, matching the supplied cornrow references',
    'a medium freeform natural afro with visible coiled texture and a soft asymmetric silhouette'
)

$views = @(
    'eye-level front-facing chest-up documentary still, 50mm lens, face large and fully readable',
    'left three-quarter waist-up candid, 50mm lens, both eyes visible',
    'right three-quarter waist-up candid, 50mm lens, both eyes visible',
    'clean left-side profile mid-shot, 85mm lens, facial silhouette unobstructed',
    'clean right-side profile mid-shot, 85mm lens, facial silhouette unobstructed',
    'eye-level full-body environmental still, 35mm lens, subject closest to camera',
    'dynamic full-body candid action frame, 35mm lens, face sharp despite movement',
    'slightly high-angle seated or leaning mid-shot, 50mm lens, natural hands',
    'subtle low-angle mid-thigh-up hero framing, 35mm lens without exaggerated anatomy',
    'over-the-shoulder turn toward camera, 50mm lens, face and rear hairstyle clearly visible'
)

$expressions = @(
    'natural deadpan reaction',
    'subtle skeptical half-smile',
    'genuine warm smile',
    'focused serious expression',
    'spontaneous mid-laugh expression',
    'surprised but believable reaction',
    'calm contemplative expression',
    'playfully frustrated expression',
    'confident conversational expression',
    'soft candid expression appropriate to the story beat'
)

$ageProfiles = @(
    'his current adult age as represented by the real references',
    'his current adult age as represented by the real references',
    'his current adult age as represented by the real references',
    'a plausible younger-adult version of the same man, approximately age 18 to 22, never a child or minor',
    'his current adult age as represented by the real references',
    'a plausible mature-adult version of the same man, approximately age 35 to 45',
    'his current adult age as represented by the real references',
    'a plausible younger-adult version of the same man, approximately age 18 to 22, never a child or minor',
    'a plausible older-adult version of the same man, approximately age 50 to 60, with restrained natural aging',
    'his current adult age as represented by the real references'
)

$characterProfiles = @(
    [pscustomobject]@{ role = 'the quick-witted lead of a contemporary apartment sitcom'; costume = 'a sharply layered casual costume with a fitted crewneck, textured overshirt, tapered trousers, clean low-top shoes, stud earrings, and a slim watch; visible seams, buttons, fabric grain, and realistic wear' },
    [pscustomobject]@{ role = 'the charming but chronically unprepared roommate in an ensemble comedy'; costume = 'a characterful color-block knit, soft tee, relaxed tailored trousers, patterned socks, simple sneakers, a small chain, and a practical canvas shoulder bag; detailed ribbing, stitching, and layered hems' },
    [pscustomobject]@{ role = 'an ambitious young manager in a workplace sitcom'; costume = 'a fitted two-piece suit with contrasting open-collar shirt, understated pocket square, leather belt, polished shoes, stud earrings, and steel watch; crisp lapels, working buttons, natural wool texture, and believable creasing' },
    [pscustomobject]@{ role = 'the charismatic owner of a neighborhood barbershop comedy'; costume = 'a premium barber jacket over a fine-gauge knit shirt, dark tailored denim, leather apron straps carried at the waist, clean boots, studs, and a metal bracelet; detailed snaps, pockets, topstitching, and brushed cotton texture' },
    [pscustomobject]@{ role = 'a gifted young chef in a fast-paced restaurant dramedy'; costume = 'a double-breasted chef coat with rolled sleeves, contrast apron, checked kitchen trousers, nonslip shoes, towel at the waist, studs, and a simple watch; realistic cotton weave, reinforced seams, buttons, and light work creases' },
    [pscustomobject]@{ role = 'an energetic local-news field reporter in a media comedy'; costume = 'a weather-ready tailored coat over a fine shirt and slim tie, pressed trousers, leather shoes, discreet earpiece wire kept away from the face, studs, watch, and handheld microphone with no logo; detailed lapels, lining, stitching, and fabric response' },
    [pscustomobject]@{ role = 'a principled public defender in a courtroom drama'; costume = 'a refined three-piece suit with waistcoat, pale dress shirt, textured tie, leather folio, polished oxfords, studs, and classic watch; precise tailoring, horn buttons, pocket construction, and natural wool drape' },
    [pscustomobject]@{ role = 'a perceptive private investigator in a modern noir mystery'; costume = 'a structured knee-length trench coat over a dark mock-neck and tailored trousers, leather gloves carried in one hand, sturdy boots, studs, and analog watch; detailed storm flap, belt hardware, lining, and rain-darkened fabric texture' },
    [pscustomobject]@{ role = 'the calm strategist of an original heist thriller'; costume = 'a sharply cut dark suit under a lightweight technical overcoat, tonal shirt, leather belt, quiet-soled shoes, slim gloves tucked into a pocket, studs, and minimalist watch; detailed hidden pockets, matte hardware, and layered technical fabrics' },
    [pscustomobject]@{ role = 'a resourceful courier in an urban action movie'; costume = 'a fitted technical jacket with articulated panels over a breathable base layer, reinforced trousers, practical boots, cross-body utility pouch, studs, and rugged watch; visible zippers, webbing, buckles, topstitching, and weathered fabric without weapons' },
    [pscustomobject]@{ role = 'the thoughtful lead of a contemporary romantic comedy'; costume = 'a soft tailored jacket over a premium knit polo, pleated trousers, leather loafers, subtle chain, studs, and elegant watch; rich knit texture, clean cuffs, refined buttons, and natural relaxed tailoring' },
    [pscustomobject]@{ role = 'a former athlete turned inspiring coach in a sports drama'; costume = 'a detailed team-neutral track jacket over a fitted performance shirt, tapered training pants, clean trainers, whistle carried at the waist, studs, and sports watch; realistic mesh, ribbed cuffs, zipper teeth, panel seams, and sweat-safe fabric' },
    [pscustomobject]@{ role = 'an independent singer-songwriter in a music-centered drama'; costume = 'a textured suede-style jacket over a ribbed shirt, dark jeans, leather boots, tasteful pendant, studs, stacked wristbands, and a guitar strap carried safely off the face; detailed nap, stitching, worn edges, and metal hardware' },
    [pscustomobject]@{ role = 'an obsessive aspiring filmmaker in a behind-the-scenes comedy'; costume = 'a multi-pocket director-style utility jacket over a soft tee, cargo-tailored trousers, sturdy sneakers, camera strap resting below the neck, studs, and digital watch; detailed pocket flaps, zippers, canvas grain, and production wear' },
    [pscustomobject]@{ role = 'an impeccably composed luxury-hotel concierge in an ensemble dramedy'; costume = 'a formal double-breasted uniform jacket with contrast piping, high-quality shirt, tailored trousers, polished shoes, discreet nameplate with no readable text, studs, and dress watch; detailed braid trim, buttons, cuffs, and structured fabric' },
    [pscustomobject]@{ role = 'a brilliant young university lecturer in an academic dramedy'; costume = 'a textured cardigan beneath a soft-shouldered blazer, open-collar Oxford shirt, pleated trousers, leather shoes, slim satchel, studs, and classic watch; visible knit pattern, elbow construction, buttons, and realistic fabric layering' },
    [pscustomobject]@{ role = 'the pilot of an original near-future science-fiction adventure'; costume = 'a grounded cinematic flight suit with segmented textile panels, padded shoulders, functional chest pockets, harness webbing kept below the neck, sturdy boots, studs, and compact wrist device; detailed seams, matte clasps, woven labels with no text, and believable technical fabric' },
    [pscustomobject]@{ role = 'a skilled ranger in an original live-action fantasy quest'; costume = 'a layered ranger costume with linen undertunic, fitted leather vest, weathered cloak pinned below the shoulder, bracers, utility belt, fitted trousers, rugged boots, studs, and carved metal accents; detailed leather grain, hand stitching, buckles, woven trim, and travel wear without weapons' },
    [pscustomobject]@{ role = 'a trusted royal advisor in an original historical fantasy drama'; costume = 'a richly tailored long coat over an embroidered high-collar tunic, sash, fitted trousers, polished boots, studs, signet-style ring, and ornamental chain below the collar; detailed brocade, embroidery, piping, buttons, and layered silk-wool textures' },
    [pscustomobject]@{ role = 'a skeptical paranormal investigator in a supernatural mystery series'; costume = 'a practical field coat over a dark henley and textured vest, durable trousers, boots, compact satchel, flashlight carried low, studs, and rugged watch; detailed canvas weave, leather trim, buckles, pocket seams, and light weathering' }
)

$costumeFinishes = @(
    'Color story: cobalt blue, burgundy, ivory, and charcoal with brushed silver hardware',
    'Color story: rust, plum, sand, and midnight navy with warm copper hardware',
    'Color story: black, graphite, pearl white, and deep red with restrained polished steel details',
    'Color story: powder blue, coral, cream, and dark indigo with matte gunmetal hardware',
    'Color story: wine red, rich navy, warm ivory, and dark brown with subtle antique-brass details'
)

$castInstructions = @{
    solo = 'The subject is the only identifiable person. No duplicate, reflection, poster face, or background person.'
    duo = 'Include exactly one supporting adult with a clearly different face and hairstyle. The subject remains larger, sharper, and visually dominant.'
    group = 'Include two to four supporting adults with distinct non-famous appearances. Keep the subject closest to camera and the only face in critical focus.'
    crowd = 'Include a believable adult crowd in middle and background. Keep the subject isolated in sharp foreground, clearly larger than every supporting face, with no identity cloning.'
}

$wardrobes = @{
    casual = @(
        'cobalt overshirt, ivory tee, charcoal trousers',
        'burgundy bomber jacket, cream shirt, dark jeans',
        'coral work jacket, white tee, navy trousers',
        'plum knit sweater, tan trousers, simple dark watch',
        'powder-blue sweatshirt, black jeans, clean white sneakers'
    )
    party = @(
        'deep-red tailored jacket, black shirt, charcoal trousers',
        'electric-blue bomber, ivory tee, burgundy trousers',
        'cream dinner jacket, midnight shirt, black trousers',
        'plum overshirt, fitted black tee, sand trousers',
        'cobalt knit polo, cream trousers, silver watch'
    )
    smart = @(
        'midnight-blue blazer, pale shirt, charcoal trousers',
        'burgundy suit jacket, cream shirt, dark trousers',
        'rust blazer, white tee, black trousers',
        'powder-blue collared shirt, navy trousers, dark belt',
        'plum overcoat, ivory knit top, charcoal trousers'
    )
    work = @(
        'navy utility overshirt, white tee, charcoal jeans',
        'burgundy cardigan, pale-blue shirt, dark trousers',
        'coral work jacket, charcoal tee, navy trousers',
        'cobalt crewneck, ivory shirt, black trousers',
        'rust overshirt, cream tee, dark denim'
    )
    athletic = @(
        'cobalt performance top, charcoal training pants, white shoes',
        'deep-red athletic tee, navy shorts, neutral trainers',
        'black fitted training shirt, burgundy shorts, gray shoes',
        'powder-blue track jacket, black pants, white sneakers',
        'cream polo, cobalt athletic trousers, coral accents'
    )
    outdoor = @(
        'deep-red waterproof shell, charcoal shirt, navy pants',
        'cobalt parka, cream scarf, charcoal trousers',
        'rust technical jacket, ivory base layer, black trail pants',
        'plum peacoat, pale shirt, dark trousers',
        'powder-blue wind shirt, sand trousers, dark boots'
    )
    travel = @(
        'camel jacket, white shirt, black travel trousers',
        'burgundy sweater, cream tee, charcoal pants',
        'cobalt marine jacket, ivory tee, dark trousers',
        'coral bomber jacket, black shirt, sand trousers',
        'midnight overcoat, powder-blue shirt, charcoal trousers'
    )
}

$items = for ($index = 0; $index -lt $rows.Count; $index++) {
    $parts = $rows[$index] -split '\|', 7
    $id = [int]$parts[0]
    $slug = $parts[1]
    $scene = $parts[2]
    $castMode = $parts[3]
    $storyBeat = $parts[4]
    $wardrobeClass = $parts[5]
    $hairstyle = $hairstyles[$index % $hairstyles.Count]
    $view = $views[$index % $views.Count]
    $expression = $expressions[$index % $expressions.Count]
    $characterProfile = $characterProfiles[$index % $characterProfiles.Count]
    $costumeFinish = $costumeFinishes[[math]::Floor($index / 20)]
    $characterRole = $characterProfile.role
    $wardrobe = "$($characterProfile.costume). $costumeFinish. Adapt the costume functionally to the named environment while preserving its character identity and detailed construction."
    $ageProfile = $ageProfiles[$index % $ageProfiles.Count]
    $castInstruction = $castInstructions[$castMode]
    if ($null -eq $castInstruction) { throw "Unknown cast mode '$castMode' for ID $id." }
    $filename = ('{0:D3}_{1}.png' -f $id, $slug)
    $localPath = Join-Path $OutputRoot $filename

    $prompt = @"
Use case: identity-preserve
Asset type: photoreal LoRA identity-training image and reusable live-action skit scene for the ByrdHouse application
Primary request: Create a genuinely new, convincingly real photograph of the exact same adult Black man shown in all five supplied real identity references, performing a grounded story beat in a live-action skit scene.
Input images: Images 1 and 2 are the primary high-clarity facial identity and large-afro references. Images 3 through 5 are secondary real references for his facial geometry, complexion, lean athletic build, smile, earrings, and alternate real hairstyles. Every reference depicts the same person. Never use any generated image as an identity source.
Scene/backdrop: $scene.
Story beat: $storyBeat.
Original character role: $characterRole. Treat this as an original live-action sitcom or movie character, not an imitation of any copyrighted or famous character.
Cast: $castInstruction Supporting adults must look like different people, never alternate versions or clones of the subject.
Subject identity: Preserve the same recognizable adult Black male in every output: his actual perceived age and masculine presentation; consistent deep-brown complexion; relatively narrow oval face; relaxed slightly hooded dark eyes with the same spacing; thick mildly angled eyebrows; medium-width rounded nose; full lips with a fuller lower lip; narrow jaw and chin; close mustache and beard boundary; hairline; small stud earrings; and lean athletic build. Do not average him into a generic model or substitute another man.
Age interpretation: $ageProfile. Preserve the same underlying facial geometry and identity through any adult age progression or regression; use anatomically plausible skin, hairline, beard density, and facial volume changes only.
Hairstyle: $hairstyle. Change only among hairstyles genuinely represented by the supplied real references.
Costume and wardrobe: $wardrobe Clothing must be photoreal, scene-appropriate, unbranded, free of readable text, and rendered with explicit construction detail suitable for later multipurpose use.
Composition/framing: $view. Even in group or crowd scenes, the subject's face must be unobstructed, properly exposed, and useful for LoRA identity training.
Performance/expression: $expression, naturally motivated by the story beat. Use believable body language and physically plausible hands.
Style/medium: premium photorealistic natural photography; a candid cinematic still from a grounded live-action comedy or drama skit; true camera optics; believable pores and skin texture; accurate hair strands and coils; real fabric behavior; practical environmental detail; coherent perspective; no beauty-filter look.
Lighting/mood: derive all light from the named time and environment with realistic shadow direction, catchlights, skin response, depth of field, motion behavior, and color temperature. Preserve complexion under day, night, practical, neon, and mixed lighting.
LoRA constraints: This must remain the same person across the dataset while adult age interpretation, character role, pose, angle, setting, cast, expression, hairstyle, and detailed costume vary. Keep the subject visually dominant and recognizable. Generate a new pose and composition rather than copying a source photograph. Do not copy the subject's face onto supporting cast. No face obstruction, sunglasses, hats, masks, heavy makeup, or hands covering key facial features.
Avoid: identity drift, different lead person, generic replacement face, changed ethnicity, lightened complexion, widened jaw, narrowed lips, altered nose, enlarged eyes, feminine features, implausible aging, bodybuilder proportions, cloned subject in background, duplicate face, extra limb, deformed hands, warped earrings, text, logo, watermark, poster layout, social-media interface, illustration, anime, cartoon, CGI, painterly rendering, waxy skin, excessive retouching, fake bokeh, impossible lighting, famous people, or minors.
"@

    [pscustomobject]@{
        id = ('{0:D3}' -f $id)
        slug = $slug
        scene = $scene
        cast_mode = $castMode
        story_beat = $storyBeat
        character_role = $characterRole
        age_profile = $ageProfile
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

$castCounts = [ordered]@{}
foreach ($mode in @('solo', 'duo', 'group', 'crowd')) {
    $castCounts[$mode] = @($items | Where-Object { $_.cast_mode -eq $mode }).Count
}

$manifest = [ordered]@{
    version = 1
    title = 'ByrdHouse 100 Photoreal LoRA Character and Skit Scenes'
    count = 100
    id_range = '201-300'
    output_root = $OutputRoot
    generator = 'Codex built-in image generation'
    identity_references = $identityReferences
    identity_contract = 'The lead is the same adult Black male in all 100 images. Use only supplied real photographs as identity references; never condition one generated scene on another.'
    training_contract = 'LoRA-oriented diversity across controlled adult age, original sitcom and movie role, pose, camera view, expression, supplied hairstyle, highly detailed costume, time, location, supporting cast, and skit action while keeping the lead face prominent and unobstructed.'
    cast_balance = $castCounts
    items = $items
}

$manifestPath = Join-Path $OutputRoot 'manifest.json'
$manifest | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath $manifestPath -Encoding utf8
$manifestPath
