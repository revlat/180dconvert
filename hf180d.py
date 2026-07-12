"""hf180d – Kernlogik für den Heal Force Prince 180D Konverter/Viewer.

Enthält: SCP-Dekodierung + Zusammenfügen (decode_record), Export (EDF+/CSV/Plot)
und technische Analyse (Herzfrequenz, HRV, Ereignisse). Wird sowohl von der CLI
(180dconvert.py) als auch von der Web-App (app.py) genutzt.

Kein Medizinprodukt – die Analyse liefert technische Hinweise zur Durchsicht,
keine Diagnose.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from healforcescpecg import HealforceSCPECG

# NeuroKit2 (optional): erweiterte Analyse. Nur Verfügbarkeit prüfen (kein Import,
# der wäre langsam) – tatsächlich importiert wird erst bei Bedarf.
HAS_NEUROKIT = importlib.util.find_spec("neurokit2") is not None

# --- Feste Geräteparameter (verifiziert, siehe docs/format-analysis.md)
SAMPLING_RATE = 150.0
FILES_PER_FOLDER = 450
MV_PER_UNIT = 1.0 / 100.0        # 100 Einheiten = 1 mV
LEAD_LABELS = ("I", "II", "III")


# --------------------------------------------------------------------------- #
# Struktur / README
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
                    Record(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if not info.records:
        raise ValueError(f"Keine Record-Zeilen in {readme_path} gefunden.")
    return info


def looks_like_disk(path: str) -> bool:
    return (os.path.isfile(os.path.join(path, "README.TXT"))
            and os.path.isdir(os.path.join(path, "ECG_0")))


def resolve_input(path: str) -> str | None:
    if not path:
        return None
    path = os.path.abspath(path)
    if looks_like_disk(path):
        return path
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
    return os.path.join(base_dir, f"ECG_{file_number // FILES_PER_FOLDER}",
                        f"{file_number}.SCP")


# --------------------------------------------------------------------------- #
# Dekodieren
# --------------------------------------------------------------------------- #
def _decode_file(path: str):
    with contextlib.redirect_stdout(io.StringIO()):
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
    qrs: np.ndarray                # (N,) bool – HW-erkannter Herzschlag
    irregular: np.ndarray          # (N,) bool – HW-markierter unregelmäßiger Schlag
    start: datetime | None
    n_files_ok: int
    n_files_failed: int
    failed_files: list[int]

    @property
    def n_samples(self) -> int:
        return self.samples.shape[0]

    @property
    def duration_s(self) -> float:
        return self.n_samples / SAMPLING_RATE

    def mv(self, lead: int, i0: int = 0, i1: int | None = None) -> np.ndarray:
        return self.samples[i0:i1, lead].astype(float) * MV_PER_UNIT


def decode_record(base_dir: str, record: Record, progress=None) -> DecodedRecord:
    chunks, qrs_chunks, irr_chunks = [], [], []
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
            marked = np.asarray(getattr(scp, "marked_beats", np.zeros_like(beats)))
            irr = marked.any(axis=1) if marked.ndim == 2 else marked.astype(bool)
            if len(irr) != len(qrs):
                irr = np.zeros(len(qrs), dtype=bool)
        except Exception:
            failed += 1
            failed_files.append(n)
            continue

        if start is None:
            start = _start_datetime(scp)
        chunks.append(s.astype(np.int32))
        qrs_chunks.append(qrs.astype(bool))
        irr_chunks.append(irr.astype(bool))
        ok += 1
        if progress:
            progress(i + 1, total)

    if not chunks:
        raise RuntimeError(f"Aufnahme {record.index}: keine Datei dekodierbar.")
    return DecodedRecord(record, np.concatenate(chunks), np.concatenate(qrs_chunks),
                         np.concatenate(irr_chunks), start, ok, failed, failed_files)


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def export_csv(dec: DecodedRecord, out_path: str) -> None:
    n = dec.n_samples
    t = np.arange(n, dtype=np.float64) / SAMPLING_RATE
    mv = dec.samples.astype(np.float64) * MV_PER_UNIT
    table = np.column_stack([t, mv, dec.qrs.astype(np.int8)])
    header = "time_s,{}_mV,{}_mV,{}_mV,qrs".format(*LEAD_LABELS)
    np.savetxt(out_path, table, delimiter=",", header=header, comments="",
               fmt=["%.4f", "%.3f", "%.3f", "%.3f", "%d"])


def _build_edf(samples: np.ndarray, start: datetime | None, dev: DeviceInfo):
    """Baut ein Edf-Objekt aus einem (N,3)-Sample-Block (Einheit 0,01 mV).

    Verlustfrei zur Geräteauflösung: EDF+ nutzt 16-Bit-Digitalwerte über den
    physikalischen Bereich des Blocks – bei wenigen mV feiner als die 0,01-mV-Rasterung.
    """
    from edfio import Edf, EdfSignal, Patient, Recording
    fs_i = int(SAMPLING_RATE)
    n = samples.shape[0]
    whole = n - (n % fs_i)                          # EDF-Datensätze = ganze Sekunden
    if whole >= fs_i:
        samples = samples[:whole]
    signals = []
    for i, label in enumerate(LEAD_LABELS):
        sig = samples[:, i].astype(np.float64) * MV_PER_UNIT
        pmin, pmax = float(sig.min()), float(sig.max())
        if pmax <= pmin:
            pmax = pmin + 1.0
        signals.append(EdfSignal(sig, sampling_frequency=SAMPLING_RATE,
                                 label=f"ECG {label}", physical_dimension="mV",
                                 physical_range=(pmin, pmax)))
    equipment = f"{dev.model}_SN{dev.serial}".strip().replace(" ", "_") or "X"
    return Edf(signals=signals, patient=Patient(code="X"),
               recording=Recording(startdate=start.date() if start else None,
                                    equipment_code=equipment),
               starttime=start.time() if start else None)


def export_edf(dec: DecodedRecord, out_path: str, dev: DeviceInfo) -> None:
    _build_edf(dec.samples, dec.start, dev).write(out_path)


def export_plot(dec: DecodedRecord, out_path: str, seconds: float = 10.0,
                offset_s: float = 0.0, title: str = "") -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    start_i = max(0, int(offset_s * SAMPLING_RATE))
    n = min(int(seconds * SAMPLING_RATE), dec.n_samples - start_i)
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
    import matplotlib.pyplot as plt2
    plt2.close(fig)
    return True


def convert(input_dir: str, output_dir: str, formats=("edf", "csv"),
            make_plot=True, plot_at: str | None = None, log=print) -> int:
    """Kompletter Batch-Lauf (von der CLI genutzt)."""
    base = resolve_input(input_dir)
    if not base:
        log(f"FEHLER: In '{input_dir}' kein Datenträger (README.TXT + ECG_0/) gefunden.")
        return 2
    if "edf" in formats:
        try:
            import edfio  # noqa: F401
        except ImportError:
            log("FEHLER: Für den EDF-Export fehlt das Paket 'edfio'.")
            log("  Am einfachsten den Starter nutzen (Start_Windows.bat / Start_Linux.sh),")
            log("  oder manuell:  pip install edfio")
            log("  (Alternativ nur CSV erzeugen:  --formats csv)")
            return 3

    dev = parse_readme(os.path.join(base, "README.TXT"))
    os.makedirs(output_dir, exist_ok=True)
    log(f"Eingabe: {base}")
    log(f"Ausgabe: {output_dir}")
    log(f"Gerät: {dev.model} (V{dev.version}, SN {dev.serial}) — "
        f"{len(dev.records)} Aufnahme(n)")

    results = []
    for rec in dev.records:
        log(f"\nAufnahme {rec.index}: Dateien {rec.first_file}–{rec.last_file} "
            f"({len(rec.file_numbers)} Segmente) …")
        dec = decode_record(base, rec)
        log(f"  dekodiert: {dec.n_files_ok} ok, {dec.n_files_failed} fehlerhaft; "
            f"{dec.duration_s / 60:.1f} min; Start: {dec.start or 'unbekannt'}")
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
            target = datetime.combine(dec.start.date(), datetime.min.time()).replace(
                hour=h, minute=m, second=s)
            if target < dec.start:
                target += timedelta(days=1)
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
# Analyse (technische Hinweise – KEINE Diagnose)
# --------------------------------------------------------------------------- #
def beat_indices(dec: DecodedRecord) -> np.ndarray:
    """Sample-Indizes der HW-erkannten Herzschläge."""
    return np.flatnonzero(dec.qrs)


def rr_series(dec: DecodedRecord):
    """RR-Intervalle: (Zeitpunkt[s] des Schlags, RR[s] zum vorherigen)."""
    idx = beat_indices(dec)
    t = idx / SAMPLING_RATE
    if len(t) < 2:
        return np.array([]), np.array([])
    return t[1:], np.diff(t)


def hrv_metrics(dec: DecodedRecord) -> dict:
    """Standard-HRV-Kennzahlen aus den RR-Intervallen (physiolog. gefiltert)."""
    _, rr = rr_series(dec)
    rr_ms = rr * 1000.0
    v = rr_ms[(rr_ms > 300) & (rr_ms < 2000)]     # 30–200 bpm
    if len(v) < 2:
        return {}
    d = np.diff(v)
    return {
        "beats": int(len(beat_indices(dec))),
        "mean_hr": 60000.0 / np.mean(v),
        "min_hr": 60000.0 / np.max(v),
        "max_hr": 60000.0 / np.min(v),
        "sdnn_ms": float(np.std(v, ddof=1)),
        "rmssd_ms": float(np.sqrt(np.mean(d ** 2))),
        "pnn50_pct": float(np.mean(np.abs(d) > 50) * 100.0),
    }


def hr_trend(dec: DecodedRecord, bin_s: float = 30.0):
    """Mittlere Herzfrequenz je Zeitfenster (für den Verlaufs-Plot)."""
    t, rr = rr_series(dec)
    if len(t) == 0:
        return np.array([]), np.array([])
    hr = 60.0 / rr
    ok = (hr > 25) & (hr < 250)
    t, hr = t[ok], hr[ok]
    if len(t) == 0:
        return np.array([]), np.array([])
    nbins = max(1, int(dec.duration_s // bin_s) + 1)
    edges = np.arange(nbins + 1) * bin_s
    which = np.clip((t // bin_s).astype(int), 0, nbins - 1)
    centers, means = [], []
    for b in range(nbins):
        vals = hr[which == b]
        if len(vals):
            centers.append((b + 0.5) * bin_s)
            means.append(float(np.mean(vals)))
    return np.array(centers), np.array(means)


def neurokit_analysis(dec: DecodedRecord) -> dict | None:
    """Erweiterte Analyse mit NeuroKit2 (falls installiert): robuste R-Zacken,
    reichere HRV (Zeit-/Frequenzdomäne, Poincaré SD1/SD2) und Signalqualität.

    Gibt None zurück, wenn NeuroKit2 fehlt oder etwas schiefgeht (dann bleibt die
    numpy-Basisanalyse aktiv). ⚠️ Technische Kennzahlen – KEINE Diagnose.
    """
    if not HAS_NEUROKIT:
        return None
    try:
        import neurokit2 as nk
        fs = SAMPLING_RATE
        sig = dec.samples[:, 1].astype(float) * MV_PER_UNIT
        cleaned = nk.ecg_clean(sig, sampling_rate=fs)
        _, info = nk.ecg_peaks(cleaned, sampling_rate=fs)
        rp = np.asarray(info["ECG_R_Peaks"])
        out: dict = {"n_rpeaks": int(len(rp)), "method": "NeuroKit2", "rpeaks": rp}

        def _g(df, name):
            try:
                v = float(df["HRV_" + name].iloc[0])
                return None if np.isnan(v) else v
            except Exception:
                return None

        try:
            ht = nk.hrv_time(rp, sampling_rate=fs)
            hfd = nk.hrv_frequency(rp, sampling_rate=fs)
            rr = np.diff(rp) / fs
            sd1 = sd2 = None
            if len(rr) > 2:
                sd1 = float(np.std(np.diff(rr), ddof=1) / np.sqrt(2) * 1000)
                sd2 = float(np.sqrt(max(0.0, 2 * np.var(rr, ddof=1)
                                       - 0.5 * np.var(np.diff(rr), ddof=1))) * 1000)
            out["hrv"] = {"MeanNN": _g(ht, "MeanNN"), "MedianNN": _g(ht, "MedianNN"),
                          "SDNN": _g(ht, "SDNN"), "SDANN": _g(ht, "SDANN1"),
                          "SDNNI": _g(ht, "SDNNI1"), "RMSSD": _g(ht, "RMSSD"),
                          "pNN50": _g(ht, "pNN50"), "pNN20": _g(ht, "pNN20"),
                          "HTI": _g(ht, "HTI"),
                          "SD1": sd1, "SD2": sd2, "LFHF": _g(hfd, "LFHF")}
        except Exception:
            out["hrv"] = {}

        try:  # Signalqualität als Zeitleiste (schnell: ~120 Stichproben à 8 s)
            w = int(8 * fs)
            n_win = min(120, max(1, len(cleaned) // w))
            starts = np.linspace(0, max(1, len(cleaned) - w), n_win).astype(int)
            qt, qv = [], []
            for s in starts:
                qt.append((s + w / 2) / fs)
                qv.append(float(np.nanmean(nk.ecg_quality(cleaned[s:s + w], sampling_rate=fs))))
            if qv:
                qt, qv = np.asarray(qt), np.asarray(qv)
                out["quality_t"] = qt
                out["quality_v"] = qv
                out["quality_mean"] = float(np.mean(qv))
                out["quality_low_pct"] = float(np.mean(qv < 0.5) * 100)
        except Exception:
            pass
        return out
    except Exception:
        return None


def _clock(dec: DecodedRecord, sec: float) -> str:
    if dec.start is None:
        return f"{sec:.0f}s"
    return (dec.start + timedelta(seconds=sec)).strftime("%d.%m %H:%M:%S")


def _rolling_median(x: np.ndarray, w: int = 11) -> np.ndarray:
    n = len(x)
    half = w // 2
    out = np.empty(n)
    for i in range(n):
        out[i] = np.median(x[max(0, i - half): i + half + 1])
    return out


def event_counts(events: list[dict]) -> dict:
    from collections import Counter
    return dict(Counter(e["typ"] for e in events))


def detect_events(dec: DecodedRecord, brady=50.0, tachy=100.0, pause_s=2.0,
                  nk: dict | None = None) -> list[dict]:
    """Technische Auffälligkeiten als anspringbare Ereignisliste.

    Erkennt: Pausen, Bradykardie-/Tachykardie-Phasen, Extrasystolen (vorzeitige
    Schläge), unregelmäßigen Rhythmus (Verdacht), geräteseitig markierte Schläge
    und Signalqualitäts-Abschnitte.

    Schlagquelle: wenn `nk` (NeuroKit2-Analyse) übergeben ist, werden dessen
    robuste R-Zacken statt der Geräte-Marker verwendet; zusätzlich werden
    Auffälligkeiten in signalschwachen Abschnitten als „unsicher" markiert.

    ⚠️ Rein technische Hinweise zur Durchsicht – KEINE Diagnose.
    """
    events: list[dict] = []
    # Schlagquelle: NeuroKit-R-Zacken bevorzugen, sonst Geräte-Marker
    if nk and nk.get("rpeaks") is not None and len(nk["rpeaks"]) > 2:
        idx = np.asarray(nk["rpeaks"])
    else:
        idx = beat_indices(dec)
    if len(idx) < 3:
        return events
    tt = idx / SAMPLING_RATE
    rr = np.diff(tt)
    t = tt[1:]                       # Zeitpunkt des jeweils 2. Schlags eines RR
    hr = np.where(rr > 0, 60.0 / rr, 0.0)
    med = _rolling_median(rr, 11)

    qt = nk.get("quality_t") if nk else None
    qv = nk.get("quality_v") if nk else None

    def _low_quality(time_s: float) -> bool:
        if qt is None or qv is None or len(qt) == 0:
            return False
        return float(np.interp(time_s, qt, qv)) < 0.5

    # 1) Pausen (langes RR)
    for ti, rri in zip(t[rr >= pause_s], rr[rr >= pause_s]):
        events.append({
            "typ": "Pause", "zeit_s": float(ti - rri),
            "dauer_s": float(rri),
            "wert": f"{rri:.1f} s ohne Schlag",
            "detail": (
                f"Zwischen zwei erkannten R-Zacken lagen {rri:.1f} s ganz ohne Herzschlag. "
                f"Erkannt, weil der Abstand zweier Schläge ≥ {pause_s:.0f} s war "
                f"(an dieser Stelle rechnerisch nur ~{60.0 / rri:.0f} bpm). "
                f"Je länger die Pause, desto auffälliger.")})

    # 2) anhaltende Brady-/Tachykardie (>= 5 Schläge in Folge)
    def _sustained(mask, label, kind):
        i = 0
        while i < len(mask):
            if mask[i]:
                j = i
                while j < len(mask) and mask[j]:
                    j += 1
                if j - i >= 5:
                    seg = hr[i:j]
                    dur = float(t[j - 1] - t[i])
                    nbeats = j - i
                    mean_hr = float(np.mean(seg))
                    if kind == "brady":
                        extreme = float(np.min(seg))
                        detail = (
                            f"{nbeats} aufeinanderfolgende Schläge mit im Schnitt "
                            f"~{mean_hr:.0f} bpm über {dur:.0f} s; langsamster Schlag "
                            f"~{extreme:.0f} bpm. Erkannt, weil ≥ 5 Schläge in Folge unter "
                            f"{brady:.0f} bpm lagen (anhaltend langsamer Rhythmus).")
                    else:
                        extreme = float(np.max(seg))
                        detail = (
                            f"{nbeats} aufeinanderfolgende Schläge mit im Schnitt "
                            f"~{mean_hr:.0f} bpm über {dur:.0f} s; schnellster Schlag "
                            f"~{extreme:.0f} bpm. Erkannt, weil ≥ 5 Schläge in Folge über "
                            f"{tachy:.0f} bpm lagen (anhaltend schneller Rhythmus).")
                    events.append({"typ": label, "zeit_s": float(t[i]),
                                   "dauer_s": dur, "wert": f"~{mean_hr:.0f} bpm über {dur:.0f} s",
                                   "detail": detail})
                i = j
            else:
                i += 1

    _sustained((hr < brady) & (hr > 20), "Bradykardie", "brady")
    _sustained(hr > tachy, "Tachykardie", "tachy")

    # 3) Extrasystolen: deutlich vorzeitige Schläge (>=20 % früher als lokal üblich),
    #    in Häufungen gruppiert. Kompensatorische Pause wird notiert, aber nicht verlangt.
    prem = np.zeros(len(rr), dtype=bool)
    for i in range(1, len(rr) - 1):
        if med[i] > 0 and rr[i] < 0.80 * med[i]:
            prem[i] = True
    pidx = np.flatnonzero(prem)
    if len(pidx):
        for g in np.split(pidx, np.flatnonzero(np.diff(t[pidx]) > 10.0) + 1):
            n = len(g)
            ratios = rr[g] / med[g]                       # < 0.8 = so viel früher
            avg_early = float((1.0 - np.mean(ratios)) * 100.0)
            max_early = float((1.0 - np.min(ratios)) * 100.0)
            dur = float(t[g[-1]] - t[g[0]])
            if n == 1:
                wert = "vorzeitiger Schlag"
                detail = (
                    f"Ein einzelner Schlag kam {avg_early:.0f} % früher als der lokale Median "
                    f"der Schlag-Abstände. Erkannt als ≥ 20 % verfrühter Schlag – typisch für "
                    f"eine Extrasystole (Extraschlag).")
            else:
                wert = f"{n} vorzeitige Schläge"
                detail = (
                    f"{n} verfrühte Schläge innerhalb von {dur:.0f} s gehäuft, im Schnitt "
                    f"{avg_early:.0f} % (bis zu {max_early:.0f} %) früher als der lokale Median "
                    f"der Schlag-Abstände. Erkannt als ≥ 20 % verfrühte Schläge – typisch für "
                    f"Extrasystolen.")
            events.append({"typ": "Extrasystolen (Verdacht)", "zeit_s": float(t[g[0]]),
                           "dauer_s": dur, "wert": wert, "detail": detail})

    # 4) Unregelmäßiger Rhythmus (Verdacht): "irregularly irregular" im 30-Schlag-Fenster
    dabs = np.abs(np.diff(rr))
    W = 30
    if len(dabs) >= W:
        frac = np.convolve((dabs > 0.12).astype(float), np.ones(W) / W, mode="valid")
        fi = np.flatnonzero(frac > 0.5)
        if len(fi):
            for g in np.split(fi, np.flatnonzero(np.diff(fi) > W) + 1):
                a, b = g[0], min(g[-1] + W, len(t) - 1)
                dur = float(t[b] - t[a])
                if dur >= 10:
                    events.append({
                        "typ": "Unregelmäßiger Rhythmus (Verdacht)",
                        "zeit_s": float(t[a]), "dauer_s": dur, "wert": f"über {dur:.0f} s",
                        "detail": (
                            f"Über {dur:.0f} s wechselten die Schlag-Abstände stark und ohne "
                            f"erkennbares Muster: In mehr als der Hälfte eines 30-Schlag-Fensters "
                            f"sprangen aufeinanderfolgende Abstände um über 120 ms. Muster eines "
                            f"„unregelmäßig unregelmäßigen“ Rhythmus.")})

    # 5) Geräte-Marker (unregelmäßige Schläge)
    irr_idx = np.flatnonzero(dec.irregular)
    if len(irr_idx):
        for g in np.split(irr_idx, np.flatnonzero(np.diff(irr_idx) > SAMPLING_RATE * 2) + 1):
            dur = float((g[-1] - g[0]) / SAMPLING_RATE)
            events.append({
                "typ": "Unregelmäßig (Gerät)", "zeit_s": float(g[0] / SAMPLING_RATE),
                "dauer_s": dur, "wert": f"{len(g)} markierte Stelle(n)",
                "detail": (
                    f"{len(g)} Stelle(n) über ~{max(1.0, dur):.0f} s, die das Gerät selbst "
                    f"während der Aufnahme als unregelmäßigen Schlag markiert hat. Direkt aus "
                    f"den Geräte-Markierungen übernommen – nicht aus der Software-Analyse.")})

    # 6) Signalqualität: bevorzugt NeuroKit-Qualität, sonst Flachlinien-Heuristik
    if qt is not None and qv is not None and len(qt):
        li = np.flatnonzero(qv < 0.4)
        if len(li):
            for g in np.split(li, np.flatnonzero(np.diff(li) > 1) + 1):
                a, b = float(qt[g[0]]), float(qt[g[-1]])
                dur = max(8.0, b - a)
                events.append({
                    "typ": "Signalqualität niedrig (NeuroKit2)", "zeit_s": a, "dauer_s": dur,
                    "wert": f"schwaches Signal ~{dur:.0f} s",
                    "detail": (
                        f"Über ~{dur:.0f} s lag der NeuroKit2-Qualitätsindex unter 0.4 "
                        f"(schwaches/gestörtes Signal, oft Bewegung oder Elektrodenkontakt). "
                        f"Auffälligkeiten in diesem Abschnitt sind nur eingeschränkt beurteilbar.")})
    else:
        sig = dec.samples[:, 1].astype(float)
        win = int(2 * SAMPLING_RATE)
        nb = len(sig) // win
        if nb:
            stds = sig[:nb * win].reshape(nb, win).std(axis=1)
            bi = np.flatnonzero(stds < 3.0)
            if len(bi):
                for g in np.split(bi, np.flatnonzero(np.diff(bi) > 1) + 1):
                    dur = len(g) * 2
                    if dur >= 4:
                        events.append({
                            "typ": "Signalqualität niedrig / Artefakt",
                            "zeit_s": float(g[0] * win / SAMPLING_RATE), "dauer_s": float(dur),
                            "wert": f"flaches/gestörtes Signal ~{dur} s",
                            "detail": (
                                f"Über ~{dur} s war das Signal flach oder gestört (sehr geringe "
                                f"Amplituden-Streuung). Heuristisch erkannt, weil NeuroKit2 nicht "
                                f"verfügbar war – vermutlich Elektroden-/Kontaktproblem.")})

    # Qualitätsfilter: Auffälligkeiten in schwachem Signal als „unsicher" kennzeichnen
    for e in events:
        if not e["typ"].startswith("Signalqualität") and _low_quality(e["zeit_s"]):
            e["unsicher"] = True
            e["wert"] = f"{e['wert']} · Signal unsicher"
            e["detail"] = (f"{e['detail']} Hinweis: Das Signal ist hier schwach – "
                           f"diese Erkennung ist unsicher.")

    events.sort(key=lambda e: e["zeit_s"])
    for i, e in enumerate(events, 1):     # feste, konsistente Nummer (nach Sortierung)
        e["nr"] = i
    return events


def csv_bytes(dec: DecodedRecord) -> bytes:
    """CSV als Bytes (für Direkt-Download im Browser)."""
    import io as _io
    n = dec.n_samples
    t = np.arange(n, dtype=np.float64) / SAMPLING_RATE
    mv = dec.samples.astype(np.float64) * MV_PER_UNIT
    table = np.column_stack([t, mv, dec.qrs.astype(np.int8)])
    buf = _io.StringIO()
    np.savetxt(buf, table, delimiter=",",
               header="time_s,{}_mV,{}_mV,{}_mV,qrs".format(*LEAD_LABELS),
               comments="", fmt=["%.4f", "%.3f", "%.3f", "%.3f", "%d"])
    return buf.getvalue().encode("utf-8")


def _edf_to_bytes(edf) -> bytes:
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".edf")
    os.close(fd)
    try:
        edf.write(tmp)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def edf_bytes(dec: DecodedRecord, dev: DeviceInfo) -> bytes:
    """EDF+ der ganzen Aufnahme als Bytes (für Direkt-Download im Browser)."""
    return _edf_to_bytes(_build_edf(dec.samples, dec.start, dev))


def edf_segment_bytes(dec: DecodedRecord, dev: DeviceInfo,
                      i0: int, i1: int) -> bytes:
    """EDF+ nur für den Ausschnitt [i0:i1] (Sample-Indizes) als Bytes.

    Startzeitstempel = Aufnahmestart + i0/fs. Verlustfrei zur Geräteauflösung.
    Die Länge wird auf ganze Sekunden gekürzt (EDF-Datensätze), damit gängige
    Viewer (EDFbrowser) sie sauber öffnen.
    """
    i0 = max(0, int(i0))
    i1 = min(dec.n_samples, int(i1))
    n = i1 - i0
    whole = n - (n % int(SAMPLING_RATE))          # auf volle Sekunden runden
    if whole >= int(SAMPLING_RATE):
        i1 = i0 + whole
    if i1 <= i0:
        raise ValueError("Leerer oder zu kurzer Ausschnitt für den EDF-Export.")
    start = (dec.start + timedelta(seconds=i0 / SAMPLING_RATE)) if dec.start else None
    return _edf_to_bytes(_build_edf(dec.samples[i0:i1], start, dev))


def view_pdf_bytes(dec: DecodedRecord, dev: DeviceInfo, i0: int, i1: int,
                   nk: dict | None = None) -> bytes:
    """Der aktuell gezeigte EKG-Ausschnitt [i0:i1] als druckfertiges PDF (Bytes).

    Zeichnet – wie im „EKG ansehen“-Tab – die drei Ableitungen plus Pulsverlauf neu
    (matplotlib), damit der Ausdruck immer vollständig auf ein A4-Blatt (quer) passt.
    ⚠️ Kein Medizinprodukt – technische Aufbereitung, keine Diagnose.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    fs = SAMPLING_RATE
    i0 = max(0, int(i0))
    i1 = min(dec.n_samples, int(i1))
    if i1 <= i0:
        raise ValueError("Leerer Ausschnitt.")
    t = np.arange(i0, i1) / fs
    mv = dec.samples[i0:i1].astype(float) * MV_PER_UNIT
    dur = float(t[-1] - t[0]) if len(t) > 1 else 0.0

    if nk and nk.get("rpeaks") is not None and len(np.asarray(nk["rpeaks"])):
        all_beats = np.asarray(nk["rpeaks"])
    else:
        all_beats = np.flatnonzero(dec.qrs)
    beats = all_beats[(all_beats >= i0) & (all_beats < i1)]

    hr_t = hr_v = None                                  # Momentan-Puls (60/RR) im Fenster
    bt = all_beats / fs
    if len(bt) >= 2:
        rr = np.diff(bt)
        ht, hv = bt[1:], np.where(rr > 0, 60.0 / rr, np.nan)
        m = (ht >= t[0]) & (ht <= t[-1]) & (hv > 25) & (hv < 250)
        hr_t, hr_v = ht[m], hv[m]

    # Rasterdichte an die Fensterlänge anpassen (EKG-Millimeterraster nur bei kurzen Fenstern)
    if dur <= 30:
        maj, minr = 0.2, 0.04
    else:
        maj = max(1.0, round(dur / 12.0))
        minr = maj / 5.0

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        fig, axes = plt.subplots(4, 1, figsize=(11.69, 8.27), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 3, 3, 2]})
        fig.suptitle(
            f"Heal Force Prince 180D – Aufnahme {dec.record.index}   ·   "
            f"{_clock(dec, float(t[0]))}   ·   {dur:.0f} s   (10 mm/mV, 25 mm/sec)",
            fontsize=11)
        for r, label in enumerate(LEAD_LABELS):
            ax = axes[r]
            ax.plot(t, mv[:, r], color="black", linewidth=0.7)
            ax.set_ylabel(f"{label}\n[mV]", rotation=0, ha="right", va="center")
            ax.xaxis.set_major_locator(plt.MultipleLocator(maj))
            ax.xaxis.set_minor_locator(plt.MultipleLocator(minr))
            ax.yaxis.set_major_locator(plt.MultipleLocator(0.5))
            ax.yaxis.set_minor_locator(plt.MultipleLocator(0.1))
            ax.grid(which="major", color="red", alpha=0.5, linewidth=0.6)
            ax.grid(which="minor", color="red", alpha=0.2, linewidth=0.4)
            ax.set_xlim(t[0], t[-1])
        if len(beats):                                   # QRS-Marker auf Ableitung II
            axes[1].plot(beats / fs, dec.samples[beats, 1].astype(float) * MV_PER_UNIT,
                         "o", color="red", ms=3)
        axp = axes[3]
        if hr_t is not None and len(hr_t):
            axp.plot(hr_t, hr_v, "-o", color="crimson", ms=3, linewidth=1.0)
        axp.set_ylabel("Puls\n[bpm]", rotation=0, ha="right", va="center")
        axp.grid(which="major", color="red", alpha=0.3, linewidth=0.5)
        axp.xaxis.set_major_locator(plt.MultipleLocator(maj))
        axp.set_xlim(t[0], t[-1])
        axes[-1].set_xlabel("Zeit [s] seit Aufnahmestart")
        fig.text(0.01, 0.01, "Kein Medizinprodukt – keine Diagnose, nur technische Aufbereitung.",
                 fontsize=7, style="italic")
        fig.tight_layout(rect=(0, 0.02, 1, 0.96))
        pdf.savefig(fig)
        plt.close(fig)
    return buf.getvalue()


def build_report_pdf(dec: DecodedRecord, dev: DeviceInfo,
                     brady=50.0, tachy=100.0, nk: dict | None = None) -> bytes:
    """Mehrseitiger technischer Bericht als PDF (Bytes). KEINE Diagnose."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    if nk is None and HAS_NEUROKIT:
        nk = neurokit_analysis(dec)
    m = hrv_metrics(dec)
    tc, hr_tr = hr_trend(dec, bin_s=30)
    events = detect_events(dec, brady=brady, tachy=tachy, nk=nk)
    counts = event_counts(events)
    hs = hourly_stats(dec)
    _, rr = rr_series(dec)
    rr_ok = rr[(rr > 0.3) & (rr < 2.0)]
    foot = "Kein Medizinprodukt – keine Diagnose, nur technische Aufbereitung."

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # ---------- Seite 1: Übersicht + HF-Verlauf + Stunden ----------
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Heal Force Prince 180D – Technischer Bericht", fontsize=15)
        lines = [
            f"Gerät:              {dev.model} (SN {dev.serial})",
            f"Aufnahme {dec.record.index}",
            f"Start:              {dec.start}",
            f"Dauer:              {dec.duration_s/60:.0f} min",
            f"Erkannte Schläge:   {m.get('beats','?')}",
            f"Herzfrequenz:       Ø {m.get('mean_hr',0):.0f}  (min {m.get('min_hr',0):.0f}"
            f" / max {m.get('max_hr',0):.0f}) bpm",
            f"HRV:                SDNN {m.get('sdnn_ms',0):.0f} ms,"
            f" RMSSD {m.get('rmssd_ms',0):.0f} ms, pNN50 {m.get('pnn50_pct',0):.1f} %",
            f"Auffälligkeiten:    {len(events)} gesamt",
        ]
        fig.text(0.07, 0.93, "\n".join(lines), va="top", fontsize=9.5, family="monospace")

        if nk:
            hv = nk.get("hrv", {})

            def _n(v):
                return f"{v:.0f} ms" if isinstance(v, (int, float)) else "–"

            nlines = ["NeuroKit2 (erweitert):",
                      f"R-Zacken: {nk.get('n_rpeaks', '?')}"]
            if nk.get("quality_mean") is not None:
                nlines.append(f"Signalqualitaet Ø: {nk['quality_mean']:.2f}")
                nlines.append(f"  niedrig: {nk.get('quality_low_pct', 0):.0f} % d. Fenster")
            nlines += [f"SDNN/RMSSD: {_n(hv.get('SDNN'))} / {_n(hv.get('RMSSD'))}",
                       f"Poincare SD1/SD2: {_n(hv.get('SD1'))} / {_n(hv.get('SD2'))}",
                       f"LF/HF: {hv['LFHF']:.2f}" if hv.get("LFHF") is not None else "LF/HF: –"]
            fig.text(0.55, 0.93, "\n".join(nlines), va="top", fontsize=9, family="monospace")

        ax1 = fig.add_axes((0.09, 0.52, 0.85, 0.22))
        if len(tc):
            ax1.plot(tc / 60, hr_tr, color="crimson", lw=0.7)
        ax1.axhline(tachy, color="orange", ls="--", lw=0.6, label=f"Tachy {tachy:.0f}")
        ax1.axhline(brady, color="steelblue", ls="--", lw=0.6, label=f"Brady {brady:.0f}")
        ax1.set_title("Herzfrequenz-Verlauf"); ax1.set_xlabel("Minuten seit Start")
        ax1.set_ylabel("bpm"); ax1.legend(fontsize=7, loc="upper right")

        ax2 = fig.add_axes((0.09, 0.24, 0.85, 0.18))
        if hs:
            x = range(len(hs))
            ax2.fill_between(x, [r["hf_min"] for r in hs], [r["hf_max"] for r in hs],
                             alpha=0.2, color="crimson")
            ax2.plot(x, [r["hf_mittel"] for r in hs], "-o", ms=3, color="crimson")
            ax2.set_xticks(list(x))
            ax2.set_xticklabels([r["uhrzeit"] for r in hs], rotation=45, fontsize=6, ha="right")
        ax2.set_title("Herzfrequenz je Stunde (Ø, Bereich min–max)"); ax2.set_ylabel("bpm")
        fig.text(0.07, 0.03, foot, fontsize=8, style="italic")
        pdf.savefig(fig); plt.close(fig)

        # ---------- Seite 2: Auffälligkeiten + Rhythmus-Grafiken ----------
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Auffälligkeiten & Rhythmus", fontsize=14)

        axb = fig.add_axes((0.30, 0.74, 0.60, 0.16))
        if counts:
            keys = list(counts)
            axb.barh(keys, [counts[k] for k in keys], color="steelblue")
            axb.invert_yaxis(); axb.tick_params(axis="y", labelsize=7)
            axb.set_title("Auffälligkeiten nach Typ (Anzahl)")
        else:
            axb.axis("off"); axb.text(0.5, 0.5, "Keine markanten Auffälligkeiten",
                                      ha="center", va="center")

        axp = fig.add_axes((0.10, 0.42, 0.36, 0.24))
        if len(rr) > 2:
            axp.scatter(rr[:-1], rr[1:], s=2, alpha=0.25, color="purple")
        axp.set_title("Poincaré (RRₙ↔RRₙ₊₁)", fontsize=9)
        axp.set_xlabel("s"); axp.set_ylabel("s")

        axh = fig.add_axes((0.57, 0.42, 0.36, 0.24))
        if len(rr_ok):
            axh.hist(rr_ok, bins=50, color="teal")
        axh.set_title("RR-Intervalle", fontsize=9); axh.set_xlabel("s")

        axt = fig.add_axes((0.10, 0.10, 0.83, 0.22))
        if events:
            types = sorted(set(e["typ"] for e in events))
            ymap = {ty: i for i, ty in enumerate(types)}
            axt.scatter([e["zeit_s"] / 3600 for e in events],
                        [ymap[e["typ"]] for e in events], s=12, color="firebrick")
            axt.set_yticks(range(len(types)))
            axt.set_yticklabels(types, fontsize=7)
            axt.set_xlabel("Stunden seit Start")
            axt.set_title("Auffälligkeiten über die Zeit", fontsize=9)
        else:
            axt.axis("off")
        fig.text(0.07, 0.03, foot, fontsize=8, style="italic")
        pdf.savefig(fig); plt.close(fig)

        # ---------- Seite 3: Ereignisliste ----------
        if events:
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.suptitle("Auffälligkeiten – Liste (zur Durchsicht)", fontsize=14)
            rows = events[:60]
            txt = "\n".join(
                f"{e.get('nr', i + 1):>3}  {_clock(dec, e['zeit_s']):>17}  "
                f"{e['typ']:<32.32} {e['wert']}"
                for i, e in enumerate(rows))
            if len(events) > 60:
                txt += f"\n\n… und {len(events) - 60} weitere (siehe App)."
            fig.text(0.05, 0.93, "Nr.        Zeit           Typ / Erkennung\n\n" + txt,
                     va="top", fontsize=7.5, family="monospace")
            fig.text(0.07, 0.03, foot, fontsize=8, style="italic")
            pdf.savefig(fig); plt.close(fig)
    return buf.getvalue()


def hourly_stats(dec: DecodedRecord) -> list[dict]:
    """Statistik je Uhrzeit-Stunde (mittlere/min/max HF, Anzahl Schläge)."""
    t, rr = rr_series(dec)
    if len(t) == 0 or dec.start is None:
        return []
    hr = 60.0 / rr
    ok = (hr > 25) & (hr < 250)
    t, hr = t[ok], hr[ok]
    rows = []
    start = dec.start
    hours = int(dec.duration_s // 3600) + 1
    for h in range(hours):
        lo, hi = h * 3600, (h + 1) * 3600
        sel = (t >= lo) & (t < hi)
        if not np.any(sel):
            continue
        vals = hr[sel]
        rows.append({
            "uhrzeit": (start + timedelta(seconds=lo)).strftime("%d.%m %H:%M"),
            "nach_s": lo,          # Sekunden seit Aufnahmebeginn (für relative Anzeige)
            "hf_mittel": float(np.mean(vals)),
            "hf_min": float(np.min(vals)),
            "hf_max": float(np.max(vals)),
            "schlaege": int(len(vals)),
        })
    return rows
