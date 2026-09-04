@echo off
REM =====================================================================
REM  Jingming Yanhuan - one-time server setup (run on the cloud server)
REM  What it does:
REM    1. Locate the installed app exe (or take it as %1)
REM    2. Write gateway.txt (enabled=1, lan=1, mode, random token)
REM    3. Open the Windows firewall for TCP 4098
REM    4. Register autostart (Startup folder, after you enable logon)
REM    5. Print the LAN URL with the token link
REM  Usage:  setup_server.bat [path\to\yanhuan.exe] [full|read-only]
REM =====================================================================
setlocal EnableExtensions

set "MODE=full"
if not "%~2"=="" set "MODE=%~2"
if not "%MODE%"=="full" if not "%MODE%"=="read-only" set "MODE=full"

set "APP_EXE=%~1"
if "%APP_EXE%"=="" (
    for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-ChildItem -Path $env:ProgramFiles,$env:LOCALAPPDATA -Filter *.exe -Recurse -ErrorAction SilentlyContinue ^| Where-Object { $_.Name -match 'yanhuan' } ^| Select-Object -First 1 -ExpandProperty FullName"') do set "APP_EXE=%%i"
)
if "%APP_EXE%"=="" (
    echo [ERR] App exe not found under %%PROGRAMFILES%% / %%LOCALAPPDATA%%.
    echo       Pass the path: setup_server.bat "C:\Program Files\JingmingYanhuan\JingmingYanhuan.exe" full
    exit /b 1
)
echo [OK] App exe : %APP_EXE%

set "RUNTIME_DIR=%APPDATA%\com.jingming.yanhuan\runtime"
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

for /f "delims=" %%t in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"') do set "TOKEN=%%t"
if "%TOKEN%"=="" set "TOKEN=%RANDOM%%RANDOM%%RANDOM%%RANDOM%"

> "%RUNTIME_DIR%\gateway.txt" (
    echo enabled=1
    echo lan=1
    echo mode=%MODE%
    echo token=%TOKEN%
)
echo [OK] gateway.txt written (mode=%MODE%)

netsh advfirewall firewall show rule name="JMYH Gateway 4098" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="JMYH Gateway 4098" dir=in action=allow protocol=TCP localport=4098 >nul
    echo [OK] firewall rule added for TCP 4098
) else (
    echo [OK] firewall rule already present
)

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%STARTUP_DIR%\JMYH Server.lnk" (
    echo.
)
del "%STARTUP_DIR%\JMYH Server.lnk" /q >nul 2>&1
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP_DIR%\JMYH Server.lnk'); $s.TargetPath = '%APP_EXE%'; $s.WorkingDirectory = (Split-Path '%APP_EXE%'); $s.Save()" >nul
echo [OK] autostart shortcut added (logs in as this user)

for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } ^| Sort-Object InterfaceMetric -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty IPAddress)"') do set "IP=%%i"
if "%IP%"=="" set "IP=YOUR\_SERVER\_IP"

echo.
echo =====================================================================
echo  Done. Next steps:
echo   1. Start the app now : %APP_EXE%
echo   2. Open the app - Settings - Remote Access - verify enabled / LAN
echo   3. LAN URL          : http://%IP%:4098/#token=%TOKEN%
echo   4. Public URL       : add a firewall/SG rule for 4098, or run:
echo        cloudflared tunnel --url http://localhost:4098
echo   Token (store this securely - it is the server key):
echo      %TOKEN%
echo =====================================================================
endlocal
