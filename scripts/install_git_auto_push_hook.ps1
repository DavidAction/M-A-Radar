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
$SafeRepoRoot = $RepoRoot -replace "\\", "/"
$hook = @'
#!/bin/sh
remote="__REMOTE__"
branch="$(git branch --show-current)"

if [ -z "$branch" ]; then
  branch="main"
fi

if git remote get-url "$remote" >/dev/null 2>&1; then
  echo "Auto-pushing $branch to $remote..."
  git -c safe.directory="__SAFE_REPO_ROOT__" push -u "$remote" "$branch"
else
  echo "Auto-push skipped: remote '$remote' is not configured."
fi
'@

$hook = $hook.Replace("__REMOTE__", $Remote).Replace("__SAFE_REPO_ROOT__", $SafeRepoRoot)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($hookPath, $hook, $utf8NoBom)
Write-Host "Installed Git post-commit auto-push hook at $hookPath"
