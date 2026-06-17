param(
  [string]$TaskName = "TL M&A Radar Daily Pipeline",
  [string]$At = "18:30",

  [ValidateSet("full", "offline")]
  [string]$Mode = "full",

  [ValidateSet("auto", "skip", "top", "all")]
  [string]$News = "top"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$Runner = Join-Path $ScriptDir "run_daily_pipeline.ps1"
if (-not (Test-Path $Runner)) {
  throw "Runner not found: $Runner"
}

$Time = [datetime]::ParseExact($At, "HH:mm", $null)
$ActionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$Runner`"",
  "-Mode", $Mode,
  "-News", $News,
  "-IncludePdfs",
  "-SaveText"
) -join " "

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ActionArgs
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 4)
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
  -Description "Refresh TL M&A Radar data, DART reports, deal memos, and monitoring changes." `
  -Force | Out-Null

$Info = Get-ScheduledTaskInfo -TaskName $TaskName
$ConfigDir = Join-Path $Root "tl_ma_radar\data"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$Config = [ordered]@{
  task_name = $TaskName
  installed_at = (Get-Date).ToString("o")
  user = $UserId
  at = $At
  mode = $Mode
  news = $News
  include_pdfs = $true
  save_text = $true
  enabled = $true
  next_run_time = $Info.NextRunTime.ToString("yyyy-MM-dd HH:mm:ss")
  action = $ActionArgs
}
$Config | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $ConfigDir "scheduler_config.json")

Get-ScheduledTask -TaskName $TaskName
