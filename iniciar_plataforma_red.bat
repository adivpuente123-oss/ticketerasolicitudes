@echo off
rem Publica la plataforma en la red local (otros entran con http://TU-IP:8502). Antes: firewall y permiso de TI.
cd /d %~dp0
call .venv\Scripts\activate.bat
streamlit run app\plataforma.py --server.address 0.0.0.0 --server.port 8502 --server.headless true --theme.base light --theme.primaryColor "#ffd21f" --theme.backgroundColor "#ffffff" --theme.secondaryBackgroundColor "#f6f6f7" --theme.textColor "#1b1b1f" --theme.sidebar.backgroundColor "#ffffff" --theme.sidebar.secondaryBackgroundColor "#f6f6f7" --theme.sidebar.textColor "#1b1b1f" --theme.sidebar.primaryColor "#ffd21f"
