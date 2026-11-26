[CmdletBinding()]
param(
    [string]$CodexRoot,
    [switch]$SkipPluginInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$canonicalSource = 'https://github.com/Hill2048/dumik-design-plugins.git'
$legacySources = @(
    'https://github.com/Hill2048/dumik-codex-plugins.git'
)
$pluginName = 'dumik-team-plugin'
$expectedSkills = @(
    'd-init',
    'd-api-test',
    'd-visual-plan',
    'd-image-director',
    'd-image-runner',
    'd-video-director',
    'd-video-runner',
    'd-project-pipeline'
)

function Write-ResultAndExit {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('current', 'updated', 'skipped', 'failed')]
        [string]$Status,
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [string]$Checkout,
        [string]$Before,
        [string]$After,
        [string]$InstalledPath
    )

    $result = [ordered]@{
        status = $Status
        updated = ($Status -eq 'updated')
        message = $Message
        checkout = $Checkout
        before = $Before
        after = $After
        installedPath = $InstalledPath
    }

    [Console]::Out.WriteLine(($result | ConvertTo-Json -Compress))
    if ($Status -eq 'failed') {
        exit 1
    }
    exit 0
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$StdoutOnly
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($StdoutOnly) {
            $output = @(& $Command @Arguments 2>$null)
        } else {
            $output = @(& $Command @Arguments 2>&1)
        }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $text = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    if ($exitCode -ne 0) {
        $detail = $text.Trim()
        if ($detail.Length -gt 600) {
            $detail = $detail.Substring($detail.Length - 600)
        }
        throw "$Command failed with exit code ${exitCode}: $detail"
    }
    return $text.Trim()
}

function Test-OfficialSourceUrl {
    param([Parameter(Mandatory = $true)][string]$Url)

    $normalized = Normalize-GitUrl -Url $Url
    if ($normalized -eq (Normalize-GitUrl -Url $canonicalSource)) {
        return $true
    }
    foreach ($legacy in $legacySources) {
        if ($normalized -eq (Normalize-GitUrl -Url $legacy)) {
            return $true
        }
    }
    return $false
}

function Normalize-GitUrl {
    param([Parameter(Mandatory = $true)][string]$Url)

    $normalized = $Url.Trim().TrimEnd('/')
    if ($normalized.EndsWith('.git', [StringComparison]::OrdinalIgnoreCase)) {
        $normalized = $normalized.Substring(0, $normalized.Length - 4)
    }
    return $normalized.ToLowerInvariant()
}

function Normalize-PathForComparison {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($fullPath.StartsWith('\\?\')) {
        $fullPath = $fullPath.Substring(4)
    }
    return $fullPath.TrimEnd('\', '/').ToLowerInvariant()
}

function Assert-SkillLayout {
    param([Parameter(Mandatory = $true)][string]$PluginRoot)

    $skillsRoot = Join-Path $PluginRoot 'skills'
    if (-not (Test-Path -LiteralPath $skillsRoot -PathType Container)) {
        throw "Missing skills directory: $skillsRoot"
    }

    $actualNames = @(Get-ChildItem -LiteralPath $skillsRoot -Directory | ForEach-Object { $_.Name })
    foreach ($skillName in $expectedSkills) {
        if (-not ($actualNames -ccontains $skillName)) {
            throw "Missing lowercase skill directory: $skillName"
        }

        $skillFile = Join-Path (Join-Path $skillsRoot $skillName) 'SKILL.md'
        if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
            throw "Missing SKILL.md: $skillFile"
        }

        $frontmatterName = Get-Content -LiteralPath $skillFile -TotalCount 15 |
            Where-Object { $_ -cmatch '^name:\s*' } |
            Select-Object -First 1
        if ($frontmatterName -cne "name: $skillName") {
            throw "Skill frontmatter name is not lowercase: $skillFile"
        }
    }
}

function Assert-VideoDirectorReferences {
    param([Parameter(Mandatory = $true)][string]$PluginRoot)

    $referencesRoot = Join-Path $PluginRoot 'skills\d-video-director\references'
    foreach ($requiredName in @('prompt-compiler.md', 'directing-design.md')) {
        $requiredPath = Join-Path $referencesRoot $requiredName
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Missing video-director reference: $requiredPath"
        }
    }

    foreach ($obsoleteName in @('seedance25-prompt-compiler.md', 'cinematic-commercial-staging.md')) {
        $obsoletePath = Join-Path $referencesRoot $obsoleteName
        if (Test-Path -LiteralPath $obsoletePath -PathType Leaf) {
            throw "Obsolete video-director reference is still present: $obsoletePath"
        }
    }
}

function Repair-SkillCasing {
    param(
        [Parameter(Mandatory = $true)][string]$PluginRoot,
        [Parameter(Mandatory = $true)][string]$AllowedRoot,
        [Parameter(Mandatory = $true)][string]$LocationLabel
    )

    $normalizedPluginRoot = Normalize-PathForComparison -Path $PluginRoot
    $normalizedAllowedRoot = Normalize-PathForComparison -Path $AllowedRoot
    if ($normalizedPluginRoot -ne $normalizedAllowedRoot -and
        -not $normalizedPluginRoot.StartsWith("$normalizedAllowedRoot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to change skill casing outside the $LocationLabel root: $PluginRoot"
    }

    $skillsRoot = Join-Path $PluginRoot 'skills'
    foreach ($skillName in $expectedSkills) {
        $matches = @(Get-ChildItem -LiteralPath $skillsRoot -Directory |
            Where-Object { $_.Name -ieq $skillName })
        if ($matches.Count -ne 1) {
            throw "Expected one installed directory for $skillName, found $($matches.Count)"
        }

        $current = $matches[0]
        if ($current.Name -cne $skillName) {
            $temporaryName = ".dumik-casefix-$([Guid]::NewGuid().ToString('N'))"
            Rename-Item -LiteralPath $current.FullName -NewName $temporaryName
            Rename-Item -LiteralPath (Join-Path $skillsRoot $temporaryName) -NewName $skillName
        }
    }
}

function Remove-ObsoleteInstalledVideoReferences {
    param([Parameter(Mandatory = $true)][string]$InstalledPath)

    $referencesRoot = Join-Path $InstalledPath 'skills\d-video-director\references'
    $renamedReferences = @{
        'seedance25-prompt-compiler.md' = 'prompt-compiler.md'
        'cinematic-commercial-staging.md' = 'directing-design.md'
    }

    foreach ($obsoleteName in $renamedReferences.Keys) {
        $replacementPath = Join-Path $referencesRoot $renamedReferences[$obsoleteName]
        $obsoletePath = Join-Path $referencesRoot $obsoleteName
        if ((Test-Path -LiteralPath $replacementPath -PathType Leaf) -and
            (Test-Path -LiteralPath $obsoletePath -PathType Leaf)) {
            Remove-Item -LiteralPath $obsoletePath -Force
        }
    }
}

function Remove-DeprecatedInstalledSkills {
    param([Parameter(Mandatory = $true)][string]$InstalledPath)

    $deprecatedArchive = Join-Path $InstalledPath 'archive\deprecated-psb-tools\d-psb-install\SKILL.md'
    $staleActiveSkill = Join-Path $InstalledPath 'skills\d-psb-install'
    if ((Test-Path -LiteralPath $deprecatedArchive -PathType Leaf) -and
        (Test-Path -LiteralPath $staleActiveSkill -PathType Container)) {
        Remove-Item -LiteralPath $staleActiveSkill -Recurse -Force
    }
}

$checkout = $null
$beforeRevision = $null
$afterRevision = $null
$installedPath = $null

try {
    if ([string]::IsNullOrWhiteSpace($CodexRoot)) {
        if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
            $CodexRoot = $env:CODEX_HOME
        } else {
            $CodexRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
        }
    }
    $CodexRoot = [IO.Path]::GetFullPath($CodexRoot)

    $pluginInfo = $null
    if (-not $SkipPluginInstall) {
        $codexCmd = Get-Command 'codex' -ErrorAction SilentlyContinue
        if ($null -ne $codexCmd) {
            try {
                $pluginListJson = Invoke-NativeCommand -Command 'codex' -Arguments @('plugin', 'list', '--json') -StdoutOnly
                $pluginList = $pluginListJson | ConvertFrom-Json
                $installedPlugins = @($pluginList.installed | Where-Object { $_.name -eq $pluginName -and $_.installed })
                if ($installedPlugins.Count -eq 1) {
                    $pluginInfo = $installedPlugins[0]
                } elseif ($installedPlugins.Count -gt 1) {
                    throw "Expected one installed $pluginName entry, found $($installedPlugins.Count)"
                }
            } catch {
                if ($_.Exception.Message -like 'Expected one installed*') {
                    throw
                }
            }
        }
    }

    $marketplacesRoot = Join-Path $CodexRoot '.tmp\marketplaces'
    $matchingCheckouts = @()
    if (Test-Path -LiteralPath $marketplacesRoot -PathType Container) {
        foreach ($directory in @(Get-ChildItem -LiteralPath $marketplacesRoot -Directory -Force)) {
            $recordPath = Join-Path $directory.FullName '.codex-marketplace-install.json'
            if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) {
                continue
            }

            try {
                $record = Get-Content -Raw -LiteralPath $recordPath | ConvertFrom-Json
            } catch {
                continue
            }

            if ($record.source_type -eq 'git' -and
                (Test-OfficialSourceUrl -Url ([string]$record.source))) {
                $matchingCheckouts += $directory.FullName
            }
        }
    }

    if ($matchingCheckouts.Count -eq 0) {
        $fallbackRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
        if (Test-Path -LiteralPath (Join-Path $fallbackRepo '.git')) {
            try {
                $fallbackOrigin = Invoke-NativeCommand -Command 'git' -Arguments @('-C', $fallbackRepo, 'config', '--get', 'remote.origin.url')
                if (Test-OfficialSourceUrl -Url $fallbackOrigin) {
                    $matchingCheckouts += $fallbackRepo
                }
            } catch {
            }
        }
    }

    if ($matchingCheckouts.Count -eq 0) {
        if (-not (Test-Path -LiteralPath $marketplacesRoot -PathType Container)) {
            throw "Codex marketplace directory was not found: $marketplacesRoot"
        }
        throw 'No managed DUMIK marketplace checkout matched the official GitHub source.'
    }

    if ($null -ne $pluginInfo -and $null -ne $pluginInfo.source -and $pluginInfo.source.source -eq 'local') {
        $pluginSourcePath = [string]$pluginInfo.source.path
        foreach ($candidate in $matchingCheckouts) {
            $candidatePluginPath = Join-Path $candidate 'plugins\dumik-team-plugin'
            if ((Normalize-PathForComparison -Path $candidatePluginPath) -eq
                (Normalize-PathForComparison -Path $pluginSourcePath)) {
                $checkout = $candidate
                break
            }
        }
    }

    if ($null -eq $checkout) {
        if ($matchingCheckouts.Count -ne 1) {
            throw "Multiple DUMIK marketplace checkouts matched and the active one could not be identified."
        }
        $checkout = $matchingCheckouts[0]
    }

    $gitMarker = Join-Path $checkout '.git'
    if (-not (Test-Path -LiteralPath $gitMarker)) {
        throw "Managed marketplace checkout is not a Git repository: $checkout"
    }

    $originUrl = Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'config', '--get', 'remote.origin.url')
    if (-not (Test-OfficialSourceUrl -Url $originUrl)) {
        throw "Marketplace origin does not match the official DUMIK source: $originUrl"
    }

    if ((Normalize-GitUrl -Url $originUrl) -ne (Normalize-GitUrl -Url $canonicalSource)) {
        [void](Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'remote', 'set-url', 'origin', $canonicalSource))
    }

    $recordPath = Join-Path $checkout '.codex-marketplace-install.json'
    if (Test-Path -LiteralPath $recordPath -PathType Leaf) {
        try {
            $recordObj = Get-Content -Raw -LiteralPath $recordPath | ConvertFrom-Json
            if ($recordObj.source_type -eq 'git' -and
                (Normalize-GitUrl -Url ([string]$recordObj.source)) -ne (Normalize-GitUrl -Url $canonicalSource)) {
                $recordObj.source = $canonicalSource
                $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
                [IO.File]::WriteAllText($recordPath, ($recordObj | ConvertTo-Json -Depth 10), $utf8NoBom)
            }
        } catch {
        }
    }

    $branch = Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    if ($branch -cne 'main') {
        throw "Marketplace checkout must be on main, found: $branch"
    }

    $trackedChanges = Invoke-NativeCommand -Command 'git' -Arguments @(
        '-C', $checkout, 'status', '--porcelain=v1', '--untracked-files=no'
    )
    if (-not [string]::IsNullOrWhiteSpace($trackedChanges)) {
        Write-ResultAndExit -Status 'skipped' `
            -Message 'Local customizations preserved; remote update and reinstall skipped. Merge local changes explicitly before updating.' `
            -Checkout $checkout
    }

    $beforeRevision = Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'rev-parse', 'HEAD')
    try {
        [void](Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'pull', '--ff-only', 'origin', 'main'))
    } catch {
        $allChanges = Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'status', '--porcelain=v1')
        if (-not [string]::IsNullOrWhiteSpace($allChanges)) {
            throw
        }
        [void](Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'fetch', 'origin', 'main'))
        [void](Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'reset', '--hard', 'FETCH_HEAD'))
    }
    $afterRevision = Invoke-NativeCommand -Command 'git' -Arguments @('-C', $checkout, 'rev-parse', 'HEAD')

    $pluginRoot = Join-Path $checkout 'plugins\dumik-team-plugin'
    Repair-SkillCasing -PluginRoot $pluginRoot -AllowedRoot $checkout -LocationLabel 'marketplace checkout'
    Assert-SkillLayout -PluginRoot $pluginRoot
    Assert-VideoDirectorReferences -PluginRoot $pluginRoot

    if (-not $SkipPluginInstall -and $null -ne $pluginInfo) {
        $installJson = Invoke-NativeCommand -Command 'codex' -Arguments @('plugin', 'add', [string]$pluginInfo.pluginId, '--json') -StdoutOnly
        $installResult = $installJson | ConvertFrom-Json
        $installedPath = [string]$installResult.installedPath
        if ([string]::IsNullOrWhiteSpace($installedPath) -or
            -not (Test-Path -LiteralPath $installedPath -PathType Container)) {
            throw 'Codex did not return a valid installed plugin path.'
        }

        $cacheRoot = Join-Path $CodexRoot 'plugins\cache'
        Repair-SkillCasing -PluginRoot $installedPath -AllowedRoot $cacheRoot -LocationLabel 'Codex plugin cache'
        Remove-ObsoleteInstalledVideoReferences -InstalledPath $installedPath
        Remove-DeprecatedInstalledSkills -InstalledPath $installedPath
        Assert-SkillLayout -PluginRoot $installedPath
        Assert-VideoDirectorReferences -PluginRoot $installedPath
    }

    $telemetryScript = Join-Path $PSScriptRoot 'report_skill_telemetry.ps1'
    if (Test-Path -LiteralPath $telemetryScript -PathType Leaf) {
        try {
            $telemetryDir = Join-Path $env:LOCALAPPDATA 'dumik-telemetry'
            $installFlag = Join-Path $telemetryDir 'installed.flag'
            if (-not (Test-Path -LiteralPath $installFlag -PathType Leaf)) {
                New-Item -ItemType Directory -Force -Path $telemetryDir | Out-Null
                Set-Content -LiteralPath $installFlag -Value (Get-Date -Format 'o') -Encoding utf8
                & $telemetryScript -Event 'install' -Skill $pluginName -Async 2>$null | Out-Null
            } elseif ($beforeRevision -ne $afterRevision) {
                & $telemetryScript -Event 'update' -Skill $pluginName -Async 2>$null | Out-Null
            }
        } catch {
        }
    }

    if ($beforeRevision -eq $afterRevision) {
        Write-ResultAndExit -Status 'current' -Message 'DUMIK Team Plugin is already current.' `
            -Checkout $checkout -Before $beforeRevision -After $afterRevision -InstalledPath $installedPath
    }

    Write-ResultAndExit -Status 'updated' -Message 'DUMIK Team Plugin was updated and reinstalled.' `
        -Checkout $checkout -Before $beforeRevision -After $afterRevision -InstalledPath $installedPath
} catch {
    Write-ResultAndExit -Status 'failed' -Message $_.Exception.Message -Checkout $checkout `
        -Before $beforeRevision -After $afterRevision -InstalledPath $installedPath
}
