[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('invoke', 'install', 'update', 'download')]
    [string]$Event,
    [string]$Skill = 'dumik-team-plugin',
    [string]$Mode = '',
    [string]$Version = '',
    [string]$HostApp = '',
    [string]$WebhookUrl = '',
    [switch]$Async,
    [switch]$Test
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:DUMIK_TELEMETRY_DISABLED -eq '1' -and -not $Test) {
    exit 0
}

$pluginRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

if ($Async -and -not $Test) {
    try {
        $argList = @(
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy', 'Bypass',
            '-File', "`"$PSCommandPath`"",
            '-Event', $Event,
            '-Skill', "`"$Skill`""
        )
        if ($Mode) { $argList += @('-Mode', "`"$Mode`"") }
        if ($Version) { $argList += @('-Version', "`"$Version`"") }
        if ($HostApp) { $argList += @('-HostApp', "`"$HostApp`"") }
        if ($WebhookUrl) { $argList += @('-WebhookUrl', "`"$WebhookUrl`"") }

        $exe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
        Start-Process -FilePath $exe -ArgumentList ($argList -join ' ') -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
    } catch {
    }
    exit 0
}

function Resolve-TelemetryConfig {
    $configPath = Join-Path $pluginRoot 'assets\telemetry-config.json'
    $enabled = $true
    $url = ''
    $timeout = 3

    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        try {
            $cfg = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($null -ne $cfg.enabled) { $enabled = [bool]$cfg.enabled }
            if ($cfg.webhookUrl) { $url = [string]$cfg.webhookUrl }
            if ($cfg.timeoutSeconds -and [int]$cfg.timeoutSeconds -gt 0) { $timeout = [int]$cfg.timeoutSeconds }
        } catch {
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($env:DUMIK_TELEMETRY_WEBHOOK)) {
        $url = $env:DUMIK_TELEMETRY_WEBHOOK.Trim()
    }
    if (-not [string]::IsNullOrWhiteSpace($WebhookUrl)) {
        $url = $WebhookUrl.Trim()
    }

    return [pscustomobject]@{
        Enabled = $enabled
        WebhookUrl = $url
        TimeoutSeconds = $timeout
    }
}

function Resolve-PluginVersion {
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        return $Version.Trim()
    }
    $verPath = Join-Path $pluginRoot 'assets\skill-versions.json'
    if (Test-Path -LiteralPath $verPath -PathType Leaf) {
        try {
            $data = Get-Content -LiteralPath $verPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($data.pluginVersion) { return [string]$data.pluginVersion }
        } catch {
        }
    }
    return 'unknown'
}

function Resolve-HostApp {
    if (-not [string]::IsNullOrWhiteSpace($HostApp)) {
        return $HostApp.Trim().ToLowerInvariant()
    }
    if ($pluginRoot -match '\.gemini\\config\\plugins') { return 'antigravity' }
    if ($pluginRoot -match '\.codex\\') { return 'codex' }
    if ($pluginRoot -match '\.zcode\\') { return 'zcode' }
    if ($env:CODEX_HOME) { return 'codex' }
    return 'local'
}

function Get-AnonymousDeviceId {
    $raw = "{0}|{1}" -f ([Environment]::MachineName), ([Environment]::UserName)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($raw)
        $hash = $sha.ComputeHash($bytes)
        $hex = ([System.BitConverter]::ToString($hash)).Replace('-', '').ToLowerInvariant()
        return $hex.Substring(0, 12)
    } finally {
        $sha.Dispose()
    }
}

try {
    $cfg = Resolve-TelemetryConfig
    if ((-not $cfg.Enabled -and -not $Test) -or [string]::IsNullOrWhiteSpace($cfg.WebhookUrl)) {
        if ($Test) {
            throw 'WebhookUrl 未配置。请先在 assets/telemetry-config.json 填入飞书多维表格 Webhook URL，或传入 -WebhookUrl 参数。'
        }
        exit 0
    }

    $payload = [ordered]@{
        event = $Event
        skill = $Skill
        mode = $Mode
        plugin_version = (Resolve-PluginVersion)
        host = (Resolve-HostApp)
        os = 'windows'
        device_id = (Get-AnonymousDeviceId)
        timestamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK')
    }

    $jsonBody = $payload | ConvertTo-Json -Compress
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)

    $response = Invoke-RestMethod `
        -Uri $cfg.WebhookUrl `
        -Method Post `
        -ContentType 'application/json; charset=utf-8' `
        -Body $bodyBytes `
        -TimeoutSec $cfg.TimeoutSeconds

    if ($Test) {
        [Console]::Out.WriteLine(([ordered]@{
            status = 'ok'
            sent = $payload
            response = $response
        } | ConvertTo-Json -Depth 5 -Compress))
    }
    exit 0
} catch {
    if ($Test) {
        [Console]::Error.WriteLine("Telemetry test failed: $($_.Exception.Message)")
        exit 1
    }
    exit 0
}
