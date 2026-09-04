# Kill leftover 景明研环 app instances and their bundled opencode sidecar.
#
# The app spawns `target\debug\opencode.exe serve` as a sidecar. It survives the
# app process and keeps the binary locked, so the next `tauri dev` build fails
# with "拒绝访问" (exit 101, tauri-build PermissionDenied). Run before each launch.
#
# Only matches the app-built sidecar (target\debug\opencode.exe); the standalone
# OpenCode server on 127.0.0.1:4096 (src-tauri\binaries\opencode-*...exe) is left
# alone.
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'jingming-yanhuan.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'opencode.exe' -and $_.CommandLine -like '*target\debug\opencode.exe*'
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
