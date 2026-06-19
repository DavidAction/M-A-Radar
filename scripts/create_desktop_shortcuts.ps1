# 바탕화면에 TL M&A Radar "시작 / 종료" 아이콘(바로가기)을 만듭니다.
# 사용법: powershell -ExecutionPolicy Bypass -File scripts\create_desktop_shortcuts.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell

$shortcuts = @(
  @{ Name = "TL M&A Radar 시작"; Target = "start-radar.bat"; Icon = "System32\shell32.dll,137"; Desc = "TL M&A Radar 서버를 켜고 브라우저를 엽니다" },
  @{ Name = "TL M&A Radar 종료"; Target = "stop-radar.bat";  Icon = "System32\shell32.dll,27";  Desc = "TL M&A Radar 서버를 끕니다" }
)

foreach ($s in $shortcuts) {
  $path = Join-Path $desktop ($s.Name + ".lnk")
  $lnk = $ws.CreateShortcut($path)
  $lnk.TargetPath = Join-Path $root $s.Target
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = Join-Path $env:SystemRoot $s.Icon
  $lnk.Description = $s.Desc
  $lnk.WindowStyle = 7   # 최소화 상태로 실행 (콘솔 창 깜빡임 최소화)
  $lnk.Save()
  Write-Host ("생성: " + $path)
}

Write-Host "바탕화면 아이콘 생성을 완료했습니다."

