@echo off
chcp 65001
REM 仮想環境があればアクティベート
IF EXIST venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM アプリケーションを起動
python "%~dp0\run_app.py" %*

REM エラー時に一時停止
if errorlevel 1 pause 