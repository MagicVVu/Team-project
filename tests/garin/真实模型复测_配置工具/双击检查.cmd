@echo off
set "GARIN_PS=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe"
if exist "%GARIN_PS%" goto run
set "GARIN_PS=pwsh.exe"
where pwsh.exe >nul 2>&1
if errorlevel 1 goto missing
:run
"%GARIN_PS%" -NoLogo -NoProfile -File "%~dp0Check-DeepSeek.ps1"
echo.
pause
exit /b
:missing
echo PowerShell 7 was not found. Ask Codex to check the local tool path.
pause
