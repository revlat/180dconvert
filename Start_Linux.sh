#!/usr/bin/env bash
# ============================================================
#  180dconvert - Starter fuer Linux/macOS
#  Legt einmalig eine lokale Python-Umgebung (.venv) an,
#  installiert die noetigen Pakete dort hinein (umgeht die
#  PEP-668-Sperre "externally managed") und startet dann
#  den gefuehrten Modus.
# ============================================================
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 ist nicht installiert. Bitte zuerst installieren:"
    echo "  openSUSE:       sudo zypper install python3"
    echo "  Debian/Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    read -r -p "Enter zum Schliessen ... " _
    exit 1
fi

# Einmalig: lokale Umgebung anlegen
if [ ! -d ".venv" ]; then
    echo "Richte einmalig eine Python-Umgebung ein (.venv) ..."
    if ! python3 -m venv .venv; then
        echo "FEHLER: Konnte .venv nicht anlegen."
        echo "  Debian/Ubuntu: 'sudo apt install python3-venv' und erneut starten."
        read -r -p "Enter zum Schliessen ... " _
        exit 1
    fi
fi

echo "Pruefe / installiere benoetigte Pakete (numpy, edfio, matplotlib) ..."
./.venv/bin/python -m pip install --quiet --upgrade pip
if ! ./.venv/bin/python -m pip install --quiet numpy edfio matplotlib; then
    echo "FEHLER: Pakete konnten nicht installiert werden (Internet vorhanden?)."
    read -r -p "Enter zum Schliessen ... " _
    exit 1
fi

./.venv/bin/python ./180dconvert.py "$@"
