@echo off
title NiftyScout
cd /d "%~dp0"
call venv\Scripts\activate 2>nul || (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
)
echo.
echo  ============================================
echo    NiftyScout - Starting...
echo    Dashboard: http://localhost:8501
echo  ============================================
echo.

REM Start Ollama in the background (silent, ignored if already running)
start "" /B ollama serve >nul 2>&1
timeout /t 2 /nobreak >nul

streamlit run app.py
pause
