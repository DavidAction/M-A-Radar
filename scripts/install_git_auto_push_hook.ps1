param(
  [string]$Remote = "origin"
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

$gitDir = (Invoke-Git rev-parse --git-dir 2>$null).Trim()
if (-not $gitDir) {
  throw "Git repository is not initialized. Run scripts\setup_github_remote.ps1 first."
}

$hookDir = Join-Path $RepoRoot $gitDir
$hookPath = Join-Path $hookDir "hooks\post-commit"
$hook = @"
#!/bin/sh
remote="${Remote}"
branch="$(git branch --show-current)"

if [ -z "$branch" ]; then
  branch="main"
fi

if git remote get-url "$remote" >/dev/null 2>&1; then
  echo "Auto-pushing $branch to $remote..."
  git -c safe.directory="$RepoRoot" push -u "$remote" "$branch"
else
  echo "Auto-push skipped: remote '$remote' is not configured."
fi
"@

Set-Content -LiteralPath $hookPath -Value $hook -Encoding UTF8
Write-Host "Installed Git post-commit auto-push hook at $hookPath"
