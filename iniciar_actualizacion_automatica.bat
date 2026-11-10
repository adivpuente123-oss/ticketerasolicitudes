@echo off
cd /d "%~dp0"
if not exist .git (
  echo Esta opcion necesita una copia instalada con git clone.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Ejecuta instalar.bat primero.
  pause
  exit /b 1
)
echo Abre una sola vez http://localhost:8502 y conserva esa pestana.
.venv\Scripts\python.exe src\actualizador.py
pause
