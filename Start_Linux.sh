#!/usr/bin/env bash
# ============================================================
#  180dconvert - Starter fuer Linux/macOS
#  Installiert bei Bedarf die noetigen Pakete und startet
#  danach den gefuehrten Modus (Ordner-Auswahl per Dialog).
# ============================================================
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 ist nicht installiert. Bitte zuerst installieren."
    echo "  z. B.:  sudo zypper install python3   (openSUSE)"
    echo "          sudo apt install python3 python3-pip python3-tk   (Debian/Ubuntu)"
    read -r -p "Enter zum Schliessen ... " _
    exit 1
fi

echo "Pruefe / installiere benoetigte Pakete (numpy, edfio, matplotlib) ..."
python3 -m pip install --quiet --user --upgrade numpy edfio matplotlib 2>/dev/null

python3 ./180dconvert.py "$@"
