$ErrorActionPreference = 'Stop'
$viewerRoot = Split-Path -Parent $PSScriptRoot
$viewerPython = Join-Path $viewerRoot '.venv\Scripts\python.exe'
$viewerLogs = Join-Path $viewerRoot '.work\viewer'
$viewerUrl = 'http://127.0.0.1:8765'

function Test-Viewer {
    try {
        $response = Invoke-RestMethod "$viewerUrl/api/capabilities" -TimeoutSec 2
        return ($response.root -eq $viewerRoot)
    } catch { return $false }
}

if (Test-Viewer) {
    Write-Output "Viewer already running: $viewerUrl"
    exit 0
}
if (-not (Test-Path -LiteralPath $viewerPython -PathType Leaf)) {
    throw 'Python environment missing. Run uv sync first.'
}
New-Item -ItemType Directory -Path $viewerLogs -Force | Out-Null
$viewerStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$viewerStdout = Join-Path $viewerLogs "$viewerStamp.stdout.log"
$viewerStderr = Join-Path $viewerLogs "$viewerStamp.stderr.log"
$viewerProcess = Start-Process -FilePath $viewerPython `
    -ArgumentList @('-m', 'asset_auto.cli', 'serve') `
    -WorkingDirectory $viewerRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $viewerStdout -RedirectStandardError $viewerStderr
for ($viewerAttempt = 0; $viewerAttempt -lt 30; $viewerAttempt++) {
    if ($viewerProcess.HasExited) {
        throw "Viewer exited. See $viewerStderr"
    }
    if (Test-Viewer) {
        Write-Output "Viewer running in background: $viewerUrl (PID $($viewerProcess.Id))"
        exit 0
    }
    Start-Sleep -Milliseconds 200
}
throw "Viewer did not become ready. See $viewerStderr"
