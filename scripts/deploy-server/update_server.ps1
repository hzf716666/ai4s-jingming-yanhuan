# Jingming Yanhuan 服务器更新脚本 (在服务器上通过"执行命令"以 PowerShell 运行)
# 用法: powershell -ExecutionPolicy Bypass -File C:\update_server.ps1
# 前提: C:\yanhuan-server.zip 已放好(新版包), WebView2 已安装
# 行为: 杀旧进程 -> 备份 -> 解压新版 -> 启动应用 -> 自检 4098

$ErrorActionPreference = "Continue"

Write-Host "== 1/5 停止旧进程 =="
Get-Process -Name "jingming-yanhuan" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Write-Host "== 2/5 备份旧版本 =="
if (Test-Path "C:\yanhuan") {
    Remove-Item "C:\yanhuan-backup" -Recurse -Force -ErrorAction SilentlyContinue
    Move-Item "C:\yanhuan" "C:\yanhuan-backup"
}

Write-Host "== 3/5 解压新版 =="
Expand-Archive -Path "C:\yanhuan-server.zip" -DestinationPath "C:\yanhuan" -Force
if (-not (Test-Path "C:\yanhuan\jingming-yanhuan.exe")) {
    Write-Host "!! 新包缺少 jingming-yanhuan.exe, 中止"
    exit 1
}

Write-Host "== 4/5 恢复网关配置(链接/token不变) =="
# gateway.txt 在 %APPDATA%\com.jingming.yanhuan\runtime, 与程序目录无关, 无需处理
$gw = "$env:APPDATA\com.jingming.yanhuan\runtime\gateway.txt"
if (Test-Path $gw) { Write-Host "gateway.txt 保持: " (Get-Content $gw -Raw | Select-String "token").Line }

Write-Host "== 5/5 尝试启动应用(需桌面会话; 若在计划任务/桌面双击则自动) =="
# 通过计划任务启动, 绑定真实桌面会话 (onlogon 触发)
schtasks /Delete /TN "JMYH" /F 2>$null | Out-Null
schtasks /Create /TN "JMYH" /TR "C:\yanhuan\jingming-yanhuan.exe" /SC ONLOGON /RL HIGHEST /F | Out-Null
Write-Host "计划任务 JMYH 已注册(用户登录桌面时自动启动)"

Write-Host "== 自检: 4098 =="
Start-Sleep -Seconds 5
if (Test-NetConnection -ComputerName 127.0.0.1 -Port 4098 -InformationLevel Quiet) {
    Write-Host "SUCCESS: 4098 已在监听, 网址无需改变"
} else {
    Write-Host "INFO: 4098 未监听(可能启动中或需桌面会话); 请在桌面双击 jingming 或重启后自动启动"
}

Write-Host "完成。若需回滚: 把 C:\yanhuan-backup 还原为 C:\yanhuan 再启动即可"
