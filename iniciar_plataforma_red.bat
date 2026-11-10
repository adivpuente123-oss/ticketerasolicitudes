@echo off
rem Publica la plataforma en la red local (otros entran con http://TU-IP:8502). Antes: firewall y permiso de TI.
cd /d %~dp0
call .venv\Scripts\activate.bat
set PORTAL_RED=1
python servidor.py
