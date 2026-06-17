param(
  [ValidateSet("full", "offline")]
  [string]$Mode = "full",

  [string]$Begin = "20250101",

  [ValidateSet("none", "latest", "all")]
  [string]$DownloadReports = "latest",

  [int]$MaxReports = 2,
  [int]$MemoLimit = 30,
  [ValidateSet("auto", "skip", "top", "all")]
  [string]$News = "top",
  [int]$NewsLimit = 120,

  [switch]$IncludePdfs,
  [switch]$SaveText,

  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
if (-not $PSBoundParameters.ContainsKey("IncludePdfs")) {
  $IncludePdfs = $true
}
if (-not $PSBoundParameters.ContainsKey("SaveText")) {
  $SaveText = $true
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$Python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

$LogDir = Join-Path $Root "tl_ma_radar\data\scheduled_runs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutLog = Join-Path $LogDir "$Stamp.out.log"
$ErrLog = Join-Path $LogDir "$Stamp.err.log"
$MetaLog = Join-Path $LogDir "$Stamp.meta.json"
$LatestMetaLog = Join-Path $LogDir "latest.meta.json"

$PipelineArgs = @(
  "scripts\run_pipeline.py",
  "--mode", $Mode,
  "--begin", $Begin,
  "--download-reports", $DownloadReports,
  "--max-reports", "$MaxReports",
  "--memo-limit", "$MemoLimit",
  "--news", $News,
  "--news-limit", "$NewsLimit"
)
if ($IncludePdfs) {
  $PipelineArgs += "--include-pdfs"
}
if ($SaveText) {
  $PipelineArgs += "--save-text"
}

Set-Location $Root
if ($DryRun) {
  [ordered]@{
    root = "$Root"
    python = $Python
    arguments = $PipelineArgs
    log_dir = $LogDir
  } | ConvertTo-Json -Depth 4
  exit 0
}

$StartedAt = (Get-Date).ToString("o")
& $Python @PipelineArgs 1> $OutLog 2> $ErrLog
$ExitCode = $LASTEXITCODE
$FinishedAt = (Get-Date).ToString("o")

$Meta = [ordered]@{
  started_at = $StartedAt
  finished_at = $FinishedAt
  exit_code = $ExitCode
  mode = $Mode
  begin = $Begin
  download_reports = $DownloadReports
  news = $News
  include_pdfs = [bool]$IncludePdfs
  save_text = [bool]$SaveText
  stdout_log = $OutLog
  stderr_log = $ErrLog
}
$Meta | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $MetaLog
$Meta | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $LatestMetaLog

if ($ExitCode -ne 0) {
  throw "TL M&A Radar pipeline failed with exit code $ExitCode. See $OutLog and $ErrLog"
}
