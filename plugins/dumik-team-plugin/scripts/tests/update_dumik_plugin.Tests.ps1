[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$canonicalSource = 'https://github.com/Hill2048/dumik-codex-plugins.git'
$scriptUnderTest = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\update_dumik_plugin.ps1'))
$expectedSkills = @(
    'd-init',
    'd-api-test',
    'd-psb-install',
    'd-visual-plan',
    'd-image-director',
    'd-image-runner',
    'd-video-director',
    'd-video-runner',
    'd-project-pipeline'
)
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$testRoot = Join-Path $tempBase "dumik-update-tests-$([Guid]::NewGuid().ToString('N'))"
$savedGitConfig = @{
    Count = $env:GIT_CONFIG_COUNT
    Key0 = $env:GIT_CONFIG_KEY_0
    Value0 = $env:GIT_CONFIG_VALUE_0
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$GitArguments)

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& git @GitArguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw "git $($GitArguments -join ' ') failed: $($output -join [Environment]::NewLine)"
    }
    return ($output -join [Environment]::NewLine).Trim()
}

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($Actual -cne $Expected) {
        throw "$Label expected '$Expected', got '$Actual'"
    }
}

function Set-GitRewrite {
    param([Parameter(Mandatory = $true)][string]$TargetPath)

    $targetUri = ([Uri][IO.Path]::GetFullPath($TargetPath)).AbsoluteUri
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = "url.$targetUri.insteadOf"
    $env:GIT_CONFIG_VALUE_0 = $canonicalSource
}

function New-TestCodexRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$RemotePath
    )

    $codexRoot = Join-Path $testRoot $Name
    $checkout = Join-Path $codexRoot '.tmp\marketplaces\dumik-team'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $checkout) | Out-Null
    [void](Invoke-Git -GitArguments @('clone', $RemotePath, $checkout))
    [void](Invoke-Git -GitArguments @('-C', $checkout, 'remote', 'set-url', 'origin', $canonicalSource))
    @{
        source_type = 'git'
        source = $canonicalSource
        ref_name = $null
        sparse_paths = @()
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $checkout '.codex-marketplace-install.json')

    return [pscustomobject]@{
        CodexRoot = $codexRoot
        Checkout = $checkout
    }
}

function Invoke-UpdateTest {
    param(
        [Parameter(Mandatory = $true)][string]$CodexRoot,
        [Parameter(Mandatory = $true)][int]$ExpectedExitCode
    )

    $output = @(& powershell -NoProfile -ExecutionPolicy Bypass -File $scriptUnderTest `
        -CodexRoot $CodexRoot -SkipPluginInstall 2>&1)
    $exitCode = $LASTEXITCODE
    Assert-Equal -Actual $exitCode -Expected $ExpectedExitCode -Label 'exit code'
    $jsonLine = ($output | ForEach-Object { $_.ToString() } | Select-Object -Last 1)
    return $jsonLine | ConvertFrom-Json
}

try {
    New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
    $remotePath = Join-Path $testRoot 'remote.git'
    $seedPath = Join-Path $testRoot 'seed'
    [void](Invoke-Git -GitArguments @('init', '--bare', '--initial-branch=main', $remotePath))
    [void](Invoke-Git -GitArguments @('init', '-b', 'main', $seedPath))
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'config', 'user.email', 'dumik-tests@example.invalid'))
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'config', 'user.name', 'DUMIK Tests'))

    foreach ($skillName in $expectedSkills) {
        $skillDirectory = Join-Path $seedPath "plugins\dumik-team-plugin\skills\$skillName"
        New-Item -ItemType Directory -Force -Path $skillDirectory | Out-Null
        @(
            '---'
            "name: $skillName"
            'description: Test fixture.'
            '---'
            ''
            '# Test fixture'
        ) | Set-Content -LiteralPath (Join-Path $skillDirectory 'SKILL.md')
    }

    $videoReferences = Join-Path $seedPath 'plugins\dumik-team-plugin\skills\d-video-director\references'
    New-Item -ItemType Directory -Force -Path $videoReferences | Out-Null
    Set-Content -LiteralPath (Join-Path $videoReferences 'prompt-compiler.md') -Value '# Test compiler'
    Set-Content -LiteralPath (Join-Path $videoReferences 'directing-design.md') -Value '# Test directing design'

    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'add', '.'))
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'commit', '-m', 'initial'))
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'remote', 'add', 'origin', $remotePath))
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'push', '-u', 'origin', 'main'))
    Set-GitRewrite -TargetPath $remotePath

    $currentFixture = New-TestCodexRoot -Name 'current' -RemotePath $remotePath
    $caseTestRoot = Join-Path $currentFixture.Checkout 'plugins\dumik-team-plugin\skills'
    $caseTestSource = Join-Path $caseTestRoot 'd-image-runner'
    $caseTestTemporary = Join-Path $caseTestRoot ".case-test-$([Guid]::NewGuid().ToString('N'))"
    Rename-Item -LiteralPath $caseTestSource -NewName (Split-Path -Leaf $caseTestTemporary)
    Rename-Item -LiteralPath $caseTestTemporary -NewName 'D-image-runner'
    $currentResult = Invoke-UpdateTest -CodexRoot $currentFixture.CodexRoot -ExpectedExitCode 0
    Assert-Equal -Actual $currentResult.status -Expected 'current' -Label 'already-current status'
    $repairedNames = @(Get-ChildItem -LiteralPath $caseTestRoot -Directory | ForEach-Object { $_.Name })
    if (-not ($repairedNames -ccontains 'd-image-runner')) {
        throw 'Current checkout skill casing was not repaired.'
    }

    Set-Content -LiteralPath (Join-Path $seedPath 'revision.txt') -Value 'second revision'
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'add', 'revision.txt'))
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'commit', '-m', 'second'))
    [void](Invoke-Git -GitArguments @('-C', $seedPath, 'push', 'origin', 'main'))
    $updatedResult = Invoke-UpdateTest -CodexRoot $currentFixture.CodexRoot -ExpectedExitCode 0
    Assert-Equal -Actual $updatedResult.status -Expected 'updated' -Label 'fast-forward status'
    if (-not (Test-Path -LiteralPath (Join-Path $currentFixture.Checkout 'revision.txt') -PathType Leaf)) {
        throw 'Fast-forward did not bring the new revision into the checkout.'
    }

    $dirtyFixture = New-TestCodexRoot -Name 'dirty' -RemotePath $remotePath
    Add-Content -LiteralPath (Join-Path $dirtyFixture.Checkout 'revision.txt') -Value 'tracked local edit'
    $dirtyResult = Invoke-UpdateTest -CodexRoot $dirtyFixture.CodexRoot -ExpectedExitCode 0
    Assert-Equal -Actual $dirtyResult.status -Expected 'skipped' -Label 'dirty-checkout status'
    if ($dirtyResult.message -notmatch 'Local customizations preserved') {
        throw "Dirty-checkout skip was not explicit: $($dirtyResult.message)"
    }

    $offlineFixture = New-TestCodexRoot -Name 'offline' -RemotePath $remotePath
    Set-GitRewrite -TargetPath (Join-Path $testRoot 'missing-remote.git')
    $offlineResult = Invoke-UpdateTest -CodexRoot $offlineFixture.CodexRoot -ExpectedExitCode 1
    Assert-Equal -Actual $offlineResult.status -Expected 'failed' -Label 'offline status'
    if ($offlineResult.message -notmatch 'git failed') {
        throw "Offline failure was not reported as a Git failure: $($offlineResult.message)"
    }

    [Console]::Out.WriteLine('{"tests":4,"passed":4,"status":"passed"}')
} finally {
    $env:GIT_CONFIG_COUNT = $savedGitConfig.Count
    $env:GIT_CONFIG_KEY_0 = $savedGitConfig.Key0
    $env:GIT_CONFIG_VALUE_0 = $savedGitConfig.Value0

    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    if ($resolvedTestRoot.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase) -and
        $resolvedTestRoot -ne $tempBase -and (Test-Path -LiteralPath $resolvedTestRoot)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
