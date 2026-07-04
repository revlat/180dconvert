#!/usr/bin/env python3
"""180dconvert - Heal Force Prince 180D SCP-ECG -> EDF+ / CSV.

Wandelt die Rohaufzeichnung eines Heal Force Prince 180D (viele einzelne
.SCP-Dateien auf dem Wechseldatenträger) in Standardformate um:
  * EDF+  (eine Datei je zusammenhängender Aufnahme; öffnet z. B. in EDFbrowser)
  * CSV   (Rohwerte in mV je Ableitung)
  * PNG   (Kontroll-Plot, sofern matplotlib installiert)

Aufruf:
    python 180dconvert.py <Eingangsordner> [Ausgangsordner] [Optionen]

  <Eingangsordner>  Der Wechseldatenträger bzw. ein Ordner mit README.TXT und
                    ECG_0/ (darf direkt der Laufwerksbuchstabe sein, z. B. E:\\).
  [Ausgangsordner]  Zielordner (Standard: ./180D-Export).

Läuft unter Windows und Linux. Benötigt: numpy, edfio (matplotlib optional).

Kein Medizinprodukt - dient nur der technischen Datenaufbereitung, stellt keine
Diagnose und ersetzt keine ärztliche Befundung.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, time

import numpy as np

from healforcescpecg import HealforceSCPECG

# --- Feste Geräteparameter (verifiziert an Rohdaten, siehe docs/format-analysis.md)
SAMPLING_RATE = 150.0          # Hz
FILES_PER_FOLDER = 450         # ECG_0 = 0..449, ECG_1 = 450..899
MV_PER_UNIT = 1.0 / 100.0      # Samples in 0,01-mV-Schritten (100 = 1 mV)
LEAD_LABELS = ("I", "II", "III")


# --------------------------------------------------------------------------- #
# README / Struktur
# --------------------------------------------------------------------------- #
@dataclass
class Record:
    index: int
    first_file: int
    last_file: int

    @property
    def file_numbers(self) -> list[int]:
        return list(range(self.first_file, self.last_file + 1))


@dataclass
class DeviceInfo:
    model: str = ""
    version: str = ""
    serial: str = ""
    records: list[Record] = field(default_factory=list)


def parse_readme(readme_path: str) -> DeviceInfo:
    """Liest README.TXT (Model, SN, Record-Aufteilung)."""
    text = open(readme_path, "r", errors="replace").read()
    info = DeviceInfo()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Model:"):
            info.model = line.split(":", 1)[1].strip()
        elif line.startswith("Version:"):
            info.version = line.split(":", 1)[1].strip()
        elif line.startswith("SN:"):
            info.serial = line.split(":", 1)[1].strip()
        else:
            m = re.match(r"^(\d+)\s*:\s*(\d+)\s*-\s*(\d+)\.scp\s*$", line, re.IGNORECASE)
            if m:
                info.records.append(
                    Record(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                )
    if not info.records:
        raise ValueError(f"Keine Record-Zeilen in {readme_path} gefunden.")
    return info


def looks_like_disk(path: str) -> bool:
    return (os.path.isfile(os.path.join(path, "README.TXT"))
            and os.path.isdir(os.path.join(path, "ECG_0")))


def resolve_input(path: str) -> str | None:
    """Findet den Datenträger-Ordner, auch wenn `path` eine Ebene darüber liegt."""
    path = os.path.abspath(path)
    if looks_like_disk(path):
        return path
    # begrenzte Tiefensuche (z. B. Laufwerk enthält "Wechseldatenträger/")
    base_depth = path.rstrip(os.sep).count(os.sep)
    try:
        for root, dirs, _ in os.walk(path):
            if looks_like_disk(root):
                return root
            if root.count(os.sep) - base_depth >= 3:
                dirs[:] = []
    except (OSError, PermissionError):
        pass
    return None


def scp_path(base_dir: str, file_number: int) -> str:
    folder = file_number // FILES_PER_FOLDER
    return os.path.join(base_dir, f"ECG_{folder}", f"{file_number}.SCP")


# --------------------------------------------------------------------------- #
# Dekodieren
# --------------------------------------------------------------------------- #
def _decode_file(path: str):
    with contextlib.redirect_stdout(io.StringIO()):   # Decoder-Diagnose schlucken
        return HealforceSCPECG(path)


def _start_datetime(scp) -> datetime | None:
    pi = getattr(scp, "patient_info", {}) or {}
    sd, st = pi.get("startdate"), pi.get("starttime")
    if not sd or not st:
        return None
    try:
        return datetime(int(sd[0]), int(sd[1]), int(sd[2]),
                        int(st[0]), int(st[1]), int(st[2]))
    except (ValueError, TypeError):
        return None


@dataclass
class DecodedRecord:
    record: Record
    samples: np.ndarray            # (N, 3) int, Einheit 0,01 mV
    qrs: np.ndarray                # (N,) bool, HW-erkannter Herzschlag
    start: datetime | None
    n_files_ok: int
    n_files_failed: int
    failed_files: list[int]


def decode_record(base_dir: str, record: Record, log=print) -> DecodedRecord:
    chunks: list[np.ndarray] = []
    qrs_chunks: list[np.ndarray] = []
    start: datetime | None = None
    ok = failed = 0
    failed_files: list[int] = []
    total = len(record.file_numbers)

    for i, n in enumerate(record.file_numbers):
        path = scp_path(base_dir, n)
        if not os.path.exists(path):
            failed += 1
            failed_files.append(n)
            continue
        try:
            scp = _decode_file(path)
            s = np.asarray(scp.samples)
            if s.ndim != 2 or s.shape[1] != len(LEAD_LABELS):
                s = s.reshape(-1, len(LEAD_LABELS))
            beats = np.asarray(scp.beats)
            qrs = beats.any(axis=1) if beats.ndim == 2 else beats.astype(bool)
        except Exception:
            failed += 1
            failed_files.append(n)
            continue

        if start is None:
            start = _start_datetime(scp)
        chunks.append(s.astype(np.int32))
        qrs_chunks.append(qrs.astype(bool))
        ok += 1
        if log and (i % 100 == 0 or i == total - 1):
            log(f"    ... {i + 1}/{total} Segmente")

    if not chunks:
        raise RuntimeError(f"Aufnahme {record.index}: keine Datei dekodierbar.")
    return DecodedRecord(record, np.concatenate(chunks, axis=0),
                         np.concatenate(qrs_chunks, axis=0), start,
                         ok, failed, failed_files)


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def export_csv(dec: DecodedRecord, out_path: str) -> None:
    n = dec.samples.shape[0]
    t = np.arange(n, dtype=np.float64) / SAMPLING_RATE
    mv = dec.samples.astype(np.float64) * MV_PER_UNIT
    table = np.column_stack([t, mv, dec.qrs.astype(np.int8)])
    header = "time_s,{}_mV,{}_mV,{}_mV,qrs".format(*LEAD_LABELS)
    np.savetxt(out_path, table, delimiter=",", header=header, comments="",
               fmt=["%.4f", "%.3f", "%.3f", "%.3f", "%d"])


def export_edf(dec: DecodedRecord, out_path: str, dev: DeviceInfo) -> None:
    from edfio import Edf, EdfSignal, Patient, Recording

    signals = []
    for i, label in enumerate(LEAD_LABELS):
        sig_mv = dec.samples[:, i].astype(np.float64) * MV_PER_UNIT
        pmin, pmax = float(sig_mv.min()), float(sig_mv.max())
        if pmax <= pmin:
            pmax = pmin + 1.0
        signals.append(EdfSignal(sig_mv, sampling_frequency=SAMPLING_RATE,
                                 label=f"ECG {label}", physical_dimension="mV",
                                 physical_range=(pmin, pmax)))
    start = dec.start
    equipment = f"{dev.model}_SN{dev.serial}".strip().replace(" ", "_") or "X"
    edf = Edf(signals=signals, patient=Patient(code="X"),
              recording=Recording(startdate=start.date() if start else None,
                                   equipment_code=equipment),
              starttime=start.time() if start else None)
    edf.write(out_path)


def export_plot(dec: DecodedRecord, out_path: str, seconds: float = 10.0,
                offset_s: float = 0.0, title: str = "") -> bool:
    """EKG-Raster-Plot (10 mm/mV, 25 mm/sec). False, wenn matplotlib fehlt."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    start_i = max(0, int(offset_s * SAMPLING_RATE))
    n = min(int(seconds * SAMPLING_RATE), dec.samples.shape[0] - start_i)
    t = offset_s + np.arange(n) / SAMPLING_RATE
    mv = dec.samples[start_i:start_i + n].astype(float) * MV_PER_UNIT

    fig, axes = plt.subplots(len(LEAD_LABELS), 1, figsize=(14, 8), sharex=True)
    fig.suptitle(f"{title}\n(150 Hz, 10 mm/mV, 25 mm/sec)", fontsize=12)
    for i, (ax, label) in enumerate(zip(axes, LEAD_LABELS)):
        ax.plot(t, mv[:, i], color="black", linewidth=0.7)
        ax.set_ylabel(f"{label}\n[mV]", rotation=0, ha="right", va="center")
        ax.set_xticks(np.arange(t[0], t[-1] + 0.2, 0.2))
        ax.xaxis.set_minor_locator(plt.MultipleLocator(0.04))
        ax.yaxis.set_major_locator(plt.MultipleLocator(0.5))
        ax.yaxis.set_minor_locator(plt.MultipleLocator(0.1))
        ax.grid(which="major", color="red", alpha=0.5, linewidth=0.6)
        ax.grid(which="minor", color="red", alpha=0.2, linewidth=0.4)
        ax.tick_params(labelbottom=(i == len(LEAD_LABELS) - 1))
        ax.set_xlim(t[0], t[-1])
    axes[-1].set_xlabel("Zeit [s]")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return True


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def convert(input_dir: str, output_dir: str, formats=("edf", "csv"),
            make_plot=True, plot_at: str | None = None, log=print) -> int:
    base = resolve_input(input_dir)
    if not base:
        log(f"FEHLER: In '{input_dir}' kein Datenträger (README.TXT + ECG_0/) gefunden.")
        return 2

    dev = parse_readme(os.path.join(base, "README.TXT"))
    os.makedirs(output_dir, exist_ok=True)
    log(f"Eingabe: {base}")
    log(f"Ausgabe: {output_dir}")
    log(f"Gerät: {dev.model} (V{dev.version}, SN {dev.serial}) — "
        f"{len(dev.records)} Aufnahme(n)")

    results: list[DecodedRecord] = []
    for rec in dev.records:
        log(f"\nAufnahme {rec.index}: Dateien {rec.first_file}–{rec.last_file} "
            f"({len(rec.file_numbers)} Segmente) …")
        dec = decode_record(base, rec, log=log)
        dur_min = dec.samples.shape[0] / SAMPLING_RATE / 60.0
        log(f"  dekodiert: {dec.n_files_ok} ok, {dec.n_files_failed} fehlerhaft; "
            f"{dur_min:.1f} min; Start: {dec.start or 'unbekannt'}")
        if dec.failed_files:
            log(f"  übersprungen: {dec.failed_files}")

        stem = os.path.join(output_dir, f"record{rec.index}")
        if "edf" in formats:
            export_edf(dec, stem + ".edf", dev)
            log(f"  -> {stem}.edf")
        if "csv" in formats:
            export_csv(dec, stem + ".csv")
            log(f"  -> {stem}.csv")
        results.append(dec)

    if make_plot and results:
        dec = next((r for r in results if r.record.index == 2), results[0])
        offset_s = 0.0
        when = dec.start
        if plot_at and dec.start:
            h, m, s = (int(x) for x in plot_at.split(":"))
            target = datetime.combine(dec.start.date(), time(h, m, s))
            if target < dec.start:
                target = target.replace(day=target.day + 1)
            offset_s = max(0.0, (target - dec.start).total_seconds())
            when = target
        png = os.path.join(output_dir, f"verify_record{dec.record.index}.png")
        if export_plot(dec, png, offset_s=offset_s,
                       title=f"Heal Force Prince 180D — Aufnahme {dec.record.index} "
                             f"({when or 'Start unbekannt'})"):
            log(f"\nKontroll-Plot: {png}")
        else:
            log("\n(Kein Plot — matplotlib nicht installiert.)")

    log("\nFertig. Die EDF-Dateien lassen sich z. B. mit EDFbrowser öffnen.")
    return 0


# --------------------------------------------------------------------------- #
# Geführter Modus (ohne Tippen – für Doppelklick / Laien)
# --------------------------------------------------------------------------- #
def _auto_find_input() -> str | None:
    """Sucht den Datenträger auf Laufwerken (Windows) bzw. Mounts (Linux)."""
    import string
    roots: list[str] = []
    if os.name == "nt":
        roots += [f"{d}:\\" for d in string.ascii_uppercase]
    else:
        roots += ["/run/media", "/media", "/mnt"]
    roots.append(os.getcwd())
    for r in roots:
        if os.path.isdir(r):
            hit = resolve_input(r)
            if hit:
                return hit
    return None


def _ask_directory(title: str) -> str | None:
    """Ordner-Auswahldialog (tkinter); None wenn nicht verfügbar/abgebrochen."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askdirectory(title=title)
        root.destroy()
        return path or None
    except Exception:
        return None


def _default_output_dir() -> str:
    home = os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    return os.path.join(desktop if os.path.isdir(desktop) else home, "180D-EKG-Export")


def _pause() -> None:
    try:
        input("\nZum Schließen Enter drücken … ")
    except (EOFError, KeyboardInterrupt):
        pass


def run_interactive() -> int:
    print("=" * 60)
    print(" Heal Force Prince 180D  ->  EDF+ / CSV Konverter")
    print("=" * 60)

    base = _auto_find_input()
    if base:
        print(f"\nGefundener Datenträger: {base}")
        try:
            if input("Diesen verwenden? [J/n] ").strip().lower() in ("n", "no", "nein"):
                base = None
        except (EOFError, KeyboardInterrupt):
            pass
    if not base:
        print("\nBitte den Ordner des Datenträgers wählen (mit ECG_0 und README.TXT) …")
        picked = _ask_directory("Datenträger wählen (Ordner mit ECG_0)")
        base = resolve_input(picked) if picked else None
    if not base:
        print("\nFEHLER: Kein gültiger Datenträger gewählt.")
        _pause()
        return 2

    out = _ask_directory("Zielordner wählen (Abbrechen = Desktop)") or _default_output_dir()
    try:
        rc = convert(base, out)
    except Exception as e:  # noqa: BLE001 – Laien eine lesbare Meldung zeigen
        print(f"\nFEHLER bei der Umwandlung: {e}")
        rc = 1
    _pause()
    return rc


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:                       # kein Argument -> geführter Modus (Doppelklick)
        return run_interactive()

    p = argparse.ArgumentParser(
        prog="180dconvert",
        description="Heal Force Prince 180D SCP-ECG -> EDF+ / CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Beispiel:\n  python 180dconvert.py E:\\ C:\\Users\\me\\Desktop\\EKG\n"
               "Ohne Argumente startet ein geführter Modus mit Ordner-Auswahl.")
    p.add_argument("input", nargs="?", help="Wechseldatenträger bzw. Ordner mit ECG_0/")
    p.add_argument("output", nargs="?", default="180D-Export",
                   help="Zielordner (Standard: ./180D-Export)")
    p.add_argument("--formats", default="edf,csv", help="edf,csv (Standard: beide)")
    p.add_argument("--no-plot", action="store_true", help="Keinen Kontroll-Plot erzeugen")
    p.add_argument("--plot-at", default=None,
                   help="Uhrzeit HH:MM:SS für den Plot-Beginn (Standard: Aufnahmebeginn)")
    args = p.parse_args(argv)

    if not args.input:                 # z. B. nur Optionen übergeben
        return run_interactive()

    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    return convert(args.input, args.output, formats=formats,
                   make_plot=not args.no_plot, plot_at=args.plot_at)


if __name__ == "__main__":
    raise SystemExit(main())
