param(
  [string]$Message = "Update TL M&A Radar",
  [string]$Remote = "origin",
  [string]$Branch = "",
  [switch]$NoPush
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
  throw "This folder is not a Git repository. Run scripts\setup_github_remote.ps1 first."
}

if ($inside -ne "true") {
  throw "This folder is not a Git repository. Run scripts\setup_github_remote.ps1 first."
}

if (-not $Branch) {
  $Branch = (Invoke-Git branch --show-current).Trim()
}
if (-not $Branch) {
  $Branch = "main"
  Invoke-Git branch -M $Branch
}

Invoke-Git add -A
$changes = Invoke-Git status --porcelain

if ($changes) {
  Invoke-Git commit -m $Message
} else {
  Write-Host "No local changes to commit."
}

if ($NoPush) {
  Write-Host "Push skipped because -NoPush was set."
  exit 0
}

$remoteUrl = (Invoke-Git remote get-url $Remote 2>$null)
if (-not $remoteUrl) {
  Write-Host "No '$Remote' remote is configured. Commit is local only."
  Write-Host "Add a remote with: git remote add $Remote https://github.com/<owner>/<repo>.git"
  exit 0
}

Invoke-Git push -u $Remote $Branch
