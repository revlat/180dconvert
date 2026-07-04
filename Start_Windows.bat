@echo off
REM ============================================================
REM  180dconvert - Doppelklick-Starter fuer Windows
REM  Installiert bei Bedarf die noetigen Pakete und startet
REM  danach den gefuehrten Modus (Ordner-Auswahl per Dialog).
REM ============================================================
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python ist nicht installiert oder nicht im PATH.
    echo Bitte zuerst Python installieren:  https://www.python.org/downloads/
    echo WICHTIG: beim Installieren "Add Python to PATH" ankreuzen.
    echo.
    pause
    exit /b 1
)

echo Pruefe / installiere benoetigte Pakete (numpy, edfio, matplotlib) ...
python -m pip install --quiet --user --upgrade numpy edfio matplotlib

python "%~dp0180dconvert.py"
pause
