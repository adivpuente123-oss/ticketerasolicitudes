@echo off
rem Abre el dashboard solo en tu computadora (http://localhost:8501)
cd /d %~dp0
call .venv\Scripts\activate.bat
streamlit run app\app.py
