@echo off
REM ============================================================
REM  180dconvert - Doppelklick-Starter fuer Windows
REM  Legt einmalig eine lokale Python-Umgebung (.venv) an,
REM  installiert die noetigen Pakete dort hinein und startet
REM  danach den gefuehrten Modus (Abfrage im Fenster).
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

REM Einmalig: lokale Umgebung anlegen
if not exist ".venv\" (
    echo Richte einmalig eine Python-Umgebung ein ^(.venv^) ...
    python -m venv .venv
    if errorlevel 1 (
        echo FEHLER: Konnte .venv nicht anlegen.
        pause
        exit /b 1
    )
)

echo Pruefe / installiere benoetigte Pakete ^(numpy, edfio, matplotlib^) ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet numpy edfio matplotlib
if errorlevel 1 (
    echo FEHLER: Pakete konnten nicht installiert werden ^(Internet vorhanden?^).
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "%~dp0180dconvert.py"
pause
