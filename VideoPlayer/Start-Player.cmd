@echo off
setlocal
chcp 65001 >nul
set "playerRelease="
set /p playerRelease=<"%~dp0current-release.txt"
if not defined playerRelease goto missing
set "playerExe=%~dp0dist\%playerRelease%\GridPlayerWorkspace.exe"
if not exist "%playerExe%" goto missing
tasklist /FI "IMAGENAME eq GridPlayerWorkspace.exe" /NH 2>nul | find /I "GridPlayerWorkspace.exe" >nul
if not errorlevel 1 (
    echo 請先正常關閉已開啟的播放器，再重新啟動，以保存目前設定並載入最新版。
    pause
    exit /b 0
)
set "GRIDPLAYER_DATA_DIR=%~dp0dist\GridPlayerWorkspace\portable_data"
start "" /D "%~dp0dist\%playerRelease%" "%playerExe%" %*
exit /b 0
:missing
echo 找不到目前版本的播放器。請確認 current-release.txt 及 dist 資料夾完整。
pause
exit /b 1
