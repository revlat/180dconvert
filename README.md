# 180dconvert

Konvertiert die Langzeit-EKG-Rohdaten eines **Heal Force Prince 180D / 180D_S**
in offene Standardformate:

- **EDF+** – eine Datei je zusammenhängender Aufnahme (öffnet z. B. in
  [EDFbrowser](https://www.teuniz.net/edfbrowser/))
- **CSV** – Rohwerte in mV je Ableitung
- **PNG** – Kontroll-Plot im EKG-Raster (optional, falls `matplotlib` installiert)

Zusätzlich gibt es eine **grafische Version** (Browser-App) zum Ansehen der Kurve
und für eine technische Analyse – siehe [unten](#grafische-version-viewer--analyse--empfohlen).

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

# Grafische Version (Viewer + Analyse) — empfohlen

Am komfortabelsten ist die lokale **Web-App** (läuft im Browser, Windows & Linux).
Sie bietet:

- **EKG scrollbar ansehen** (3 Ableitungen mit QRS-Markern, Zeit-Slider, Sprung
  zu jeder Auffälligkeit)
- **Technische Analyse**: Herzfrequenz-Verlauf über die ganze Nacht,
  HRV-Kennzahlen (SDNN/RMSSD/pNN50), Statistik je Stunde und eine anspringbare
  Liste von **Auffälligkeiten** – Pausen, Brady-/Tachykardie-Phasen,
  Extrasystolen (vorzeitige Schläge), unregelmäßiger Rhythmus (Verdacht),
  geräteseitig markierte Schläge sowie Signalqualitäts-/Artefakt-Abschnitte
- **Direkt-Download** von EDF+, CSV und einem **mehrseitigen PDF-Bericht**
  (mit Grafiken: HF-Verlauf, Stunden-Statistik, Poincaré, RR-Histogramm,
  Ereignis-Zeitleiste) – direkt aus dem Browser

**Starten:**
- **Windows:** Doppelklick auf **`Start_GUI_Windows.bat`**
- **Linux/macOS:** `bash Start_GUI_Linux.sh`
- manuell: `pip install streamlit plotly numpy edfio matplotlib` und dann
  `streamlit run app.py`

Der Starter richtet beim ersten Mal automatisch eine lokale Umgebung ein und
öffnet die App im Browser. Dort den Pfad des Datenträgers eingeben (oder
„automatisch suchen") → **Laden** → Tabs *EKG ansehen / Analyse / Export*.

> ⚠️ Auch hier: technische Hinweise zur Durchsicht, **keine Diagnose**.

---

# Nur konvertieren (Schnellstart, ohne grafische Ansicht)

Wenn du **bloß die EDF/CSV-Dateien** brauchst – ganz ohne Kommandozeile. Beim
ersten Mal dauert es etwa 10 Minuten (einmalige Python-Installation), danach
genügt ein Doppelklick.

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

**1. Python sicherstellen** (meist schon vorhanden)
```bash
# openSUSE:
sudo zypper install python3
# Debian/Ubuntu:
sudo apt install python3 python3-pip
```

**2. Starten** (im Terminal)
```bash
bash Start_Linux.sh
```

## Geführter Modus (die Ordner-Abfrage)

Wird das Programm **ohne Argumente** gestartet (Starter oder `python 180dconvert.py`
im Terminal / Konsolenfenster), fragt es direkt in der Konsole nach den Ordnern:

1. Es **sucht den Datenträger automatisch**. Wird er gefunden, nur mit **Enter**
   bestätigen; sonst den **Pfad eingeben** (oder den Ordner ins Fenster ziehen –
   der Pfad wird eingefügt – dann Enter). Das darf direkt das Laufwerk sein, z. B.
   `E:\`.
2. Danach den **Zielordner** eingeben (leer lassen = Desktop-Ordner
   `180D-EKG-Export`).
3. Umwandeln, „Fertig", mit **Enter** schließen.

**So sieht die Abfrage aus** (Beispiel, Gerät wurde automatisch gefunden):

```
Gefundener Datenträger: E:\
Diesen verwenden? [J/n] (leer = ja):                     <- einfach Enter

Wohin sollen die Ergebnisse (EDF/CSV)?
  Zielordner (leer = C:\Users\Du\Desktop\180D-EKG-Export):  <- Enter oder Pfad
```

Wird das Gerät **nicht** automatisch gefunden, kommt stattdessen diese Zeile –
hier den Ordner (oder das Laufwerk) eintippen bzw. hineinziehen, dann Enter:

```
Pfad:  E:\
```

> Bewusst per Text-Eingabe statt Klick-Dialog – das funktioniert im Windows-
> Konsolenfenster wie im Linux-Terminal zuverlässig und kann nicht „hängen".

## Wenn etwas nicht klappt

- **„Python ist nicht installiert / nicht im PATH"** → Python neu installieren und
  **„Add Python to PATH"** ankreuzen.
- **Es passiert nichts / kein Fenster** → das Programm läuft **im Terminal /
  Konsolenfenster** und fragt dort per Text. Nicht per Doppelklick im Dateimanager
  starten, sondern über den Starter bzw. aus einem Terminal.
- **„Kein gültiger Datenträger"** → es muss der Ordner sein, der `README.TXT` und
  `ECG_0` enthält (oder direkt das Laufwerk des Geräts).

---

# Nutzung über die Kommandozeile

Alternative für alle, die lieber direkt mit Pfaden arbeiten oder das Tool in
Skripte einbinden möchten.

**Installation:** Python 3.10+ und die Bibliotheken. Am besten in einer lokalen
Umgebung (`venv`) – auf vielen Linux-Distributionen ist ein System-`pip install`
gesperrt (PEP 668 „externally managed"):
```bash
python3 -m venv .venv
.venv/bin/pip install numpy edfio matplotlib      # Windows: .venv\Scripts\pip install ...
```
(`matplotlib` ist optional, nur für den Kontroll-Plot.) Danach mit
`.venv/bin/python 180dconvert.py …` aufrufen. Der **Starter** (`Start_*.sh/.bat`)
erledigt genau diese Einrichtung automatisch.

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
| `app.py` | **Grafische Version** (Streamlit-Web-App: Viewer + Analyse) |
| `hf180d.py` | Kernlogik: Dekodieren, Zusammenfügen, Export, Analyse |
| `180dconvert.py` | Kommandozeilen-Konverter (nutzt `hf180d`) |
| `healforcescpecg.py` | SCP-ECG-Decoder für das Gerät (vendoriert, MIT) |
| `Start_GUI_Windows.bat` / `Start_GUI_Linux.sh` | Starter der grafischen Version |
| `Start_Windows.bat` / `Start_Linux.sh` | Starter des reinen Konverters |
| `docs/format-analysis.md` | Technische Analyse des Dateiformats |
| `LICENSE` / `NOTICE` | Lizenz (MIT) und Attribution des Decoders |
| `pyproject.toml` | Abhängigkeiten / Projekt-Metadaten |

## Credits & verwendete Bibliotheken

**Mitgeliefert (vendoriert, im Repo enthalten):**
- SCP-ECG-Wellenform-Decoder: **Kaibin Bao**,
  [KaibinBao/healforcescpecg](https://github.com/KaibinBao/healforcescpecg)
  (MIT), als `healforcescpecg.py` mit kleinem numpy≥2.0-Patch. Lizenz-Volltext in
  [`NOTICE`](NOTICE).

**Laufzeit-Abhängigkeiten** (per `pip` installiert, nicht im Repo enthalten):

| Paket | Zweck | Lizenz |
|-------|-------|--------|
| numpy | Arrays / Berechnung | BSD-3-Clause |
| edfio | EDF+-Export | Apache-2.0 |
| matplotlib | Kontroll-Plot / PDF-Bericht | Matplotlib-Lizenz (BSD-artig) |
| streamlit | Web-Oberfläche (`app.py`) | Apache-2.0 |
| plotly | interaktive Diagramme (`app.py`) | MIT |

Alle Lizenzen sind permissiv und mit der MIT-Lizenz dieses Projekts vereinbar.

## Lizenz

MIT – siehe [`LICENSE`](LICENSE). Der mitgelieferte Decoder steht ebenfalls unter
MIT (Copyright © 2019 Kaibin Bao), siehe [`NOTICE`](NOTICE).
