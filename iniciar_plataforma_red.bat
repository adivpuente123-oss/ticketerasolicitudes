@echo off
rem Publica la plataforma en la red local (otros entran con http://TU-IP:8502). Antes: firewall y permiso de TI.
cd /d %~dp0
call .venv\Scripts\activate.bat
streamlit run app\plataforma.py --server.address 0.0.0.0 --server.port 8502 --server.headless true
