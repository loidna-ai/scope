@echo off
REM 가상환경 자동 활성화 스크립트 (CMD용)
REM 사용법: activate.bat

cd /d "%~dp0"
call venv\Scripts\activate.bat
echo ✓ 가상환경이 활성화되었습니다.
python --version
cd /d "%~dp0"

