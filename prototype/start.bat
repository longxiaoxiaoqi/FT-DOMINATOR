@echo off
title 测试资源管理
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 server.py
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python server.py
  ) else (
    "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" server.py
  )
)
pause
