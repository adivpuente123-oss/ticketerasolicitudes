@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto error
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Instalacion completada. Ejecuta iniciar_plataforma.bat
pause
exit /b 0
:error
echo No se completo la instalacion. Revisa el mensaje anterior y usa Python 3.12.
pause
exit /b 1
