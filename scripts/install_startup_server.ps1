param(
  [int]$Port = 8766,
  [switch]$Lan,
  [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$Starter = Join-Path $Root "start_radar.ps1"
if (-not (Test-Path $Starter)) {
  throw "Starter not found: $Starter"
}

$StartupDir = [Environment]::GetFolderPath("Startup")
if (-not $StartupDir) {
  throw "Could not resolve current user Startup folder."
}

$ShortcutPath = Join-Path $StartupDir "TL M&A Radar Always-On Server.cmd"
$LanArg = if ($Lan) { " -Lan" } else { "" }
$Cmd = @"
@echo off
cd /d "$Root"
start "TL M&A Radar" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Starter" -Port $Port$LanArg
"@
$Cmd | Set-Content -Encoding ASCII -Path $ShortcutPath

$ConfigDir = Join-Path $Root "tl_ma_radar\data"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$Config = [ordered]@{
  task_name = "Current User Startup"
  installed_at = (Get-Date).ToString("o")
  port = $Port
  lan = [bool]$Lan
  url = if ($Lan) { "http://<server-ip>:$Port" } else { "http://127.0.0.1:$Port" }
  enabled = $true
  action = $ShortcutPath
  method = "startup_folder"
}
$Config | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $ConfigDir "server_task_config.json")

if ($StartNow) {
  $Args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$Starter`"", "-Port", $Port)
  if ($Lan) {
    $Args += "-Lan"
  }
  Start-Process -FilePath "powershell.exe" -ArgumentList ($Args -join " ") -WindowStyle Hidden
}

Write-Host "Installed startup launcher: $ShortcutPath"
