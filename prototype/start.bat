@echo off
chcp 65001 >nul
title 测试资源管理
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 pause
