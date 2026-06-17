param(
  [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11+ is required. Install it from https://www.python.org/downloads/windows/ and rerun this script."
}

if ($Force -and (Test-Path ".venv")) {
  Remove-Item -LiteralPath ".venv" -Recurse -Force
}

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example. Add DART_API_KEY before full refresh."
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start local app: powershell -ExecutionPolicy Bypass -File .\start_radar.ps1"
Write-Host "Start for LAN:   powershell -ExecutionPolicy Bypass -File .\start_radar.ps1 -Lan"
