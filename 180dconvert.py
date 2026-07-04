#!/usr/bin/env python3
"""180dconvert – Kommandozeile für den Heal Force Prince 180D Konverter.

    python 180dconvert.py <Eingangsordner> [Ausgangsordner] [Optionen]

Ohne Argumente startet ein geführter Modus mit Abfrage in der Konsole.
Die grafische Version (Viewer + Analyse) startet über  app.py  (Streamlit).
Die eigentliche Logik liegt in hf180d.py.

Kein Medizinprodukt – nur technische Datenaufbereitung, keine Diagnose.
"""

from __future__ import annotations

import argparse
import os
import string
import sys

from hf180d import convert, looks_like_disk, resolve_input


def _auto_find_input() -> str | None:
    """Sucht den Datenträger auf Laufwerken (Windows) bzw. Mounts (Linux)."""
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


def _ask_path(prompt: str, default: str | None = None) -> str | None:
    """Liest einen Pfad aus der Konsole (leere Eingabe -> default).

    Bewusst Text statt grafischem Dialog: ein tkinter-Fenster öffnet sich unter
    Wayland oft unsichtbar im Hintergrund und blockiert dann.
    """
    try:
        p = input(prompt).strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        return default
    return p or default


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
        if (_ask_path("Diesen verwenden? [J/n] (leer = ja): ", default="j") or "j").lower() \
                in ("n", "no", "nein"):
            base = None
    if not base:
        print("\nBitte den Ordner des Datenträgers angeben "
              "(enthält ECG_0 und README.TXT).")
        print("  Tipp: Das darf direkt das Laufwerk des Geräts sein, z. B.  E:\\")
        print("  (Pfad eintippen oder den Ordner ins Fenster ziehen, dann Enter.)")
        typed = _ask_path("Pfad: ")
        base = resolve_input(typed) if typed else None
    if not base:
        print("\nFEHLER: Kein gültiger Datenträger angegeben "
              "(es muss der Ordner mit ECG_0 und README.TXT sein).")
        _pause()
        return 2

    default_out = _default_output_dir()
    print("\nWohin sollen die Ergebnisse (EDF/CSV)?")
    out = _ask_path(f"  Zielordner (leer = {default_out}): ", default=default_out)
    try:
        rc = convert(base, out)
    except Exception as e:  # noqa: BLE001 – lesbare Meldung statt Traceback
        print(f"\nFEHLER bei der Umwandlung: {e}")
        rc = 1
    _pause()
    return rc


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return run_interactive()

    p = argparse.ArgumentParser(
        prog="180dconvert",
        description="Heal Force Prince 180D SCP-ECG -> EDF+ / CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Beispiel:\n  python 180dconvert.py E:\\ C:\\Users\\me\\Desktop\\EKG\n"
               "Ohne Argumente startet ein geführter Modus mit Ordner-Abfrage.")
    p.add_argument("input", nargs="?", help="Wechseldatenträger bzw. Ordner mit ECG_0/")
    p.add_argument("output", nargs="?", default="180D-Export",
                   help="Zielordner (Standard: ./180D-Export)")
    p.add_argument("--formats", default="edf,csv", help="edf,csv (Standard: beide)")
    p.add_argument("--no-plot", action="store_true", help="Keinen Kontroll-Plot erzeugen")
    p.add_argument("--plot-at", default=None,
                   help="Uhrzeit HH:MM:SS für den Plot-Beginn (Standard: Aufnahmebeginn)")
    args = p.parse_args(argv)

    if not args.input:
        return run_interactive()

    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    return convert(args.input, args.output, formats=formats,
                   make_plot=not args.no_plot, plot_at=args.plot_at)


if __name__ == "__main__":
    raise SystemExit(main())
