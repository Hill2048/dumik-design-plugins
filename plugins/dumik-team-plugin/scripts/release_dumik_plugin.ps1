param(
  [string]$Version = "",
  [string]$Message = "",
  [string]$Notes = "",
  [string]$NotesFile = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$pluginRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$repoRoot = [IO.Path]::GetFullPath((Join-Path $pluginRoot "..\.."))

$codexManifestPath = Join-Path $pluginRoot ".codex-plugin\plugin.json"
$rootManifestPath = Join-Path $pluginRoot "plugin.json"
$skillVersionsPath = Join-Path $pluginRoot "assets\skill-versions.json"

$codexManifest = Get-Content -LiteralPath $codexManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$currentVersion = [string]$codexManifest.version

if ([string]::IsNullOrWhiteSpace($Version)) {
  if ($currentVersion -notmatch '^(\d+)\.(\d+)\.(\d+)$') {
    throw "Unsupported current version format: $currentVersion"
  }
  $major = [int]$Matches[1]
  $minor = [int]$Matches[2]
  $patch = [int]$Matches[3] + 1
  $Version = "$major.$minor.$patch"
}

$tag = "v$Version"
if ([string]::IsNullOrWhiteSpace($Message)) {
  $Message = "chore(dumik-team-plugin): release $tag"
}

Write-Host "Current version: $currentVersion -> Target version: $Version ($tag)"

if ($DryRun) {
  Write-Host "[DryRun] Skip file edits, git push, and GitHub release."
  exit 0
}

function Update-JsonVersion {
  param(
    [string]$Path,
    [string]$FieldName,
    [string]$NewValue
  )
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  $pattern = "(`"$FieldName`"\s*:\s*)`"[^`"]+`""
  $updated = [regex]::Replace($raw, $pattern, "`${1}`"$NewValue`"", 1)
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($Path, $updated, $utf8NoBom)
}

Update-JsonVersion -Path $codexManifestPath -FieldName "version" -NewValue $Version
Update-JsonVersion -Path $rootManifestPath -FieldName "version" -NewValue $Version
Update-JsonVersion -Path $skillVersionsPath -FieldName "pluginVersion" -NewValue $Version

Push-Location $repoRoot
try {
  git add -A
  git diff --cached --quiet
  if ($LASTEXITCODE -ne 0) {
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw "git commit failed." }
  }

  git push origin main
  if ($LASTEXITCODE -ne 0) { throw "git push failed." }

  $gh = Get-Command gh -ErrorAction SilentlyContinue
  if ($null -eq $gh) {
    throw "gh CLI not found; cannot publish GitHub release $tag."
  }

  $existingTags = @(gh release list --limit 30 --json tagName --jq '.[].tagName')
  if ($LASTEXITCODE -ne 0) { throw "gh release list failed." }
  $prevTag = ($existingTags | Where-Object { $_ -ne $tag } | Select-Object -First 1)

  $releaseTitle = "DUMIK Team Plugin $tag"
  $tempNotesFile = ""
  try {
    $rawNotes = ""
    if (-not [string]::IsNullOrWhiteSpace($NotesFile)) {
      if (-not (Test-Path -LiteralPath $NotesFile -PathType Leaf)) {
        throw "NotesFile not found: $NotesFile"
      }
      $rawNotes = Get-Content -LiteralPath $NotesFile -Raw -Encoding UTF8
    } elseif (-not [string]::IsNullOrWhiteSpace($Notes)) {
      $rawNotes = $Notes
    }

    $resolvedNotesFile = ""
    if (-not [string]::IsNullOrWhiteSpace($rawNotes)) {
      $cleanNotes = $rawNotes.TrimStart([char]0xFEFF).Trim()
      # Strip duplicate leading H1 title if it repeats the Release title
      $cleanNotes = [regex]::Replace($cleanNotes, '^\#\s+DUMIK\b[^\r\n]*(\r?\n)+', '')
      if ($prevTag -and ($cleanNotes -notmatch 'https://github\.com/.+/compare/')) {
        $cleanNotes = "$cleanNotes`n`n[查看与 $prevTag 的完整差异](https://github.com/Hill2048/dumik-codex-plugins/compare/$prevTag...$tag)"
      }
      $tempNotesFile = Join-Path $env:TEMP ("dumik-release-notes-$tag.md")
      $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
      [IO.File]::WriteAllText($tempNotesFile, $cleanNotes, $utf8NoBom)
      $resolvedNotesFile = $tempNotesFile
    }

    if ($existingTags -contains $tag) {
      if ($resolvedNotesFile) {
        gh release edit $tag --title $releaseTitle --notes-file $resolvedNotesFile
        if ($LASTEXITCODE -ne 0) { throw "gh release edit $tag failed." }
      } else {
        Write-Host "GitHub release $tag already exists."
      }
    } else {
      if ($resolvedNotesFile) {
        gh release create $tag --title $releaseTitle --notes-file $resolvedNotesFile
      } else {
        gh release create $tag --title $releaseTitle --generate-notes
      }
      if ($LASTEXITCODE -ne 0) { throw "gh release create $tag failed." }
    }
  } finally {
    if ($tempNotesFile -and (Test-Path -LiteralPath $tempNotesFile)) {
      Remove-Item -LiteralPath $tempNotesFile -Force -ErrorAction SilentlyContinue
    }
  }
} finally {
  Pop-Location
}

Write-Host "Released $tag successfully."
