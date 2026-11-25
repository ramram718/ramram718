@echo off
chcp 65001 >nul
cd /d "%~dp0"
where git >nul 2>nul && if exist .git (
  echo 최신 버전 받는 중...
  git pull --ff-only
  python -m pip install -q -r requirements.txt
)
echo.
python -m kal_award ui %*
echo.
pause
