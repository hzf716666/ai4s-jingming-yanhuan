@echo off
cd /d %~dp0
start "" cmd /c "cd apps\desktop && node node_modules\vite\bin\vite.js --port 5174 --strictPort"
timeout /t 5 /nobreak >nul
pnpm --filter @ai4s/desktop tauri dev --config "E:\openscience\jingming-yanhuan\apps\desktop\src-tauri\tauri.jingming.json"