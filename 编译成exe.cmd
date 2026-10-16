@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.14 -m venv .venv
    if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto failed
.venv\Scripts\python.exe steam_ban_manager.py --self-test
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --icon "assets\app.ico" --add-data "assets;assets" --version-file "version_info.txt" --name "PUBG账号管理系统" steam_ban_manager.py
if errorlevel 1 goto failed
echo [完成] dist\PUBG账号管理系统.exe
pause
exit /b 0
:failed
echo [错误] 构建或检查失败，请查看上方输出。
pause
exit /b 1
