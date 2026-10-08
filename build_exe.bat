@echo off
REM Gera dist\PebolimArcade.exe (execute dentro da pasta do projeto)
python -m pip install -r requirements.txt
python -m PyInstaller --onefile --noconsole --name PebolimArcade main.py
echo.
echo Pronto! O executavel esta em dist\PebolimArcade.exe
pause
