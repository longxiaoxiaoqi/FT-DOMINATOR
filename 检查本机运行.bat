@echo off
"%~dp0platform\.venv\Scripts\python.exe" "%~dp0platform\local_check.py"
set "check_result=%errorlevel%"
pause
exit /b %check_result%
