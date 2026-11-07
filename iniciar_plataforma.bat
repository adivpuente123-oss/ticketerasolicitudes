@echo off
rem Plataforma de solicitudes (supervisores y back office). Se abre en http://localhost:8502
rem Usa un tema claro propio; el dashboard (iniciar.bat) sigue oscuro.
cd /d %~dp0
call .venv\Scripts\activate.bat
streamlit run app\plataforma.py --server.port 8502 --theme.base light --theme.primaryColor "#ffd21f" --theme.backgroundColor "#ffffff" --theme.secondaryBackgroundColor "#f6f6f7" --theme.textColor "#1b1b1f" --theme.sidebar.backgroundColor "#ffffff" --theme.sidebar.secondaryBackgroundColor "#f6f6f7" --theme.sidebar.textColor "#1b1b1f" --theme.sidebar.primaryColor "#ffd21f"
