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

function Invoke-Git {
  param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GitArgs
  )
  & git -c "safe.directory=$RepoRoot" @GitArgs
}

try {
  $inside = (Invoke-Git rev-parse --is-inside-work-tree 2>$null).Trim()
} catch {
  $inside = ""
}

if ($inside -ne "true") {
  Invoke-Git init
}

Invoke-Git branch -M $Branch

$existingRemote = (Invoke-Git remote get-url $Remote 2>$null)
if ($existingRemote) {
  Invoke-Git remote set-url $Remote $RemoteUrl
} else {
  Invoke-Git remote add $Remote $RemoteUrl
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
