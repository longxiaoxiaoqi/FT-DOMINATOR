param([switch]$NoOpen, [switch]$Restart)
$ErrorActionPreference = 'Stop'
$platformRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $platformRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing Python environment. Follow platform/README.md to install requirements first.'
}
$port = if ($env:FT_PORT) { $env:FT_PORT } else { '4180' }
$url = "http://127.0.0.1:$port"
$expected = (& $python (Join-Path $platformRoot 'ft/build.py')) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read local application version.' }
function Get-Platform {
    try {
        $session = Invoke-RestMethod "$url/api/session" -TimeoutSec 2
        if ($session.app -eq 'ft-platform') { return $session }
    } catch {}
    return $null
}
$session = Get-Platform
if ($session -and $session.instance -and $session.instance -ne $expected.instance) {
    throw 'This port belongs to another FT data directory. No process was changed.'
}
if ($Restart) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($serverPid in @($listeners.OwningProcess | Select-Object -Unique)) {
        if (-not $serverPid) { continue }
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid"
        $scriptPath = Join-Path $platformRoot 'serve.py'
        if (-not $session -or -not $processInfo.CommandLine -or $processInfo.CommandLine.IndexOf($scriptPath, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw 'Port is occupied by an unverified process. No process was stopped.'
        }
    }
    foreach ($serverPid in @($listeners.OwningProcess | Select-Object -Unique)) {
        if ($serverPid) { Stop-Process -Id $serverPid -ErrorAction Stop }
    }
    foreach ($attempt in 1..30) {
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 200
    }
    $session = $null
}
if ($session -and $session.build -ne $expected.build) {
    throw 'An older application version is running. Close any unsaved form, then double-click platform/restart.bat.'
}
if (-not $session) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port is occupied. No application was started and no other process was stopped.'
    }
    & $python (Join-Path $platformRoot 'manage.py') check
    if ($LASTEXITCODE -ne 0) { throw 'Application check failed; service was not started.' }
    & $python (Join-Path $platformRoot 'manage.py') migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed.' }
    $runtime = if ($env:FT_DATA_DIR) { $env:FT_DATA_DIR } else { Join-Path $platformRoot 'runtime' }
    Start-Process -FilePath $python -ArgumentList ('"' + (Join-Path $platformRoot 'serve.py') + '"') -WorkingDirectory $platformRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'server.log') -RedirectStandardError (Join-Path $runtime 'server-error.log')
    foreach ($attempt in 1..30) {
        Start-Sleep -Milliseconds 300
        $session = Get-Platform
        if ($session) { break }
    }
}
if (-not $session -or $session.build -ne $expected.build -or $session.instance -ne $expected.instance) {
    throw 'FT platform did not start with the expected version/data directory. Check runtime/server-error.log.'
}
Write-Host "FT platform ready: $url (build $($session.build))"
if (-not $NoOpen) {
    if ($session.needs_setup) {
        $runtime = if ($env:FT_DATA_DIR) { $env:FT_DATA_DIR } else { Join-Path $platformRoot 'runtime' }
        $setupKey = (Get-Content -LiteralPath (Join-Path $runtime 'initial-setup.txt') -Raw).Trim()
        $url += '/#setup=' + $setupKey
    }
    Start-Process $url
}
