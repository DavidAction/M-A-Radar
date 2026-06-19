@echo off
chcp 65001 >nul
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0scripts\radar.ps1" -Action stop
timeout /t 2 >nul
