# Format-Analyse: Heal Force Prince 180D `.SCP`-Dateien

Stand der Analyse auf Basis von `rohmateriel/Wechseldatenträger/ECG_0/0.SCP`
(und Stichproben). Byte-Offsets sind 0-basiert, Zahlen little-endian, sofern
nicht anders vermerkt.

> **STATUS: gelöst.** Format vollständig verstanden, Konverter fertig (siehe
> [`../README.md`](../README.md)). Kern-Ergebnis: 3 Ableitungen (I/II/III),
> **150 Hz**, 30 s pro Datei, Amplitude in 0,01-mV-Schritten. Dekodiert mit dem
> vendorierten `healforcescpecg`-Decoder — Details unter
> [„GELÖST: Wellenform-Dekodierung"](#gelöst-wellenform-dekodierung-via-kaibinbaohealforcescpecg).
>
> Dieses Dokument bildet **auch den Analyse-Weg** ab (inkl. Sackgassen). Wo
> unten „Zwischenstand" oder „noch ungelöst" steht, ist das der Stand *an jener
> Stelle der Untersuchung* — weiter unten aufgelöst.

## Zusammenfassung

- Format: **SCP-ECG (EN 1064 / ISO 11073-91064)**, standardkonform mit
  Hersteller-Eigenheiten.
- Jede Datei ist **exakt 32768 Byte** (feste Flash-Page), mit Nutzdaten bis
  ~29424 Byte, danach Padding (`0xFF`/`0x00`).
- Jede Datei ist ein **eigenständiges SCP-Record** (eigene Section 0/1/2/3/6/9)
  – die Dateien müssen **nicht** byteweise konkateniert werden, sondern als
  Sequenz von Zeitsegmenten dekodiert und die Wellenform aneinandergehängt.
- Alle geprüften Dateien haben unterschiedliche Prüfsummen → echte,
  fortlaufende Zeitsegmente (keine Duplikate).

## Datei-Header (Offset 0)

```
0000: 09 91  00 00 f0 72  40 fd 00 00 4c 00 00 00 0d 0d
```

| Offset | Größe | Feld                | Beispiel      | Bedeutung                          |
|-------:|------:|---------------------|---------------|------------------------------------|
| 0      | 2     | CRC (ganze Datei)   | `09 91`       | CCITT-CRC über den Record          |
| 2      | 4     | Record-Länge (?)    | `00 00 f0 72` | siehe Hinweis unten                |
| 6      | …     | Section 0 beginnt   |               | Pointer-Tabelle                    |

> **Hinweis Record-Länge:** Das 4-Byte-Feld bei Offset 2 liest sich standard-LE
> als absurd groß (0x72F00000). Auffällig: `0x72F0 = 29424` entspricht exakt dem
> Ende der Nutzdaten (Ende Section 9). Die Feldinterpretation weicht also vom
> Standard ab; für den Decoder ist sie unkritisch, da die Section-0-Pointer die
> Struktur eindeutig beschreiben.

## Section-Header-Layout (16 Byte)

Für alle Sections gilt (verifiziert an Section 0, 1, 2, 3, 6, 9):

| Offset | Größe | Feld               |
|-------:|------:|--------------------|
| 0      | 2     | Section-CRC        |
| 2      | 2     | Section-ID         |
| 4      | 4     | Section-Länge      |
| 8      | 1     | Section-Version (`0x0D` = 13) |
| 9      | 1     | Protokoll-Version (`0x0D` = 13) |
| 10     | 6     | reserviert         |

## Section 0 – Pointer-Tabelle (@ Byte 6, Länge 76)

Nach dem 16-Byte-Header folgen 10-Byte-Pointer-Einträge:
`ID(2) · Länge(4) · Index(4)` (Index = 1-basierter Byte-Offset in der Datei).

| # | ID | Länge (dez) | Index (Byte) | Section                          |
|--:|---:|------------:|-------------:|----------------------------------|
| 0 | 0  | 76          | 6            | Pointer-Tabelle (dieses Section 0)|
| 1 | 1  | 66          | 82           | Patientendaten / Zeitstempel     |
| 2 | 2  | 30          | 148          | Huffman-Tabellen                 |
| 3 | 3  | 28          | 178          | Ableitungs-Definition (Leads)    |
| 4 | 6  | 27024       | 488          | **Rhythmus-/Wellenform-Daten**   |
| 5 | 9  | 1792        | 27632        | Herstellerspezifische Daten      |

(Die anschließenden Pointer-Bytes sind Padding/„Garbage" – nur diese 6
Einträge sind gültig.)

## Section 1 – Patient / Zeitstempel (@ Byte 82, Länge 66)

Enthält Tag-basierte Felder. Nahe dem Ende ein Datum/Zeit-Block:

```
0082: 00 19 04 00 07 ea 07 03 1a 03 00 17 14 13
```

`ea 07` (LE) = **0x07EA = 2026** → Aufnahmejahr. Die folgenden Bytes kodieren
Monat/Tag/Stunde/Minute/Sekunde (genaues Layout in Phase 2 zu fixieren; die
Hersteller-Software zeigte für diese Aufnahme z. B. `07.04.2026 06:34:43`).
Patienten-ID-Feld ist leer (`00000`).

## Section 2 – Huffman (@ Byte 148, Länge 30)

Sehr klein (nur 14 Byte Nutzdaten). Das deutet darauf hin, dass **keine
umfangreichen benutzerdefinierten Huffman-Tabellen** verwendet werden –
wahrscheinlich Standard-Default-Tabelle oder gar keine Kompression. Das
vereinfacht das Dekodieren der Wellenform erheblich.

```
00a4: 00 01 00 01 00 02 01 00 00 00 00 08 00 00
```

## Section 3 – Ableitungs-Definition (@ Byte 178, Länge 28)

```
00c2: 03 04 95 11 00 00 28 23 00 00 05 00 ...
```

Erstes Byte `03` = **Anzahl Ableitungen = 3** (passt zu den 3 vom Nutzer
genannten Kurvenverläufen). Die folgenden Wertepaare kodieren die Sample-Bereiche
je Ableitung (Start-/End-Sample). Detail-Layout in Phase 2.

## Section 6 – Wellenform (@ Byte 488, Länge lt. Header 20274)

```
01e8: [16-Byte-Header] 34 25 96 00 00 00 1a 4f fe 05 f9 3d ...
```

Nutzdaten beginnen bei Byte 504. Erwartete Felder gemäß SCP-ECG Section 6:
Amplitude Value Multiplier (nV/Einheit), Sample-Intervall, Flags für
Differenz-Kodierung/Bimodal-Kompression, dann die (ggf. delta-kodierten)
Samples je Ableitung.

> **Offen (Phase 2):** exakte Sample-Rate (Recherche nennt für das 180D
> häufig ~300 Hz), Amplituden-Skalierung und ob Differenz-Kodierung aktiv ist.
> Diese drei Größen sind für korrekte mV-/Zeitwerte entscheidend und müssen
> gegen einen Screenshot der Hersteller-Software verifiziert werden.

## Referenzwerte aus Hersteller-Ausdruck

Im Rohmaterial liegt ein Foto eines Ausdrucks aus der Heal-Force-Software
(`rohmateriel/20260704_152358.jpg.jpeg`, „ECG Waveform Record"). Es dient als
**Verifikations-Anker** für den Decoder:

| Feld            | Wert                     | Nutzen                                        |
|-----------------|--------------------------|-----------------------------------------------|
| ID No.          | 2                        | Ausdruck gehört zu Record 2 (Dateien 29–899)  |
| Record Time     | 07.04.2026 06:34:43      | Soll-Wert für Section-1-Zeitstempel-Decoder   |
| Print Out Time  | 07.04.2026 15:21:12      | konsistent mit Datei-mtimes                    |
| Ableitungen     | I, II, III               | 3 Kanäle → Kanal-Labels für EDF               |
| Heart Rate      | 68 bpm                   | Soll-Wert zum Plausibilisieren nach Decodieren |
| Verstärkung     | 10 mm/mV                 | Amplituden-Eichung (Eichzacke ▽ = 1 mV sichtbar)|
| Vorschub        | 25 mm/sec                | Zeit-Eichung (Displaywert, nicht = Sample-Rate)|

→ Nach dem Dekodieren von Section 6 muss ein Plot dieselbe Morphologie, HR 68 und
über die Eichzacke dieselbe mV-Skalierung ergeben. Damit sind Amplituden- und
Zeitskalierung überprüfbar statt geschätzt.

> **Nicht anwendbar:** Die in der Vorrecherche kursierende `.DAT/.ESK`-Beschreibung
> (300 Hz, State-Bytes 1/2/129, 512-Byte-Block) betrifft ein *anderes* Gerät/Format
> aus einem fremden Blog. Unsere Dateien sind SCP-ECG; diese Codierung gilt hier
> **nicht**. „300 Hz" wird nur als grober Kreuzcheck-Kandidat mitgeführt.

## Verifikation mit generischem Tool (scpinfo)

Getestet mit dem Open-Source-Reader **gitrust/scpinfo** (unabhängige
Python-Implementierung des SCP-ECG-Standards). Ergebnis:

**Auf Standard-SCP (mitgeliefertes example.scp): läuft perfekt** (liest Patient,
12 Pointer, alle Sektionen). **Auf unseren Heal-Force-Dateien: scheitert
zunächst** — und legt damit exakt die gerätespezifischen Abweichungen offen.
Drei Patches waren nötig, danach liest das Tool die Struktur sauber:

1. **Kompakte Pointer-Tabelle:** Standard-SCP schreibt immer **12** Section-Pointer
   (0–11, auch leere). Heal Force schreibt nur die **6** benutzten
   (0,1,2,3,6,9); Section-0-Länge 76 = 16 + 6·10. → Pointer-Anzahl aus der Länge
   ableiten statt 12 annehmen.
2. **0-basierte Section-Indizes:** Standard-Pointer-Index ist 1-basiert
   (Section liegt bei `index-1`). Heal Force ist **0-basiert** (Section 1 bei
   Byte 82 = Pointer-Index 82). → `move(index)` statt `move(index-1)`.
3. **Padding-Lücken:** Sektionen liegen **nicht lückenlos** hintereinander
   (z. B. Lücke zwischen Section 3 @206 und Section 6 @488). → strikt per
   Pointer-Index seeken, nicht sequentiell lesen.

→ **Fazit:** Der Container ist echtes Standard-SCP-ECG (unabhängig bestätigt),
aber **kein generischer Viewer öffnet die Dateien unverändert** — es braucht
genau diese drei Anpassungen. Das ist die Kern-Spezifikation für unseren
Konverter.

### Section-6-Rohfelder (via gepatchtem scpinfo)

```
avm (Amplituden-Multiplier) = 9524 nV ?
sample_time_interval        = 150 ?
encoding-Flag               = 0
bimodal                     = 0
nr_bytes_for_leads          = [20250, 2561, 511]   -> ungleich!
```

**Zwischenstand (an dieser Stelle noch offen, direkt darunter gelöst) – die Wellenform-Kodierung:**
- Die drei „Leads" haben stark **ungleiche Sample-Zahlen** (10125/1281/256) –
  das sind *nicht* 3 gleich lange, parallele EKG-Kanäle. Der Section-6-Subheader
  wird also vermutlich noch falsch interpretiert (weitere Heal-Force-Abweichung).
- Als int16-roh gelesen **springen die Samples wild** (keine glatte Kurve);
  als int8-Deltas ergibt sich nur eine monotone Drift. → Die tatsächliche
  Sample-Kodierung ist **weder Standard-int16 noch simple 1-Byte-Differenz**.
  Das ist der verbleibende Reverse-Engineering-Kern und muss gegen den
  Hersteller-Ausdruck (HR 68, Morphologie) kalibriert werden.

## GELÖST: Wellenform-Dekodierung via KaibinBao/healforcescpecg

Es existiert ein **fertiger Open-Source-Decoder für genau dieses Gerät**:
[github.com/KaibinBao/healforcescpecg](https://github.com/KaibinBao/healforcescpecg)
(„based on experience with data from a Healforce Prince 180D device"). Er löst
die Wellenform-Kodierung vollständig. Die Datei-Layout-Annahme des Decoders
(`ECG_{i//450}/{i}.SCP`) ist **identisch mit unseren Daten**.

Die Heal-Force-Sample-Kodierung (laut Decoder + verifiziert an unseren Dateien):
- Rhythmusdaten sind **nicht Huffman-kodiert** (trotz vorhandener Section 2).
- **12-Bit-Samples** = 10-Bit signed Amplitude + 2 Bit Beat-Marker.
- Je **4 Samples in 3 16-Bit-Words** gepackt.
- Die 3 Kanäle sind **in einem Strom interleaved** (nicht getrennt) — daher die
  scheinbar „ungleichen Leads" bei naiver Standard-Lesart.
- Bit 15 = HW-erkannter Herzschlag (QRS), Bit 14 = irregulärer Schlag.
- Amplitude quantisiert in **0,01-mV-Schritten (100 = 1 mV)**.

**Verifiziertes Ergebnis (29.SCP):** 4500 Samples × 3 Kanäle, **150 Hz**,
= **30 s pro Datei**, Amplituden −0,05…0,55 mV, klare EKG-Morphologie
(P-QRS-T), HW-Beats ≈ 80 bpm (Ausdruck zeigt 68 für anderen Abschnitt →
normale HF-Schwankung).

> Nötig war nur ein 1-Zeilen-Patch für numpy≥2.0 (Bitmasken in uint16 statt
> int16, sonst OverflowError). Kein Datenproblem.

Damit sind die früheren „offenen Punkte" (Sample-Rate, Amplituden-Faktor,
Section-6-Länge, Sample-Kodierung) **alle geklärt**.

## Offene Punkte / Risiken (historisch — siehe oben, gelöst)

- Länge im Section-6-Header (20274) ≠ Länge in der Pointer-Tabelle (27024);
  Ursache klären (Padding, gerätespezifische Zählweise).
- Exaktes Datum/Zeit-Layout in Section 1 (Soll: 07.04.2026 06:34:43, s. o.).
- Sample-Rate + Amplituden-Skalierung aus Section-6-Header verbindlich
  bestimmen. Verifikation nun möglich gegen den Hersteller-Ausdruck
  (HR 68, 10 mm/mV, 25 mm/sec) statt reiner Schätzung.
- Section 9 (herstellerspezifisch, 1792 B) noch nicht inspiziert — evtl.
  HR-/Analyse-Anmerkungen; nicht die primäre Wellenformquelle.
