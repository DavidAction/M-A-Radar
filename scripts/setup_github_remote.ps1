param(
  [Parameter(Mandatory = $true)]
  [string]$RemoteUrl,
  [string]$Branch = "main",
  [string]$Remote = "origin",
  [switch]$InstallAutoPushHook,
  [switch]$Push
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

try {
  $inside = (& git rev-parse --is-inside-work-tree 2>$null).Trim()
} catch {
  $inside = ""
}

if ($inside -ne "true") {
  & git init
}

& git branch -M $Branch

$existingRemote = (& git remote get-url $Remote 2>$null)
if ($existingRemote) {
  & git remote set-url $Remote $RemoteUrl
} else {
  & git remote add $Remote $RemoteUrl
}

if ($InstallAutoPushHook) {
  & (Join-Path $PSScriptRoot "install_git_auto_push_hook.ps1") -Remote $Remote
}

if ($Push) {
  & (Join-Path $PSScriptRoot "git_auto_push.ps1") -Message "Initial TL M&A Radar handoff" -Remote $Remote -Branch $Branch
} else {
  Write-Host "GitHub remote configured. Push with:"
  Write-Host "powershell -ExecutionPolicy Bypass -File scripts\git_auto_push.ps1 -Message `"Initial TL M&A Radar handoff`""
}
