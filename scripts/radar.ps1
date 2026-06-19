param(
  [ValidateSet("start", "stop", "status")]
  [string]$Action = "start",
  [int]$Port = 8766
)

# TL M&A Radar on/off control. Used by start-radar.bat / stop-radar.bat and the desktop icons.
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot

function Get-RadarPids {
  param([int]$Port)
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($conns) { return @($conns.OwningProcess | Sort-Object -Unique) }
  return @()
}

switch ($Action) {
  "start" {
    $running = Get-RadarPids -Port $Port
    if ($running.Count -gt 0) {
      Write-Host "TL M&A Radar is already running (port $Port)."
    }
    else {
      Write-Host "Starting TL M&A Radar on port $Port ..."
      $startScript = Join-Path $root "start_radar.ps1"
      Start-Process -WindowStyle Minimized -FilePath "powershell" -ArgumentList @(
        "-ExecutionPolicy", "Bypass", "-NoProfile", "-File", $startScript, "-Port", "$Port"
      )
      for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 800
        if ((Get-RadarPids -Port $Port).Count -gt 0) { break }
      }
      if ((Get-RadarPids -Port $Port).Count -gt 0) {
        Write-Host "Server is up."
      }
      else {
        Write-Host "Server did not start within timeout. Check the minimized PowerShell window for errors."
      }
    }
    Start-Process "http://127.0.0.1:$Port"
  }
  "stop" {
    $running = Get-RadarPids -Port $Port
    if ($running.Count -eq 0) {
      Write-Host "No running server found (port $Port)."
    }
    else {
      foreach ($procId in $running) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped TL M&A Radar (PID $procId)."
      }
    }
    Start-Sleep -Seconds 1
  }
  "status" {
    $running = Get-RadarPids -Port $Port
    if ($running.Count -gt 0) { Write-Host "RUNNING (port $Port, PID $($running -join ', '))" }
    else { Write-Host "STOPPED (port $Port)" }
    Start-Sleep -Seconds 2
  }
}
