@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ==========================================
echo  数诊编排 DataDx  ·  可视化控制台
echo ==========================================
echo.
python --version || (echo [错误] 没找到 python，请先安装 Python 3.10+ && pause && exit /b 1)
echo.
echo 正在启动 http://127.0.0.1:8080 ...
echo 关闭本窗口即停止服务。
echo.
python -m harness.console --port 8080
pause
