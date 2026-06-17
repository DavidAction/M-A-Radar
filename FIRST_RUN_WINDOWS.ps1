param(
  [int]$Port = 8766,
  [switch]$Lan,
  [switch]$Start,
  [switch]$Refresh,
  [switch]$NewsAll,
  [switch]$ForceSetup
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "TL M&A Radar first-run setup"
Write-Host "Repository: $PSScriptRoot"
Write-Host ""

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "Git is not installed or not on PATH. This app can still run, but GitHub updates will not work on this PC." -ForegroundColor Yellow
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11+ is required. Install it from https://www.python.org/downloads/windows/ and rerun this script."
}

powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -Force:$ForceSetup

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $Python scripts\check_ready.py

Write-Host ""
Write-Host "Next steps"
Write-Host "1. Open .env and add DART_API_KEY / NAVER_CLIENT_ID / NAVER_CLIENT_SECRET if this PC needs fresh DART or news refresh."
Write-Host "2. Start app:"
Write-Host "   powershell -ExecutionPolicy Bypass -File .\start_radar.ps1 -Port $Port"
Write-Host "3. Browser:"
Write-Host "   http://127.0.0.1:$Port"

if ($Lan) {
  Write-Host ""
  Write-Host "LAN mode selected. Other computers on the same network can connect to:"
  Write-Host "   http://<this-computer-ip>:$Port"
  Write-Host "If blocked, allow Python or TCP port $Port in Windows Defender Firewall."
}

if ($Start) {
  $args = @("-ExecutionPolicy", "Bypass", "-File", ".\start_radar.ps1", "-Port", "$Port")
  if ($Lan) { $args += "-Lan" }
  if ($Refresh) { $args += "-Refresh" }
  if ($NewsAll) { $args += "-NewsAll" }
  powershell @args
}
