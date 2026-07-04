#!/usr/bin/env python3
"""Grafische Version (Web-App) für den Heal Force Prince 180D.

Start:  streamlit run app.py      (oder Start_GUI_Linux.sh / Start_GUI_Windows.bat)

Bietet: Quelle/Ziel wählen, EKG scrollbar ansehen (3 Ableitungen), technische
Analyse (Herzfrequenz-Verlauf, HRV, Auffälligkeiten, Stunden-Statistik), Export
nach EDF+/CSV und ein PDF-Kurzbericht.

Kein Medizinprodukt – die Analyse liefert technische Hinweise zur Durchsicht,
KEINE Diagnose.
"""

from __future__ import annotations

import os
import string
from datetime import timedelta

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import hf180d as h

st.set_page_config(page_title="180D EKG – Viewer & Analyse", layout="wide")

ss = st.session_state
ss.setdefault("records", {})      # index -> DecodedRecord
ss.setdefault("analysis", {})     # index -> dict
ss.setdefault("dev", None)
ss.setdefault("base", None)
ss.setdefault("view_start", 0.0)


def auto_find() -> str | None:
    roots = ([f"{d}:\\" for d in string.ascii_uppercase] if os.name == "nt"
             else ["/run/media", "/media", "/mnt"]) + [os.getcwd()]
    for r in roots:
        if os.path.isdir(r):
            hit = h.resolve_input(r)
            if hit:
                return hit
    return None


def clock(dec, sec: float) -> str:
    if dec.start is None:
        return f"{sec:.0f} s"
    return (dec.start + timedelta(seconds=sec)).strftime("%d.%m %H:%M:%S")


def load_source(base: str) -> None:
    """Dekodiert alle Aufnahmen des Datenträgers und legt sie in den State."""
    dev = h.parse_readme(os.path.join(base, "README.TXT"))
    prog = st.progress(0.0, "Dekodiere …")
    recs, ana = {}, {}
    for ri, rec in enumerate(dev.records):
        def cb(i, n, ri=ri, rec=rec, nrec=len(dev.records)):
            prog.progress((ri + i / n) / nrec, f"Aufnahme {rec.index}: {i}/{n} Segmente")
        dec = h.decode_record(base, rec, progress=cb)
        if h.HAS_NEUROKIT:
            prog.progress((ri + 1) / len(dev.records),
                          f"Aufnahme {rec.index}: erweiterte Analyse (NeuroKit2) …")
        nk = h.neurokit_analysis(dec)
        recs[rec.index] = dec
        ana[rec.index] = {
            "nk": nk,
            "hrv": h.hrv_metrics(dec),
            "events": h.detect_events(dec, nk=nk),   # nutzt NeuroKit-R-Zacken falls vorhanden
            "trend": h.hr_trend(dec, bin_s=30),
            "hourly": h.hourly_stats(dec),
        }
    prog.empty()
    ss.records, ss.analysis, ss.dev, ss.base = recs, ana, dev, base
    ss.view_start = 0.0
    st.success("Dekodiert. Unten eine Aufnahme wählen.")


# --------------------------------------------------------------------------- #
st.title("🫀 Heal Force Prince 180D – EKG Viewer & Analyse")
st.caption("⚠️ Kein Medizinprodukt – technische Aufbereitung und Hinweise, **keine Diagnose**.")

# ---- Sidebar: Datenquelle laden ----
with st.sidebar:
    st.header("1) Datenträger laden")

    if st.button("🔎 Automatisch suchen", width="stretch"):
        found = auto_find()
        if found:
            ss.base = found
            st.success("Gefunden – unten auf 'Laden' klicken.")
        else:
            st.warning("Nichts gefunden – bitte Pfad eingeben.")

    path = st.text_input(
        "Ordner des Datenträgers (mit ECG_0 / README.TXT)",
        value=ss.base or "",
        help="Darf direkt das Laufwerk sein, z. B. E:\\ . "
             "Tipp: den Ordner ins Feld ziehen fügt den Pfad ein.")

    if st.button("📥 Laden / Dekodieren", type="primary", width="stretch"):
        base = h.resolve_input(path)
        if not base:
            st.error("Kein gültiger Datenträger (README.TXT + ECG_0/) an diesem Pfad.")
        else:
            load_source(base)

if not ss.records:
    st.info("Links den Datenträger wählen und **Laden / Dekodieren** drücken. "
            "Das darf direkt das Laufwerk des Geräts sein (z. B. `E:\\`).")
    st.stop()

# ---- Aufnahme wählen ----
dev = ss.dev
idx = st.selectbox("Aufnahme", list(ss.records.keys()),
                   format_func=lambda i: f"Aufnahme {i}  ({ss.records[i].duration_s/60:.0f} min, "
                                         f"Start {ss.records[i].start:%d.%m %H:%M}" if ss.records[i].start
                                         else f"Aufnahme {i}")
dec = ss.records[idx]
ana = ss.analysis[idx]

c = st.columns(4)
c[0].metric("Dauer", f"{dec.duration_s/60:.0f} min")
c[1].metric("Ø Herzfrequenz", f"{ana['hrv'].get('mean_hr', float('nan')):.0f} bpm")
c[2].metric("HF min / max", f"{ana['hrv'].get('min_hr', 0):.0f} / {ana['hrv'].get('max_hr', 0):.0f}")
c[3].metric("Auffälligkeiten", f"{len(ana['events'])}")

tab_view, tab_ana, tab_export = st.tabs(["📈 EKG ansehen", "🔬 Analyse", "💾 Export"])

# =========================================================================== #
with tab_view:
    left, right = st.columns([3, 1])
    with right:
        win = st.select_slider("Fensterbreite", [5, 10, 20, 30, 60], value=10,
                               format_func=lambda s: f"{s} s")
        if ana["events"]:
            labels = [f"{e['typ']} – {clock(dec, e['zeit_s'])}" for e in ana["events"]]
            pick = st.selectbox("Zu Auffälligkeit springen", ["—"] + labels)
            if pick != "—":
                ss.view_start = max(0.0, ana["events"][labels.index(pick)]["zeit_s"] - win / 3)
    with left:
        max_start = max(0.0, dec.duration_s - win)
        ss.view_start = st.slider("Startzeit (Minuten)", 0.0, max_start / 60,
                                  min(ss.view_start, max_start) / 60, step=0.05) * 60
        st.caption(f"Zeigt **{clock(dec, ss.view_start)}** … "
                   f"{clock(dec, ss.view_start + win)}  (10 mm/mV, 25 mm/sec)")

    fs = h.SAMPLING_RATE
    i0 = int(ss.view_start * fs)
    i1 = min(dec.n_samples, i0 + int(win * fs))
    t = np.arange(i0, i1) / fs
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        subplot_titles=[f"Ableitung {l}" for l in h.LEAD_LABELS])
    for r, lbl in enumerate(h.LEAD_LABELS):
        fig.add_trace(go.Scatter(x=t, y=dec.samples[i0:i1, r] * h.MV_PER_UNIT,
                                 mode="lines", line=dict(color="black", width=1)),
                      row=r + 1, col=1)
        fig.update_yaxes(title_text="mV", row=r + 1, col=1, zeroline=True,
                         gridcolor="rgba(255,0,0,0.2)")
    nkinfo = ana.get("nk")
    if nkinfo and nkinfo.get("rpeaks") is not None:
        rp = np.asarray(nkinfo["rpeaks"])
        beats = rp[(rp >= i0) & (rp < i1)]
    else:
        beats = np.flatnonzero(dec.qrs[i0:i1]) + i0
    if len(beats):
        fig.add_trace(go.Scatter(x=beats / fs, y=dec.samples[beats, 1] * h.MV_PER_UNIT,
                                 mode="markers", marker=dict(color="red", size=6),
                                 name="QRS"), row=2, col=1)
    fig.update_xaxes(title_text="Zeit [s]", row=3, col=1, gridcolor="rgba(255,0,0,0.2)")
    fig.update_layout(height=620, showlegend=False, margin=dict(l=50, r=20, t=40, b=40))
    st.plotly_chart(fig, width="stretch")

# =========================================================================== #
with tab_ana:
    st.subheader("Herzfrequenz-Verlauf")
    tc, hr = ana["trend"]
    if len(tc):
        base_dt = dec.start
        x = [base_dt + timedelta(seconds=float(s)) for s in tc] if base_dt else tc
        f = go.Figure(go.Scatter(x=x, y=hr, mode="lines", line=dict(color="crimson")))
        f.update_layout(height=300, yaxis_title="bpm", margin=dict(l=40, r=20, t=10, b=30))
        st.plotly_chart(f, width="stretch")

    st.subheader("HRV-Kennzahlen (technisch)")
    m = ana["hrv"]
    if m:
        cc = st.columns(4)
        cc[0].metric("Schläge", f"{m['beats']}")
        cc[1].metric("SDNN", f"{m['sdnn_ms']:.0f} ms")
        cc[2].metric("RMSSD", f"{m['rmssd_ms']:.0f} ms")
        cc[3].metric("pNN50", f"{m['pnn50_pct']:.1f} %")

    st.subheader("Erweiterte Analyse (NeuroKit2)")
    nk = ana.get("nk")
    if nk:
        qcols = st.columns(4)
        qcols[0].metric("R-Zacken (NeuroKit2)", f"{nk.get('n_rpeaks', '?')}")
        if nk.get("quality_mean") is not None:
            qcols[1].metric("Signalqualität Ø", f"{nk['quality_mean']:.2f}")
            qcols[2].metric("niedrige Qualität", f"{nk.get('quality_low_pct', 0):.0f} %")
        hv = nk.get("hrv", {})
        order = [("MeanNN", "ms"), ("SDNN", "ms"), ("RMSSD", "ms"), ("pNN50", "%"),
                 ("SD1", "ms"), ("SD2", "ms"), ("LFHF", "")]
        st.dataframe(
            [{"Kennzahl": ("LF/HF" if k == "LFHF" else k),
              "Wert": (f"{hv[k]:.1f} {u}".strip() if isinstance(hv.get(k), (int, float)) else "–")}
             for k, u in order],
            hide_index=True, width="stretch")
        st.caption("Robuste R-Zacken-Erkennung, Signalqualität und erweiterte HRV "
                   "(inkl. Frequenz-/Poincaré-Maße) via NeuroKit2 – technisch, keine Diagnose.")
    else:
        st.info("**NeuroKit2 ist nicht installiert** – es läuft die numpy-Basisanalyse. "
                "Für die erweiterte Analyse (robustere R-Zacken, Signalqualität, reichere HRV): "
                "`pip install neurokit2` – oder den GUI-Starter erneut ausführen.")

    st.subheader("Auffälligkeiten (Hinweise zur Durchsicht – keine Diagnose)")
    ev = ana["events"]
    if ev:
        st.dataframe([{"Zeit": clock(dec, e["zeit_s"]), "Typ": e["typ"], "Info": e["wert"]}
                      for e in ev], width="stretch", hide_index=True)
    else:
        st.write("Keine markanten Auffälligkeiten erkannt.")

    st.subheader("Statistik je Stunde")
    hs = ana["hourly"]
    if hs:
        st.dataframe([{"Uhrzeit": r["uhrzeit"], "Ø HF": f"{r['hf_mittel']:.0f}",
                       "min": f"{r['hf_min']:.0f}", "max": f"{r['hf_max']:.0f}",
                       "Schläge": r["schlaege"]} for r in hs],
                     width="stretch", hide_index=True)

# =========================================================================== #
with tab_export:
    st.write(f"Beim Klick werden diese drei Dateien der **Aufnahme {idx}** erzeugt und "
             "stehen anschließend zum Download bereit:")
    st.markdown(
        f"- **`record{idx}.edf`** — EDF+ (die Aufnahme; öffnet z. B. in EDFbrowser)\n"
        f"- **`record{idx}.csv`** — Rohwerte in mV je Ableitung (Zeit, I, II, III, QRS)\n"
        f"- **`bericht_record{idx}.pdf`** — mehrseitiger technischer Bericht")
    st.caption("Bei langen Aufnahmen dauert das Erzeugen einen Moment (v. a. die große CSV).")
    if st.button("📦 Download-Dateien erzeugen", type="primary"):
        with st.spinner("Erzeuge EDF+, CSV und PDF-Bericht …"):
            ss[f"dl_{idx}"] = {
                "edf": h.edf_bytes(dec, dev),
                "csv": h.csv_bytes(dec),
                "pdf": h.build_report_pdf(dec, dev, nk=ana.get("nk")),
            }
    dl = ss.get(f"dl_{idx}")
    if dl:
        d = st.columns(3)
        d[0].download_button("⬇️ EDF+ (.edf)", dl["edf"], file_name=f"record{idx}.edf",
                             mime="application/octet-stream", width="stretch")
        d[1].download_button("⬇️ CSV (.csv)", dl["csv"], file_name=f"record{idx}.csv",
                             mime="text/csv", width="stretch")
        d[2].download_button("⬇️ PDF-Bericht", dl["pdf"], file_name=f"bericht_record{idx}.pdf",
                             mime="application/pdf", width="stretch")
    else:
        st.info("Auf **Download-Dateien erzeugen** klicken – danach erscheinen die "
                "Download-Buttons.")
