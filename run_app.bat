@echo off
chcp 65001

IF EXIST venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python "%~dp0\run_app.py" %*


if errorlevel 1 pause 