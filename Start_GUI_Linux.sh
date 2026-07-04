#!/usr/bin/env bash
# ============================================================
#  180dconvert - grafische Version (Viewer + Analyse) fuer Linux/macOS
#  Legt eine lokale .venv an, installiert die Pakete und
#  oeffnet die App im Browser.
# ============================================================
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 ist nicht installiert. Bitte zuerst installieren."
    read -r -p "Enter zum Schliessen ... " _
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Richte einmalig eine Python-Umgebung ein (.venv) ..."
    python3 -m venv .venv || { echo "FEHLER: .venv konnte nicht angelegt werden."; \
        read -r -p "Enter ... " _; exit 1; }
fi

echo "Pruefe / installiere Pakete (numpy, edfio, matplotlib, streamlit, plotly, neurokit2) ..."
./.venv/bin/python -m pip install --quiet --upgrade pip
if ! ./.venv/bin/python -m pip install --quiet numpy edfio matplotlib streamlit plotly neurokit2; then
    echo "FEHLER: Pakete konnten nicht installiert werden (Internet vorhanden?)."
    read -r -p "Enter zum Schliessen ... " _
    exit 1
fi

# Erststart-Abfragen (E-Mail / Telemetrie) ueberspringen
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
mkdir -p "$HOME/.streamlit"
[ -f "$HOME/.streamlit/credentials.toml" ] || printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"

PORT=8501
echo
echo "=================================================================="
echo "  Die App startet gleich. Adresse im Browser:"
echo "        http://localhost:$PORT"
echo "  (oeffnet sich meist automatisch - sonst obige Adresse im Browser"
echo "   eingeben). Zum Beenden hier im Fenster Strg+C druecken."
echo "=================================================================="
echo
./.venv/bin/python -m streamlit run app.py \
    --server.port "$PORT" --server.headless false
