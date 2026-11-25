@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] Python 패키지 설치...
python -m pip install -r requirements.txt || goto :fail
echo [2/2] 브라우저 설치...
python -m playwright install chromium || goto :fail
echo.
echo 설치 완료. 이제 run.bat 을 더블클릭하세요.
pause
exit /b 0
:fail
echo.
echo !! 설치 실패. Python이 설치되어 있는지 확인하세요 (python.org, "Add python.exe to PATH" 체크).
pause
exit /b 1
