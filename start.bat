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
streamlit run app.py
pause
