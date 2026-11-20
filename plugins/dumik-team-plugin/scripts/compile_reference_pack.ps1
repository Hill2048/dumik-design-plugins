param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('d-init','d-image-director','d-image-runner','d-consistency-check','d-prompt-reverse','d-video-director','d-video-runner','d-visual-plan','d-project-pipeline','d-api-test','d-psb-install')]
    [string]$Skill,
    [string]$Mode = 'default',
    [string]$Model = '',
    [string]$ProjectRoot = '',
    [string]$OutputPath = '',
    [switch]$FullReferenceArchive
)

$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path -Parent $PSScriptRoot
$modeText = $Mode.ToLowerInvariant()
$modelText = $Model.ToLowerInvariant()
$refs = New-Object System.Collections.Generic.List[string]

if ($Mode -eq 'default') {
    throw "Mode is required for $Skill. Choose the mode named in that skill's SKILL.md before compiling the reference pack."
}

function Add-Ref([string]$relativePath) {
    $fullPath = Join-Path $pluginRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Reference file not found: $relativePath"
    }
    if (-not $refs.Contains($relativePath)) { [void]$refs.Add($relativePath) }
}

Add-Ref 'assets/reference-loading-protocol.md'
Add-Ref 'assets/agent-skill-routing.md'

switch ($Skill) {
    'd-init' {
        Add-Ref 'assets/project-env-protocol.md'
        Add-Ref 'skills/d-init/references/entry-templates.md'
        if ($ProjectRoot -and (Test-Path (Join-Path $ProjectRoot 'AGENTS.md'))) { Add-Ref 'assets/task-state-contract.md' }
    }
    'd-image-director' {
        Add-Ref 'assets/task-state-contract.md'
        Add-Ref 'assets/image-reference-format.md'
        Add-Ref 'skills/d-image-director/references/control-layer.md'
        Add-Ref 'skills/d-image-director/references/prompt-contract.md'
        if ($modeText -match 'legacy' -and $modeText -notmatch '^(detail|milestone)') {
            Add-Ref 'skills/d-image-director/references/original.md'
        }
        switch -Regex ($modeText) {
            '^(detail|milestone)' {
                Add-Ref 'skills/d-image-director/references/prompt-segments.md'
                Add-Ref 'skills/d-image-director/references/lighting-control.md'
                Add-Ref 'skills/d-image-director/references/camera-language.md'
                Add-Ref 'skills/d-image-director/references/realism.md'
                Add-Ref 'assets/detail-page-prompt-packs/README.md'
                if ($modeText -match 'plan|strategy|translate|策划|翻译') {
                    Add-Ref 'skills/d-visual-plan/references/visual-selling-translation.md'
                }
                if ($modeText -match 'contrast|对比') { Add-Ref 'assets/detail-page-prompt-packs/proof-by-contrast.json' }
                if ($modeText -match 'macro|material|材质|微距') { Add-Ref 'assets/detail-page-prompt-packs/proof-by-material-macro.json' }
                if ($modeText -match 'scene|场景') { Add-Ref 'assets/detail-page-prompt-packs/proof-by-scene.json' }
                if ($modeText -match 'structure|callout|结构') { Add-Ref 'assets/detail-page-prompt-packs/proof-by-structure-callout.json' }
                if ($modeText -match 'lifestyle|生活') { Add-Ref 'assets/detail-page-prompt-packs/proof-by-lifestyle.json' }
                if ($modeText -match 'poster|ad|海报|主图|kv') { Add-Ref 'assets/detail-page-prompt-packs/proof-by-ad-poster.json' }
            }
            'edit|brief' {
                Add-Ref 'skills/d-image-director/references/prompt-segments.md'
                Add-Ref 'skills/d-image-director/references/six-structure.md'
                if ($modeText -match 'legacy') { Add-Ref 'skills/d-image-director/references/legacy/D-image-prompt.md' }
            }
            'direction' {
                Add-Ref 'skills/d-image-director/references/prompt-segments.md'
                Add-Ref 'skills/d-image-director/references/legacy/D-grid-prompt.md'
            }
            'hd' {
                Add-Ref 'skills/d-image-director/references/prompt-segments.md'
                Add-Ref 'skills/d-image-director/references/legacy/D-image-HD.md'
            }
            'repair' { Add-Ref 'skills/d-image-director/references/legacy/D-image-repair.md' }
        }
        if ($modeText -match 'six') { Add-Ref 'skills/d-image-director/references/six-structure.md' }
        if ($modeText -match 'person|model|talent|material|texture|repair|space|template|袖|手|人') { Add-Ref 'skills/d-image-director/references/templates.md' }
        if ($modeText -match 'white|scene|白底') { Add-Ref 'skills/d-image-director/references/white-to-scene.md' }
        if ($modeText -match 'light|lighting|shadow|c4d|光影') { Add-Ref 'skills/d-image-director/references/lighting-control.md' }
        if ($modeText -match 'camera|lens|focal|composition|framing|广角|机位|构图|视角') { Add-Ref 'skills/d-image-director/references/camera-language.md' }
        if ($modeText -match 'realism|真实') { Add-Ref 'skills/d-image-director/references/realism.md' }
        if ($modeText -match 'multiview|multi-view|logo|多视') { Add-Ref 'skills/d-image-director/references/multi-view-lock.md' }
        if ($modeText -match 'model|talent|person|hand|wrist|sleeve|佩戴|模特|人|手|腕|袖') { Add-Ref 'skills/d-image-director/references/model-product.md' }
        if ($modeText -match 'json|module|模块') { Add-Ref 'skills/d-image-director/references/prompt-json-modules.md' }
    }
    'd-prompt-reverse' {
        Add-Ref 'assets/image-reference-format.md'
        Add-Ref 'assets/workflow-chain.md'
        Add-Ref 'skills/d-prompt-reverse/references/reverse-protocol.md'
        Add-Ref 'skills/d-image-director/references/control-layer.md'
        Add-Ref 'skills/d-image-director/references/prompt-segments.md'
        Add-Ref 'skills/d-image-director/references/six-structure.md'
    }
    'd-consistency-check' {
        Add-Ref 'assets/image-reference-format.md'
        Add-Ref 'skills/d-consistency-check/references/checklist.md'
    }
    'd-image-runner' {
        Add-Ref 'assets/task-state-contract.md'
        Add-Ref 'assets/image-reference-format.md'
        if ($modeText -match 'legacy') { Add-Ref 'skills/d-image-runner/references/legacy/D-image-run.md' }
        if ($modeText -match 'batch|json|results') { Add-Ref 'skills/d-image-runner/references/results-input-example.json' }
        if ($modeText -match 'postprocess|rh|upscale|remove-bg|cutout') {
            Add-Ref 'skills/d-image-runner/references/legacy/D-rh.md'
            Add-Ref 'skills/d-image-runner/references/model-runninghub-workflow.md'
        }
        if ($modelText -match 'image2\.5|flare|sunburst') { Add-Ref 'skills/d-image-runner/references/model-image2.5.md' }
        elseif ($modelText -match 'banana|gemini-3|flash-image|pro-image') { Add-Ref 'skills/d-image-runner/references/model-banana2.md' }
        elseif ($modelText -match 'image2') { Add-Ref 'skills/d-image-runner/references/model-image2.md' }
        elseif ($modeText -notmatch 'postprocess|rh|upscale|remove-bg|cutout') { Add-Ref 'skills/d-image-runner/references/model-banana2.md' }
    }
    'd-video-director' {
        Add-Ref 'assets/task-state-contract.md'
        Add-Ref 'assets/image-reference-format.md'
        Add-Ref 'skills/d-video-director/references/prompt-compiler.md'
        Add-Ref 'skills/d-video-director/references/directing-design.md'
        if ($modeText -match 'report|analysis|evidence|html') { Add-Ref 'skills/d-video-director/references/report-data-schema.md' }
        if ($modeText -match 'interactive|timeline|review') { Add-Ref 'skills/d-video-director/references/interactive-report.md' }
        if ($modeText -match 'storyboard|shot|keyframe|scene|sequence') { Add-Ref 'skills/d-video-director/references/templates.md' }
        if ($modeText -match 'image-to-video|first-frame|product') { Add-Ref 'skills/d-video-director/references/seedance-image-to-video.md' }
        if ($modeText -match 'storyboard') { Add-Ref 'skills/d-video-director/references/seedance-storyboard-driven.md' }
        if ($modeText -match 'depth') { Add-Ref 'skills/d-video-director/references/depth-video.md' }
        if ($modeText -match 'camera|trajectory|track|orbit|compound') { Add-Ref 'skills/d-video-director/references/seedance-camera-codec.md' }
        Add-Ref 'skills/d-video-director/references/video-methodology-mcsla.md'
        if ($modeText -match 'storyboard|shot|shotlist|keyframe|scene|sequence|prompt|pipeline|director') { Add-Ref 'skills/d-video-director/references/video-directing-shotlist.md' }
        if ($modeText -match 'acting|performance|character|dialogue|troubleshoot|diagnose|fix|failure|repair|report|analysis') { Add-Ref 'skills/d-video-director/references/video-acting-and-failure-modes.md' }
    }
    'd-video-runner' {
        Add-Ref 'assets/task-state-contract.md'
        Add-Ref 'assets/image-reference-format.md'
        Add-Ref 'skills/d-video-runner/references/legacy/D-video-run.md'
        if ($modeText -match 'batch|json|results') { Add-Ref 'skills/d-video-runner/references/results-input-example.json' }
        if ($modelText -match 'veo') { Add-Ref 'skills/d-video-runner/references/veo.md' }
        if ($modelText -match 'seedance|dreamina' -or -not $modelText) { Add-Ref 'skills/d-video-runner/references/seedance-platform-limits.md' }
    }
    'd-visual-plan' {
        Add-Ref 'assets/task-state-contract.md'
        Add-Ref 'skills/d-visual-plan/references/task-decompose.md'
        if ($modeText -match 'video') {
            if ($modeText -match 'legacy') { Add-Ref 'skills/d-visual-plan/references/legacy/D-video-plan.md' }
        }
        elseif ($modeText -match 'original') {
            Add-Ref 'skills/d-visual-plan/references/original.md'
        }
        else {
            if ($modeText -match 'legacy') { Add-Ref 'skills/d-visual-plan/references/legacy/D-detail-plan.md' }
            Add-Ref 'skills/d-visual-plan/references/visual-selling-translation.md'
        }
        if ($modeText -match 'canvas|feishu') { Add-Ref 'skills/d-visual-plan/references/feishu-canvas-decompose.md' }
        if ($modeText -match 'seedance|dreamina') { Add-Ref 'skills/d-visual-plan/references/seedance-creative-strategy.md' }
    }
    'd-project-pipeline' {
        Add-Ref 'assets/task-state-contract.md'
        Add-Ref 'skills/d-project-pipeline/references/canvas-auto-pipeline.md'
        if ($modeText -match 'legacy') { Add-Ref 'skills/d-project-pipeline/references/legacy/D-detail-auto.md' }
        if ($modeText -match 'canvas|feishu') { Add-Ref 'skills/d-visual-plan/references/visual-selling-translation.md' }
    }
    'd-api-test' {
        Add-Ref 'skills/d-api-test/references/image-benchmark.md'
    }
    'd-psb-install' {
        Add-Ref 'assets/task-state-contract.md'
        Add-Ref 'assets/skill-versions.json'
        Add-Ref 'scripts/install_psb_smart_object_tools.ps1'
    }
}

# The active skill's entire references tree is always registered. The mode map above
# selects the files whose full content is needed for this task. This distinction is
# what keeps the receipt complete without putting every historical/template file in
# every prompt-writing context.
$selectedRefs = New-Object System.Collections.Generic.List[string]
foreach ($selectedRef in @($refs)) { [void]$selectedRefs.Add($selectedRef) }
$skillReferencesRoot = Join-Path $pluginRoot ("skills/{0}/references" -f $Skill)
if (Test-Path -LiteralPath $skillReferencesRoot -PathType Container) {
    foreach ($referenceFile in (Get-ChildItem -LiteralPath $skillReferencesRoot -Recurse -File | Sort-Object FullName)) {
        $relativePath = $referenceFile.FullName.Substring($pluginRoot.Length + 1).Replace('\', '/')
        Add-Ref $relativePath
    }
}

# Follow local Markdown links from selected files. A reference file can point to a
# model table, template, example, or script that is part of the same rule chain.
# External URLs and missing illustrative links are ignored; explicit Add-Ref calls
# above still fail loudly when a required file is missing.
$pluginRootFull = [System.IO.Path]::GetFullPath($pluginRoot).TrimEnd('\') + '\'
$scanQueue = New-Object System.Collections.Generic.Queue[string]
foreach ($selectedRef in @($selectedRefs)) { $scanQueue.Enqueue($selectedRef) }
$scannedRefs = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
while ($scanQueue.Count -gt 0) {
    $sourceRef = $scanQueue.Dequeue()
    if (-not $scannedRefs.Add($sourceRef)) { continue }
    $sourcePath = Join-Path $pluginRoot $sourceRef
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { continue }
    $sourceText = Get-Content -LiteralPath $sourcePath -Raw
    $sourceDirectory = Split-Path -Parent $sourcePath
    foreach ($linkMatch in [regex]::Matches($sourceText, '\[[^\]]+\]\(([^)\s#]+)(?:#[^)]*)?\)')) {
        $linkTarget = $linkMatch.Groups[1].Value.Trim()
        if (-not $linkTarget -or $linkTarget -match '^(?i:https?|mailto):') { continue }
        try {
            $decodedTarget = [uri]::UnescapeDataString($linkTarget).Replace('/', '\')
            $candidatePath = [System.IO.Path]::GetFullPath((Join-Path $sourceDirectory $decodedTarget))
        } catch { continue }
        if (-not $candidatePath.StartsWith($pluginRootFull, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
        if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) { continue }
        $candidateRef = $candidatePath.Substring($pluginRootFull.Length).Replace('\', '/')
        if (-not $refs.Contains($candidateRef)) { Add-Ref $candidateRef }
        if (($candidateRef -match '(^|/)references/legacy/' -or $candidateRef -eq 'skills/d-image-director/references/original.md') -and (-not $selectedRefs.Contains($candidateRef))) {
            continue
        }
        if (-not $selectedRefs.Contains($candidateRef)) {
            [void]$selectedRefs.Add($candidateRef)
            $scanQueue.Enqueue($candidateRef)
        }
    }
}

$selectedSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($selectedRef in @($selectedRefs)) { [void]$selectedSet.Add($selectedRef) }

if (-not $OutputPath) {
    $packDir = Join-Path $env:TEMP 'dumik-reference-packs'
    New-Item -ItemType Directory -Force -Path $packDir | Out-Null
    $OutputPath = Join-Path $packDir ("{0}-{1}-{2}.md" -f $Skill, ($modeText -replace '[^a-z0-9_-]', '_'), (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'
$lines = New-Object System.Collections.Generic.List[string]
[void]$lines.Add('# DUMIK Task Reference Pack')
[void]$lines.Add('')
[void]$lines.Add("- Skill: $Skill")
[void]$lines.Add("- Mode: $Mode")
[void]$lines.Add("- Model: $Model")
[void]$lines.Add("- Generated: $now")
[void]$lines.Add("- Plugin root: $pluginRoot")
if ($ProjectRoot) { [void]$lines.Add("- Project root: $ProjectRoot") }
[void]$lines.Add('')
[void]$lines.Add('## Reference receipt')
[void]$lines.Add('')
[void]$lines.Add('### Task-selected references')
[void]$lines.Add('')
foreach ($relativePath in $selectedRefs) { [void]$lines.Add(('- `' + $relativePath + '`')) }
[void]$lines.Add('')
[void]$lines.Add('### Full active-skill reference inventory')
[void]$lines.Add('')
[void]$lines.Add('All files in the active skill reference tree are registered below. Only files marked `selected` are included with full正文 by default.')
[void]$lines.Add('')

function Get-ReferenceSummary([string]$fullPath) {
    $raw = Get-Content -LiteralPath $fullPath -Raw
    $summary = (($raw -split "`r?`n") | ForEach-Object { $_.Trim() } | Where-Object {
        $_ -and $_ -notmatch '^```' -and $_ -notmatch '^[-*_]{3,}$'
    } | Select-Object -First 3) -join ' '
    if (-not $summary) { $summary = '（文件无可提取的短摘要）' }
    $summary = $summary -replace '\s+', ' '
    if ($summary.Length -gt 360) { $summary = $summary.Substring(0, 360).TrimEnd() + '…' }
    return $summary
}

foreach ($relativePath in $refs) {
    $fullPath = Join-Path $pluginRoot $relativePath
    $hash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash
    $length = (Get-Item -LiteralPath $fullPath).Length
    $status = if ($selectedSet.Contains($relativePath)) { 'selected' } else { 'inventory-only' }
    $summary = Get-ReferenceSummary $fullPath
    [void]$lines.Add(('- ' + $status + ': `' + $relativePath + '` | bytes=' + $length + ' | sha256=' + $hash + ' | 摘要：' + $summary))
}

[void]$lines.Add('')
[void]$lines.Add('## Source content')
[void]$lines.Add('')
if ($FullReferenceArchive) {
    [void]$lines.Add('This is a full reference archive. It includes every registered reference file. Historical `legacy` files remain background only.')
    [void]$lines.Add('')
}
$contentRefs = if ($FullReferenceArchive) { @($refs) } else { @($selectedRefs) }
foreach ($relativePath in $contentRefs) {
    $fullPath = Join-Path $pluginRoot $relativePath
    if ($relativePath -match '/legacy/') {
        [void]$lines.Add("### $relativePath (legacy background; cannot override current rules)")
    } else {
        [void]$lines.Add("### $relativePath")
    }
    [void]$lines.Add('')
    [void]$lines.Add((Get-Content -LiteralPath $fullPath -Raw).TrimEnd())
    [void]$lines.Add('')
    [void]$lines.Add('---')
    [void]$lines.Add('')
}

$lines | Set-Content -LiteralPath $OutputPath -Encoding utf8
[pscustomobject]@{
    status = 'compiled'
    skill = $Skill
    mode = $Mode
    model = $Model
    reference_count = $refs.Count
    output_path = (Resolve-Path -LiteralPath $OutputPath).Path
    references = @($refs)
    selected_references = @($selectedRefs)
    source_content_references = @($contentRefs)
    full_reference_archive = [bool]$FullReferenceArchive
} | ConvertTo-Json -Depth 5
