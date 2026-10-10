@echo off
python -m pip install --upgrade pygame pyinstaller
python -m PyInstaller --onefile --noconsole --name PebolimArcade --icon assets\icon.ico --add-data "assets;assets" --collect-all pygame main.py
echo.
echo Pronto! O jogo esta em dist\PebolimArcade.exe
pause
