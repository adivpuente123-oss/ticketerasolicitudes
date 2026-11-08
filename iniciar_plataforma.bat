@echo off
rem Plataforma de solicitudes (supervisores y back office). Se abre en http://localhost:8502
rem Usa un tema claro propio; el dashboard (iniciar.bat) sigue oscuro.
cd /d %~dp0
call .venv\Scripts\activate.bat
streamlit run app\plataforma.py --server.port 8502
