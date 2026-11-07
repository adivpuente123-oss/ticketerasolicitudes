@echo off
rem Publica el dashboard en la red local (otros entran con http://TU-IP:8501)
cd /d %~dp0
call .venv\Scripts\activate.bat
streamlit run app\app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
