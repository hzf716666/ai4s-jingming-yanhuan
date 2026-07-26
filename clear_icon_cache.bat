@echo off
echo 正在清除 Windows 图标缓存...
echo.

:: 停止 Windows Explorer
taskkill /f /im explorer.exe

:: 删除图标缓存文件
del /a /q "%LocalAppData%\IconCache.db"
del /a /f /q "%LocalAppData%\Microsoft\Windows\Explorer\iconcache_*.db"

:: 重启 Windows Explorer
start explorer.exe

echo.
echo 图标缓存已清除！
echo 请重新运行 run_jingming.bat 启动应用。
pause
