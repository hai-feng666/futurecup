@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ==========================================
echo  一键演示：跑一次 + 强制故障返修 + 评测
echo ==========================================
echo.
echo [1/3] 正常运行一次
python -m harness.cli run
echo.
echo [2/3] 强制注入数字漂移，演示"验证抓错 - 自动返修"
python -m harness.cli run --fault
echo.
echo [3/3] 三组基线对比评测
python -m eval.run_eval
echo.
pause
