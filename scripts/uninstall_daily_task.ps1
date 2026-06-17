param(
  [string]$TaskName = "TL M&A Radar Daily Pipeline"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$ConfigPath = Join-Path $Root "tl_ma_radar\data\scheduler_config.json"

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $Task) {
  if (Test-Path $ConfigPath) {
    $Config = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json
    $Config | Add-Member -NotePropertyName enabled -NotePropertyValue $false -Force
    $Config | Add-Member -NotePropertyName removed_at -NotePropertyValue (Get-Date).ToString("o") -Force
    $Config | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $ConfigPath
  }
  Write-Output "Task not found: $TaskName"
  exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
if (Test-Path $ConfigPath) {
  $Config = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json
  $Config | Add-Member -NotePropertyName enabled -NotePropertyValue $false -Force
  $Config | Add-Member -NotePropertyName removed_at -NotePropertyValue (Get-Date).ToString("o") -Force
  $Config | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $ConfigPath
}
Write-Output "Removed task: $TaskName"
