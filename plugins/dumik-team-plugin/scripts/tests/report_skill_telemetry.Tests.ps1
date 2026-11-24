[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptUnderTest = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\report_skill_telemetry.ps1'))
$tempFile = Join-Path ([IO.Path]::GetTempPath()) ("dumik-telemetry-test-" + [Guid]::NewGuid().ToString('N') + ".json")

$pyCode = @"
import http.server, json, socketserver, sys
out_path = sys.argv[1]
class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(body)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"code":0,"msg":"ok"}')
    def log_message(self, *args):
        pass
with socketserver.TCPServer(('127.0.0.1', 0), Handler) as httpd:
    port = httpd.server_address[1]
    print(port, flush=True)
    httpd.handle_request()
"@

$pyFile = Join-Path ([IO.Path]::GetTempPath()) ("dumik-telemetry-srv-" + [Guid]::NewGuid().ToString('N') + ".py")
[IO.File]::WriteAllText($pyFile, $pyCode, (New-Object System.Text.UTF8Encoding($false)))

$proc = $null
try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'python'
    $psi.Arguments = "`"$pyFile`" `"$tempFile`""
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $port = $proc.StandardOutput.ReadLine().Trim()
    $url = "http://127.0.0.1:$port/webhook"

    $res = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptUnderTest `
        -Event 'invoke' -Skill 'd-image-director' -Mode 'detail' -WebhookUrl $url -Test
    if ($LASTEXITCODE -ne 0) { throw "Telemetry -Test failed with exit code $LASTEXITCODE" }
    $proc.WaitForExit(5000) | Out-Null

    if (-not (Test-Path -LiteralPath $tempFile -PathType Leaf)) {
        throw "Mock server did not receive POST payload."
    }
    $received = Get-Content -LiteralPath $tempFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($received.event -ne 'invoke') { throw "Unexpected event: $($received.event)" }
    if ($received.skill -ne 'd-image-director') { throw "Unexpected skill: $($received.skill)" }
    if ($received.mode -ne 'detail') { throw "Unexpected mode: $($received.mode)" }
    if ($received.device_id -notmatch '^[a-f0-9]{12}$') { throw "Invalid device_id: $($received.device_id)" }

    # Silent failure test on unreachable endpoint (non-Test mode must exit 0)
    & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptUnderTest `
        -Event 'invoke' -Skill 'd-init' -WebhookUrl 'http://127.0.0.1:1/unreachable'
    if ($LASTEXITCODE -ne 0) { throw "Non-test mode should exit 0 on failure, got $LASTEXITCODE" }

    # Disabled switch test
    $prevDisabled = $env:DUMIK_TELEMETRY_DISABLED
    try {
        $env:DUMIK_TELEMETRY_DISABLED = '1'
        & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptUnderTest `
            -Event 'invoke' -Skill 'd-init' -WebhookUrl 'http://127.0.0.1:1/unreachable'
        if ($LASTEXITCODE -ne 0) { throw "Disabled mode should exit 0, got $LASTEXITCODE" }
    } finally {
        $env:DUMIK_TELEMETRY_DISABLED = $prevDisabled
    }

    [Console]::Out.WriteLine('{"tests":3,"passed":3,"status":"passed"}')
} finally {
    if ($proc -and -not $proc.HasExited) { $proc.Kill() }
    Remove-Item -LiteralPath $tempFile, $pyFile -Force -ErrorAction SilentlyContinue
}
