@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 请先按照 README.md 创建 .venv 并安装依赖。
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto failed
.venv\Scripts\python.exe steam_ban_manager.py --self-test
if errorlevel 1 goto failed
echo [完成] 检查通过。
pause
exit /b 0
:failed
echo [错误] 检查未通过。
pause
exit /b 1
