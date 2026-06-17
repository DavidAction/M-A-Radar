param(
  [int]$Port = 8766,
  [string]$HostName = "127.0.0.1",
  [switch]$Lan,
  [switch]$InstallDeps,
  [switch]$Refresh,
  [switch]$NewsAll
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

if ($InstallDeps) {
  & $Python -m pip install -r requirements.txt
}

if ($Refresh) {
  $newsMode = if ($NewsAll) { "all" } else { "top" }
  & $Python scripts\run_pipeline.py --mode full --news $newsMode
}

$BindHost = if ($Lan) { "0.0.0.0" } else { $HostName }
Write-Host "TL M&A Radar starting at http://$HostName`:$Port"
if ($Lan) {
  Write-Host "LAN mode enabled. Use http://<this-computer-ip>:$Port from another computer on the same network."
}

& $Python app.py --host $BindHost --port $Port
