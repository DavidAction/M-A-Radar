param(
  [string]$TaskName = "TL M&A Radar Always-On Server",
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

$ActionParts = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$Starter`"",
  "-Port", $Port
)
if ($Lan) {
  $ActionParts += "-Lan"
}
$ActionArgs = $ActionParts -join " "

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ActionArgs -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 2)
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal `
  -UserId $UserId `
  -LogonType Interactive `
  -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Principal $Principal `
  -Description "Start TL M&A Radar web server at user logon and keep it available for deal review." `
  -Force | Out-Null

$ConfigDir = Join-Path $Root "tl_ma_radar\data"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$Config = [ordered]@{
  task_name = $TaskName
  installed_at = (Get-Date).ToString("o")
  user = $UserId
  port = $Port
  lan = [bool]$Lan
  url = if ($Lan) { "http://<server-ip>:$Port" } else { "http://127.0.0.1:$Port" }
  enabled = $true
  action = $ActionArgs
}
$Config | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $ConfigDir "server_task_config.json")

if ($StartNow) {
  Start-ScheduledTask -TaskName $TaskName
}

Get-ScheduledTask -TaskName $TaskName
