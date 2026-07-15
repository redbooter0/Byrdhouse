param(
    [string]$Root = "E:\ByrdHouse"
)

$ErrorActionPreference = "Stop"
$safePath = Join-Path $Root "workflows\flux2_klein\safe_first_run.json"
$variantDir = Join-Path $Root "Images\Workflows\flux2_klein_real_to_gaming"

function Read-Json([string]$Path) {
    Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

function Write-Json($Value, [string]$Path) {
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $json = $Value | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($Path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

function Clone-Json($Value) {
    (($Value | ConvertTo-Json -Depth 100) | ConvertFrom-Json)
}

function Set-NoteProperty($Object, [string]$Name, $Value) {
    $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value -Force
}

function Get-Node($Workflow, [string]$Id) {
    @($Workflow.nodes | Where-Object { $_.id.ToString() -eq $Id })[0]
}

function Set-Prompt($Workflow, [string]$Prompt) {
    $node = Get-Node $Workflow "92:74"
    $node.widgets_values = @($Prompt)
}

function Add-Link($Workflow, [int]$Id, [string]$Origin, [int]$OriginSlot, [string]$Target, [int]$TargetSlot, [string]$Type) {
    $Workflow.links += ,@($Id, $Origin, $OriginSlot, $Target, $TargetSlot, $Type)
}

function Rebuild-Links($Workflow) {
    $removed = @("104", "105", "106", "107", "108", "110", "112", "116", "117", "118", "119", "120", "121", "122", "123", "124")
    $Workflow.nodes = @($Workflow.nodes | Where-Object { $removed -notcontains $_.id.ToString() })
    $Workflow.links = @($Workflow.links | Where-Object {
        $removed -notcontains $_[1].ToString() -and $removed -notcontains $_[3].ToString()
    })

    $next = [int]$Workflow.last_link_id + 1
    Add-Link $Workflow $next "92:70" 0 "92:63" 0 "MODEL"; $next += 1
    Add-Link $Workflow $next "92:71" 0 "92:74" 0 "CLIP"; $next += 1
    Add-Link $Workflow $next "92:72" 0 "92:84:78" 1 "VAE"; $next += 1
    Add-Link $Workflow $next "92:72" 0 "92:79:78" 1 "VAE"; $next += 1
    Add-Link $Workflow $next "92:72" 0 "92:65" 1 "VAE"; $next += 1
    Add-Link $Workflow $next "92:81" 0 "92:62" 1 "INT"; $next += 1
    Add-Link $Workflow $next "92:81" 1 "92:62" 2 "INT"; $next += 1
    Add-Link $Workflow $next "92:81" 0 "92:66" 0 "INT"; $next += 1
    Add-Link $Workflow $next "92:81" 1 "92:66" 1 "INT"; $next += 1
    Add-Link $Workflow $next "92:65" 0 "98" 1 "IMAGE"; $next += 1

    foreach ($node in @($Workflow.nodes)) {
        foreach ($input in @($node.inputs)) {
            if ($null -ne $input) { $input.link = $null }
        }
        foreach ($output in @($node.outputs)) {
            if ($null -ne $output) { $output.links = $null }
        }
    }
    foreach ($link in @($Workflow.links)) {
        $origin = Get-Node $Workflow $link[1].ToString()
        $target = Get-Node $Workflow $link[3].ToString()
        if ($null -eq $origin -or $null -eq $target) { continue }
        $targetInput = @($target.inputs)[$link[4]]
        if ($null -ne $targetInput) { $targetInput.link = $link[0] }
        $originOutput = @($origin.outputs)[$link[2]]
        if ($null -ne $originOutput) {
            if ($null -eq $originOutput.links) { $originOutput.links = @() }
            $originOutput.links += $link[0]
        }
    }
    $Workflow.last_link_id = $next - 1
}

$styleModes = [ordered]@{
    AAA = "AAA semi-realistic game character: grounded anatomy, cinematic materials, premium promotional render, restrained stylization."
    HERO = "Stylized hero character: iconic silhouette, confident readable shapes, polished hero presentation, controlled exaggeration."
    FANTASY = "Fantasy RPG: believable leather, cloth, metal, and crafted fantasy materials; grounded fantasy costume language and adventure lighting."
    SCIFI = "Sci-fi operative: tactical fabric, polymer, brushed metal, subtle emissive accents, functional equipment, cool cinematic lighting."
    CEL_SHADED = "Cel-shaded game character: clean graphic planes, deliberate contour separation, simplified controlled shading, readable colors."
    GRITTY = "Dark action-game character: gritty practical materials, restrained palette, hard directional light, atmospheric tension, realistic wear."
    SPLASH_ART = "Promotional splash art: strong hero read, dynamic cinematic lighting, environmental atmosphere, polished marketing key-art finish."
}

$intensityProfiles = [ordered]@{
    IDENTITY_LOCK = "Maximum likeness preservation; subtle game conversion; conservative costume changes; preserve pose and silhouette."
    BALANCED_GAMING = "Strong identity retention; obvious game-character conversion; moderate costume and material redesign."
    FULL_CHARACTER_REDESIGN = "Identity remains recognizable; stronger costume transformation; stronger stylization; more dramatic game-world presentation."
}

$workflow = Read-Json $safePath
Rebuild-Links $workflow
$meta = $workflow.extra.byrdhouse
Set-NoteProperty $meta "workflow_version" "2.1.0"
Set-NoteProperty $meta "compatibility_patch" "Removed unavailable legacy GetNode/SetNode storage helpers and rewired to native outputs."
Set-NoteProperty $meta "composition_modes" ([ordered]@{
    PRIMARY_HEAD_ONLY = "Main-subject identity is protected; other visible heads remain governed by the game scene or style reference."
    ALL_HEADS = "Reserved multi-person mode; requires separate identity references or masks per person and is not enabled in SAFE_FIRST_RUN."
})
Set-NoteProperty $meta "style_modes" $styleModes
Set-NoteProperty $meta "intensity_profiles" $intensityProfiles
Set-NoteProperty $meta "style_mode_default" "AAA"
Set-NoteProperty $meta "intensity_profile_default" "BALANCED_GAMING"
Set-NoteProperty $meta "face_mode_default" "PRIMARY_HEAD_ONLY"
Set-NoteProperty $meta "reference_library" "E:\ByrdHouse\profiles\me\references"
Write-Json $workflow $safePath

$basePrompt = [string]((Get-Node $workflow "92:74").widgets_values[0])
$variants = @(
    @{ slug = "aaa_semirealistic"; name = "AAA SEMI-REALISTIC"; style = "AAA"; extra = "" },
    @{ slug = "hero_splash"; name = "STYLIZED HERO + SPLASH ART"; style = "HERO"; extra = " Add promotional splash-art presentation and an iconic hero read." },
    @{ slug = "fantasy_rpg"; name = "FANTASY RPG"; style = "FANTASY"; extra = "" },
    @{ slug = "scifi_operative"; name = "SCI-FI OPERATIVE"; style = "SCIFI"; extra = "" },
    @{ slug = "cel_shaded_action"; name = "CEL-SHADED + DARK ACTION"; style = "CEL_SHADED"; extra = " Add restrained dark action-game mood and controlled graphic shadow shapes." }
)

foreach ($variant in $variants) {
    $copy = Clone-Json $workflow
    $copy.extra.byrdhouse.profile = "REAL_TO_GAME_$($variant.slug.ToUpper())"
    $copy.extra.byrdhouse.workflow_name = "ByrdHouse Flux2 Klein Real-to-Gaming - $($variant.name)"
    $copy.extra.byrdhouse.style_mode_default = $variant.style
    $prompt = $basePrompt -replace "STYLE MODE: AAA\.", "STYLE MODE: $($variant.style)."
    $prompt = $prompt -replace "INTENSITY PROFILE: BALANCED GAMING\.", "INTENSITY PROFILE: BALANCED GAMING.$($variant.extra)"
    Set-Prompt $copy $prompt
    $out = Join-Path $variantDir ("byrdhouse_flux2_klein_real_to_gaming_$($variant.slug)_ui_v1.json")
    Write-Json $copy $out
}

Write-Output "Patched SAFE workflow: $safePath"
Write-Output "Created five UI variants under: $variantDir"
