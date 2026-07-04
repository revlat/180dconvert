@echo off
REM ============================================================
REM  180dconvert - grafische Version (Viewer + Analyse) fuer Windows
REM  Legt eine lokale .venv an, installiert die Pakete und
REM  oeffnet die App im Browser.
REM ============================================================
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python ist nicht installiert oder nicht im PATH.
    echo Bitte installieren:  https://www.python.org/downloads/  ^("Add Python to PATH" ankreuzen^)
    pause
    exit /b 1
)

if not exist ".venv\" (
    echo Richte einmalig eine Python-Umgebung ein ^(.venv^) ...
    python -m venv .venv
    if errorlevel 1 ( echo FEHLER: .venv konnte nicht angelegt werden. & pause & exit /b 1 )
)

echo Pruefe / installiere Pakete ^(numpy, edfio, matplotlib, streamlit, plotly, neurokit2^) ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet numpy edfio matplotlib streamlit plotly neurokit2
if errorlevel 1 ( echo FEHLER: Pakete konnten nicht installiert werden. & pause & exit /b 1 )

REM Erststart-Abfragen (E-Mail / Telemetrie) ueberspringen
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo ==================================================================
echo   Die App startet gleich. Adresse im Browser:
echo         http://localhost:8501
echo   ^(oeffnet sich meist automatisch - sonst obige Adresse im Browser
echo    eingeben^). Zum Beenden dieses Fenster schliessen.
echo ==================================================================
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless false
pause
