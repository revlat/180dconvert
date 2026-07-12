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

# Druckansicht (Strg+P): Bedienelemente & Streamlit-Chrome ausblenden, volle Breite,
# Farben mitdrucken, nicht mitten in Diagrammen/Tabellen umbrechen. Wirkt NUR beim Drucken.
st.markdown("""
<style>
@media print {
  [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
  [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stStatusWidget"],
  [data-baseweb="tab-list"] { display: none !important; }
  [data-testid="stSlider"], [data-testid="stSelectbox"], [data-testid="stSelectSlider"],
  [data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stToggle"],
  [data-testid="stTextInput"], [data-testid="stFileUploader"] { display: none !important; }
  [data-testid="stAppViewContainer"], [data-testid="stMain"], .block-container {
    max-width: 100% !important; width: 100% !important; padding: 0.4rem !important; }
  html, body { background: #fff !important; }
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  [data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stTable"],
  [data-testid="stMetric"], [data-testid="stAlert"], .stAlert {
    break-inside: avoid; page-break-inside: avoid; }
  @page { margin: 12mm; }
}
/* Bildschirm: Standard-Padding oben (6rem) ist zu viel Leerraum */
[data-testid="stMainBlockContainer"], .stMainBlockContainer, .block-container {
  padding-top: 1rem !important; }
/* Sidebar-Einklapp-Pfeil immer zeigen (Standard: nur bei Hover) */
[data-testid="stSidebarCollapseButton"] {
  display: block !important; visibility: visible !important; opacity: 1 !important; }
[data-testid="stSidebarCollapseButton"] button { visibility: visible !important; }
</style>
""", unsafe_allow_html=True)

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

tab_view, tab_ana, tab_export = st.tabs(["📈 EKG ansehen", "🔬 Analyse", "💾 Export (alles)"])

# =========================================================================== #
with tab_view:
    fs = h.SAMPLING_RATE
    ss.setdefault("start_min", 0.0)
    ss.setdefault("event_pick", "—")

    ev_list = ana["events"]
    labels = [f"{e['nr']}: {clock(dec, e['zeit_s'])} – {e['typ']}" for e in ev_list]
    label_by_nr = {e["nr"]: labels[i] for i, e in enumerate(ev_list)}
    event_by_label = {labels[i]: ev_list[i] for i in range(len(ev_list))}
    if ss.event_pick not in (["—"] + labels):     # z. B. nach Aufnahme-Wechsel
        ss.event_pick = "—"

    left, right = st.columns([3, 2])
    with right:
        win = st.select_slider("Fensterbreite", list(range(5, 125, 5)), value=10,
                               format_func=lambda s: f"{s} s")
        max_min = max(0.0, (dec.duration_s - win) / 60.0)

        # --- Klick im Navigator (aus vorherigem Lauf) VOR der Selectbox auswerten ---
        nav_pts = ((ss.get("nav") or {}).get("selection", {}) or {}).get("points", [])
        nav_x = nav_pts[0].get("x") if nav_pts else None
        nav_nr = None
        for p in nav_pts:                          # Marker tragen customdata [nr, typ]
            if p.get("customdata"):
                nav_nr, nav_x = p["customdata"][0], p.get("x")
                break
        if nav_nr is None and nav_x is not None and ev_list:   # Fallback: exakt auf Markerposition?
            ex_min = np.array([e["zeit_s"] for e in ev_list]) / 60.0
            j = int(np.argmin(np.abs(ex_min - nav_x)))
            if abs(ex_min[j] - nav_x) < 1e-6:
                nav_nr = ev_list[j]["nr"]
        if nav_x is not None and nav_x != ss.get("_nav_applied"):
            ss._nav_applied = nav_x
            if nav_nr is not None and nav_nr in label_by_nr:
                ss.event_pick = label_by_nr[nav_nr]            # Marker -> Auffälligkeit wählen
            else:                                              # freie Stelle -> Auswahl aufheben
                ss.event_pick = "—"
                ss.start_min = float(min(max(0.0, nav_x - (win / 3) / 60.0), max_min))

        if labels:
            options = ["—"] + labels

            def _step_event(delta, opts):      # Callback: läuft VOR dem Rerun -> disabled stimmt sofort
                cur = opts.index(ss.event_pick) if ss.event_pick in opts else 0
                ss.event_pick = opts[max(0, min(cur + delta, len(opts) - 1))]

            cur_opt = options.index(ss.event_pick) if ss.event_pick in options else 0
            row = st.columns([6, 1, 1], vertical_alignment="bottom")
            row[0].selectbox("Zu Auffälligkeit (Nr.) springen", options,
                             key="event_pick", width="stretch")
            row[1].button("‹", key="ev_prev", disabled=(cur_opt <= 0),
                          width="stretch", on_click=_step_event, args=(-1, options))
            row[2].button("›", key="ev_next", disabled=(cur_opt >= len(options) - 1),
                          width="stretch", on_click=_step_event, args=(1, options))

    pick = ss.event_pick if labels else "—"
    picked_event = event_by_label.get(pick)

    # Sprung nur bei NEUER Auswahl -> der Startzeit-Slider bleibt danach frei bedienbar.
    if pick != ss.get("_pick_applied"):
        ss._pick_applied = pick
        if picked_event is not None:
            ss.start_min = float(min(max(0.0, (picked_event["zeit_s"] - win / 3) / 60.0), max_min))
    ss.start_min = float(min(ss.start_min, max_min))   # bei Fensterbreite-Wechsel clampen

    with left:
        if max_min > 0:
            st.slider("Startzeit (Minuten)", 0.0, max_min, key="start_min", step=0.05)
        else:
            ss.start_min = 0.0
        ss.view_start = ss.start_min * 60.0
        st.caption(f"Zeigt **{clock(dec, ss.view_start)}** … "
                   f"{clock(dec, ss.view_start + win)}  (10 mm/mV, 25 mm/sec)")

        # Export des aktuell gezeigten Ausschnitts: EDF+ und druckfertiges PDF nebeneinander
        i0 = int(ss.view_start * fs)
        i1 = min(dec.n_samples, i0 + int(win * fs))
        seg_id = (idx, i0, i1)
        bcol = st.columns(2)
        with bcol[0]:                                  # EDF+ des Ausschnitts (verlustfrei)
            if st.button(f"🧩 Ausschnitt ({win} s) als EDF+", key="prep_seg"):
                try:
                    ss["seg_edf"] = {"id": seg_id, "bytes": h.edf_segment_bytes(dec, dev, i0, i1)}
                except Exception as ex:                # z. B. edfio fehlt / zu kurz
                    ss["seg_edf"] = {"id": seg_id, "error": str(ex)}
            seg = ss.get("seg_edf")
            if seg and seg.get("id") == seg_id and seg.get("bytes"):
                fn = f"record{idx}_{int(round(ss.view_start))}-{int(round(ss.view_start + win))}s.edf"
                st.download_button("⬇️ EDF+ laden", seg["bytes"], file_name=fn,
                                   mime="application/octet-stream", key="dl_seg")
            elif seg and seg.get("id") == seg_id and seg.get("error"):
                st.error(f"EDF+ nicht möglich: {seg['error']}")
        with bcol[1]:                                  # druckfertiges PDF genau dieser Ansicht
            if st.button("🖨️ Ansicht als PDF", key="prep_viewpdf"):
                try:
                    ss["view_pdf"] = {"id": seg_id,
                                      "bytes": h.view_pdf_bytes(dec, dev, i0, i1, nk=ana.get("nk"))}
                except Exception as ex:
                    ss["view_pdf"] = {"id": seg_id, "error": str(ex)}
            vp = ss.get("view_pdf")
            if vp and vp.get("id") == seg_id and vp.get("bytes"):
                fnp = f"ansicht_record{idx}_{int(round(ss.view_start))}-{int(round(ss.view_start + win))}s.pdf"
                st.download_button("⬇️ PDF laden", vp["bytes"], file_name=fnp,
                                   mime="application/pdf", key="dl_viewpdf")
            elif vp and vp.get("id") == seg_id and vp.get("error"):
                st.error(f"PDF nicht möglich: {vp['error']}")

    if picked_event is not None:
        e = picked_event
        dauer = f"  ·  Dauer {e['dauer_s']:.0f} s" if e.get("dauer_s") else ""
        box = (f"**Nr. {e['nr']} – {e['typ']}**  ·  {clock(dec, e['zeit_s'])}{dauer}\n\n"
               f"{e.get('detail', e['wert'])}")
        (st.warning if e.get("unsicher") else st.info)(box)

    # ---- Haupt-EKG: aktuelles Fenster in VOLLER Auflösung + Puls des Fensters ----
    t = np.arange(i0, i1) / fs

    # Schlagquelle (NeuroKit-R-Zacken bevorzugt, sonst Geräte-Marker) – global,
    # damit der Puls auch am Fensterrand nahtlos anschließt.
    nkinfo = ana.get("nk")
    if nkinfo and nkinfo.get("rpeaks") is not None:
        all_beats = np.asarray(nkinfo["rpeaks"])
    else:
        all_beats = np.flatnonzero(dec.qrs)
    beats = all_beats[(all_beats >= i0) & (all_beats < i1)]

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.045,
                        row_heights=[0.27, 0.27, 0.27, 0.19],
                        subplot_titles=[f"Ableitung {l}" for l in h.LEAD_LABELS]
                        + [""])                       # Puls-Reihe: bpm-Achse reicht als Beschriftung
    fig.update_annotations(font_size=12)              # "Ableitung X"-Titel dezenter
    for r, lbl in enumerate(h.LEAD_LABELS):
        fig.add_trace(go.Scatter(x=t, y=dec.samples[i0:i1, r] * h.MV_PER_UNIT,
                                 mode="lines", line=dict(color="black", width=1)),
                      row=r + 1, col=1)
        fig.update_yaxes(title_text="mV", row=r + 1, col=1, zeroline=True,
                         gridcolor="rgba(255,0,0,0.2)")
    if len(beats):
        fig.add_trace(go.Scatter(x=beats / fs, y=dec.samples[beats, 1] * h.MV_PER_UNIT,
                                 mode="markers", marker=dict(color="red", size=6),
                                 name="QRS"), row=2, col=1)

    # Pulsverlauf: Momentan-Herzfrequenz (60/RR) an jedem Schlag im sichtbaren Fenster.
    bt = all_beats / fs
    if len(bt) >= 2:
        rr = np.diff(bt)
        hr_t = bt[1:]
        hr_v = np.where(rr > 0, 60.0 / rr, np.nan)
        margin = win * 0.5                        # Randpunkte mitnehmen -> Linie bis zum Rand
        sel = ((hr_t >= t[0] - margin) & (hr_t <= (t[-1] if len(t) else 0) + margin)
               & (hr_v > 25) & (hr_v < 250))
        if np.any(sel):
            fig.add_trace(go.Scatter(x=hr_t[sel], y=hr_v[sel], mode="lines+markers",
                                     line=dict(color="crimson", width=1.5),
                                     marker=dict(size=5, color="crimson"),
                                     name="Puls",
                                     hovertemplate="%{x:.1f} s · %{y:.0f} bpm<extra></extra>"),
                          row=4, col=1)
    fig.update_yaxes(title_text="bpm", row=4, col=1, gridcolor="rgba(255,0,0,0.2)")
    fig.update_xaxes(title_text="Zeit [s]", row=4, col=1, gridcolor="rgba(255,0,0,0.2)")
    if len(t):                                     # x-Bereich exakt aufs Fenster begrenzen
        fig.update_xaxes(range=[t[0], t[-1]])
    fig.update_layout(height=780, showlegend=False, margin=dict(l=50, r=20, t=40, b=40))
    st.plotly_chart(fig, width="stretch")

    # ---- Navigator: Puls der GANZEN Aufnahme, klickbar (EKG bleibt oben voll aufgelöst) ----
    tc, hrtr = ana["trend"]                        # 30-s-Mittel, günstig für die Übersicht
    if len(tc):
        nav = go.Figure(go.Scatter(
            x=tc / 60.0, y=hrtr, mode="lines+markers",
            line=dict(color="crimson", width=1), marker=dict(size=3, color="crimson"),
            name="Puls", hovertemplate="%{x:.1f} min · %{y:.0f} bpm<extra></extra>"))
        nav.add_vrect(x0=ss.view_start / 60.0, x1=(ss.view_start + win) / 60.0,
                      fillcolor="steelblue", opacity=0.25, line_width=0)

        # Auffälligkeiten markieren: dünne Führungslinie + nummerierter Punkt im Band darüber
        ev = ana["events"]
        if ev:
            ymin, ymax = float(np.min(hrtr)), float(np.max(hrtr))
            span = max(1.0, ymax - ymin)
            top = ymax + span * 0.18               # Markerband oberhalb der Pulskurve

            xs, ys = [], []                        # 1) senkrechte Führungslinien (nicht klickbar)
            for e in ev:
                x = e["zeit_s"] / 60.0
                xs += [x, x, None]
                ys += [ymin, top, None]
            nav.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                     line=dict(color="rgba(255,127,14,0.45)", width=1),
                                     hoverinfo="skip", showlegend=False, name="Marker"))

            ex = np.array([e["zeit_s"] for e in ev], dtype=float) / 60.0
            colors = ["#9aa0a6" if e.get("unsicher") else "#ff7f0e" for e in ev]
            cd = [[e["nr"], e["typ"]] for e in ev]
            show_text = len(ev) <= 40              # bei sehr vielen nur Punkte (sonst Textsalat)
            nav.add_trace(go.Scatter(     # 2) nummerierte Punkte oben (klickbar -> EKG springt hin)
                x=ex, y=np.full(len(ev), top), mode="markers+text" if show_text else "markers",
                text=[str(e["nr"]) for e in ev] if show_text else None,
                textposition="top center", textfont=dict(size=9, color="#333"),
                marker=dict(symbol="circle", size=9, color=colors,
                            line=dict(color="black", width=0.6)),
                customdata=cd, name="Auffälligkeit",
                hovertemplate="Nr. %{customdata[0]}: %{customdata[1]}<br>"
                              "%{x:.1f} min<extra></extra>"))
            nav.update_yaxes(range=[ymin - span * 0.12, top + span * 0.22])

        nav.update_layout(
            height=210, margin=dict(l=50, r=20, t=30, b=36),
            title=dict(text="Puls – ganze Aufnahme (Punkt/Nummer anklicken → EKG springt dorthin; "
                            "orange = Auffälligkeit, blau = aktuelles Fenster)",
                       font=dict(size=13)),
            xaxis_title="Zeit [min]", yaxis_title="bpm",
            showlegend=False, clickmode="event+select")
        st.plotly_chart(nav, key="nav", on_select="rerun", selection_mode="points")
    else:
        st.caption("Kein Pulsverlauf für die Übersicht verfügbar (zu wenige Schläge erkannt).")

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

    st.subheader("HRV-Grafiken (technisch)")
    _, rr_all = h.rr_series(dec)
    rr_ms = rr_all * 1000.0
    if len(rr_ms) > 3:
        gx, gy = rr_ms[:-1], rr_ms[1:]                    # aufeinanderfolgende RR-Paare
        pm = (gx > 300) & (gx < 2000) & (gy > 300) & (gy < 2000)   # nur physiologische Paare
        rr_ok = rr_ms[(rr_ms > 300) & (rr_ms < 2000)]
        g1, g2 = st.columns(2)
        pc = go.Figure(go.Scattergl(x=gx[pm], y=gy[pm], mode="markers",
                                    marker=dict(size=3, color="purple", opacity=0.35)))
        if np.any(pm):
            lo, hi = float(gx[pm].min()), float(gx[pm].max())
            pc.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines",
                                    line=dict(color="gray", dash="dot", width=1)))
        pc.update_layout(height=340, showlegend=False, title="Poincaré (RRₙ ↔ RRₙ₊₁)",
                         xaxis_title="RRₙ [ms]", yaxis_title="RRₙ₊₁ [ms]",
                         margin=dict(l=55, r=20, t=40, b=45))
        g1.plotly_chart(pc, width="stretch")
        hh = go.Figure(go.Histogram(x=rr_ok, nbinsx=50, marker_color="teal"))
        hh.update_layout(height=340, showlegend=False, title="RR-Intervalle (Verteilung)",
                         xaxis_title="RR [ms]", yaxis_title="Anzahl",
                         margin=dict(l=55, r=20, t=40, b=45))
        g2.plotly_chart(hh, width="stretch")
        st.caption("Poincaré: Schlag-zu-Schlag-Streuung (Breite ≈ SD1, Länge ≈ SD2). "
                   "Histogramm: Verteilung der Schlagabstände. Technisch, keine Diagnose.")
    else:
        st.info("Zu wenige Schläge für HRV-Grafiken.")

    st.subheader("Erweiterte Analyse (NeuroKit2)")
    nk = ana.get("nk")
    if nk:
        qcols = st.columns(4)
        qcols[0].metric("R-Zacken (NeuroKit2)", f"{nk.get('n_rpeaks', '?')}")
        if nk.get("quality_mean") is not None:
            qcols[1].metric("Signalqualität Ø", f"{nk['quality_mean']:.2f}")
            qcols[2].metric("niedrige Qualität", f"{nk.get('quality_low_pct', 0):.0f} %")
        hv = nk.get("hrv", {})
        # (Schlüssel, Anzeigename, Einheit); SDANN/SDNNI/HTI brauchen längere Aufnahmen.
        order = [("MeanNN", "MeanNN", "ms"), ("MedianNN", "MedianNN", "ms"),
                 ("SDNN", "SDNN", "ms"), ("SDANN", "SDANN", "ms"), ("SDNNI", "SDNNI", "ms"),
                 ("RMSSD", "RMSSD", "ms"), ("pNN50", "pNN50", "%"), ("pNN20", "pNN20", "%"),
                 ("HTI", "HTI (Dreiecksindex)", ""),
                 ("SD1", "SD1", "ms"), ("SD2", "SD2", "ms"), ("LFHF", "LF/HF", "")]
        st.dataframe(
            [{"Kennzahl": name,
              "Wert": (f"{hv[k]:.1f} {u}".strip() if isinstance(hv.get(k), (int, float)) else "–")}
             for k, name, u in order],
            hide_index=True, width="stretch")
        st.caption("Robuste R-Zacken-Erkennung, Signalqualität und erweiterte HRV "
                   "(Zeit-/Frequenz-/Poincaré-Maße) via NeuroKit2 – technisch, keine Diagnose. "
                   "SDANN, SDNNI und HTI sind für längere Aufnahmen gedacht und bleiben bei "
                   "kurzen Aufzeichnungen leer („–“).")
    else:
        st.info("**NeuroKit2 ist nicht installiert** – es läuft die numpy-Basisanalyse. "
                "Für die erweiterte Analyse (robustere R-Zacken, Signalqualität, reichere HRV): "
                "`pip install neurokit2` – oder den GUI-Starter erneut ausführen.")

    st.subheader("Auffälligkeiten (Hinweise zur Durchsicht – keine Diagnose)")
    st.caption("Die **Nr.** ist dieselbe wie im Auswahlmenü „Zu Auffälligkeit springen“ "
               "im Tab „EKG ansehen“.")
    ev = ana["events"]
    if ev:
        st.dataframe(
            [{"Nr.": e["nr"], "Zeit": clock(dec, e["zeit_s"]), "Typ": e["typ"],
              "Dauer": (f"{e['dauer_s']:.0f} s" if e.get("dauer_s") else "–"),
              "Wie & warum erkannt / Besonderheiten": e.get("detail", e["wert"])}
             for e in ev],
            width="stretch", hide_index=True,
            column_config={"Wie & warum erkannt / Besonderheiten": st.column_config.TextColumn(width="large")})
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
