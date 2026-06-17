$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "TL M&A Radar Always-On Server.cmd"

if (Test-Path $ShortcutPath) {
  Remove-Item -LiteralPath $ShortcutPath -Force
}

$ConfigPath = Join-Path $Root "tl_ma_radar\data\server_task_config.json"
if (Test-Path $ConfigPath) {
  Remove-Item -LiteralPath $ConfigPath -Force
}

Write-Host "Removed startup launcher: $ShortcutPath"
