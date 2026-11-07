@echo off
cd /d "%~dp0"
set BUZON_ATENCION=adiv.puente@goexpertis.com
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe src\servicio_outlook.py --cada 15
) else (
  python src\servicio_outlook.py --cada 15
)
pause
