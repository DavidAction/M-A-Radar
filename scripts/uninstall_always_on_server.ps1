param(
  [string]$TaskName = "TL M&A Radar Always-On Server"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$ConfigPath = Join-Path $Root "tl_ma_radar\data\server_task_config.json"
if (Test-Path $ConfigPath) {
  Remove-Item -LiteralPath $ConfigPath -Force
}

Write-Host "Removed scheduled task: $TaskName"
