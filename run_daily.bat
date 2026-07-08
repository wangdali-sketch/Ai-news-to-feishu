@echo off
set "PROJECT_DIR=D:\Ai-news-to-feishu"
set "PYTHON_EXE=C:\Users\tgf\AppData\Local\Programs\Python\Python314\python.exe"

cd /d "%PROJECT_DIR%"

if not exist "logs" mkdir "logs"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "RUN_TIME=%%i"

"%PYTHON_EXE%" main.py >> "logs\daily_%RUN_TIME%.log" 2>&1
