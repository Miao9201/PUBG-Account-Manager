@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo [错误] 请先按照 README.md 创建 .venv 并安装 requirements.txt。
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0steam_ban_manager.py"
