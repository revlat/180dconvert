# 180dconvert

Konvertiert die Langzeit-EKG-Rohdaten eines **Heal Force Prince 180D / 180D_S**
in offene Standardformate:

- **EDF+** – eine Datei je zusammenhängender Aufnahme (öffnet z. B. in
  [EDFbrowser](https://www.teuniz.net/edfbrowser/))
- **CSV** – Rohwerte in mV je Ableitung
- **PNG** – Kontroll-Plot im EKG-Raster (optional, falls `matplotlib` installiert)

Läuft unter **Windows und Linux**. Reines Python – nichts muss als Paket
installiert werden, nur ein paar Bibliotheken (siehe unten).

> ⚠️ **Kein Medizinprodukt.** Dient nur der technischen Datenaufbereitung, stellt
> **keine Diagnose** und ersetzt weder das Gerät noch eine ärztliche Befundung.

## Hintergrund

Das Gerät speichert eine Aufzeichnung als viele einzelne `.SCP`-Dateien
(je 30 s, 3 Ableitungen I/II/III, 150 Hz). Das Format ist SCP-ECG-basiert, weicht
aber vom Standard EN 1064 ab (u. a. 10-Bit-Samples, interleaved Kanäle) – deshalb
öffnen es Standard-Viewer nicht direkt. Details:
[`docs/format-analysis.md`](docs/format-analysis.md).

---

# Schnellstart (per Doppelklick)

Der bequemste Weg – ganz ohne Kommandozeile. Beim ersten Mal dauert es etwa
10 Minuten, weil Python einmalig installiert werden muss; danach genügt ein
Doppelklick.

## Windows

**1. Python einmalig installieren**
1. <https://www.python.org/downloads/> öffnen, **Download Python** klicken.
2. Installer starten. **Wichtig:** unten **„Add Python to PATH"** ankreuzen,
   dann **Install Now**.

**2. Gerät anstecken**
- EKG-Gerät per USB anschließen. Es erscheint als **Wechseldatenträger**
  (ein neues Laufwerk, z. B. `E:` mit den Ordnern `ECG_0`, `ECG_1`).

**3. Programm starten**
- Doppelklick auf **`Start_Windows.bat`** (in diesem Ordner).
  Beim ersten Mal lädt es kurz die benötigten Pakete nach (Internet nötig).
- Dann fragt das Programm nach den Ordnern (siehe *Geführter Modus* unten).

**4. Ergebnisse ansehen**
- Im Zielordner liegen `record1.edf`, `record2.edf` (die Aufnahmen), CSV-Dateien
  und ein Kontroll-Bild. Die `.edf` öffnest du mit **EDFbrowser** (kostenlos):
  <https://www.teuniz.net/edfbrowser/>.

## Linux / macOS

**1. Python + Tk sicherstellen** (meist schon vorhanden)
```bash
# openSUSE:
sudo zypper install python3 python3-tk
# Debian/Ubuntu:
sudo apt install python3 python3-pip python3-tk
```

**2. Starten**
```bash
bash Start_Linux.sh
```

## Geführter Modus (die Ordner-Abfrage)

Wird das Programm **ohne Argumente** gestartet (Doppelklick / Starter), fragt es
selbst nach den Ordnern:

1. Es **sucht den Datenträger automatisch**. Wird er gefunden, nur mit **Enter**
   bestätigen; sonst öffnet sich ein **Ordner-Auswahlfenster** zum Anklicken.
2. Danach ein **zweites Fenster** für den Zielordner (Abbrechen = Ergebnisse auf
   dem Desktop unter `180D-EKG-Export`).
3. Umwandeln, „Fertig", mit **Enter** schließen.

> Die Auswahlfenster brauchen `tkinter`. Unter Windows ist es bei Python dabei,
> unter Linux ggf. `python3-tk` nachinstallieren.

## Wenn etwas nicht klappt

- **„Python ist nicht installiert / nicht im PATH"** → Python neu installieren und
  **„Add Python to PATH"** ankreuzen.
- **Kein Auswahlfenster (Linux)** → `python3-tk` installieren – oder die Pfade
  direkt angeben (siehe *Nutzung über die Kommandozeile*).
- **„Kein gültiger Datenträger"** → es muss der Ordner sein, der `README.TXT` und
  `ECG_0` enthält (oder direkt das Laufwerk des Geräts).

---

# Nutzung über die Kommandozeile

Alternative für alle, die lieber direkt mit Pfaden arbeiten oder das Tool in
Skripte einbinden möchten.

**Installation:** Python 3.10+ und die Bibliotheken:
```bash
pip install numpy edfio matplotlib
```
(`matplotlib` ist optional, nur für den Kontroll-Plot.)

**Aufruf:**
```bash
python 180dconvert.py <Eingangsordner> [Ausgangsordner]
```
- **`<Eingangsordner>`** – Wechseldatenträger bzw. Ordner mit `README.TXT` und
  `ECG_0/`. Darf direkt der Laufwerksbuchstabe sein.
- **`[Ausgangsordner]`** – optional, Standard `./180D-Export`.

**Beispiele:**
```bash
# Windows – Gerät auf Laufwerk E:
python 180dconvert.py E:\ C:\Users\me\Desktop\EKG
# Linux – gemounteter Datenträger
python 180dconvert.py /run/media/me/PRINCE180D
```

**Optionen:** `--formats edf,csv`, `--no-plot`,
`--plot-at HH:MM:SS` (Plot-Beginn auf eine bestimmte Uhrzeit legen, z. B. für den
Vergleich mit einem Geräte-Ausdruck).

**Ausgabe** im Zielordner: `record1.edf`, `record2.edf`, `record1.csv`,
`record2.csv`, `verify_record2.png`.

---

## Projektdateien

| Datei | Zweck |
|-------|-------|
| `180dconvert.py` | Das Hauptprogramm (Dekodieren, Zusammenfügen, Export) |
| `healforcescpecg.py` | SCP-ECG-Decoder für das Gerät (vendoriert, MIT) |
| `Start_Windows.bat` / `Start_Linux.sh` | Doppelklick-Starter (Pakete + Start) |
| `docs/format-analysis.md` | Technische Analyse des Dateiformats |
| `LICENSE` / `NOTICE` | Lizenz (MIT) und Attribution des Decoders |
| `pyproject.toml` | Abhängigkeiten / Projekt-Metadaten |

## Credits

- SCP-ECG-Wellenform-Decoder: **Kaibin Bao**,
  [KaibinBao/healforcescpecg](https://github.com/KaibinBao/healforcescpecg)
  (MIT), hier als `healforcescpecg.py` mit kleinem numpy≥2.0-Patch. Siehe
  [`NOTICE`](NOTICE).

## Lizenz

MIT – siehe [`LICENSE`](LICENSE). Der mitgelieferte Decoder steht ebenfalls unter
MIT (Copyright © 2019 Kaibin Bao), siehe [`NOTICE`](NOTICE).
