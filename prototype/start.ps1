param([switch]$NoOpen)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = "http://127.0.0.1:4173"

function Test-App {
    try {
        $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
        return $health.ok -eq $true
    } catch {
        return $false
    }
}

if (-not (Test-App)) {
    $bundledPython = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundledPython) {
        $python = $bundledPython
        $arguments = @("$root\server.py")
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $python = "py"
        $arguments = @("-3", "$root\server.py")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $python = "python"
        $arguments = @("$root\server.py")
    } else {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show("Python was not found. The local service cannot start.", "Test Asset Manager") | Out-Null
        exit 1
    }

    Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden
    foreach ($attempt in 1..20) {
        Start-Sleep -Milliseconds 300
        if (Test-App) { break }
    }
}

if (-not (Test-App)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("The local service failed to start. Please check README.txt.", "Test Asset Manager") | Out-Null
    exit 1
}

if (-not $NoOpen) {
    Start-Process $url
}
