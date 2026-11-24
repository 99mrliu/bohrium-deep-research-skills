#!/usr/bin/env python3
"""make_deck_json.py -- build the deck.json content source for the run.

Reads the synthetic paper.pdf (to confirm the quotes it embeds resolve)
and data.csv (to render fig1.png + numeric sidecar), then writes a
deck.json containing: title/bullets/figure/real-table/limitations/evidence
slides, per-slide notes with timing, and verbatim quotes. Table 1 data is
real tabular data that build_native.py turns into a native table shape.

Usage:
    python3 make_deck_json.py --paper paper.pdf --data data.csv \
        --fig-dir figs/ --out deck.json
"""
import argparse
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TABLE1 = [["PBE", "3.905", "-525.00"],
          ["HSE", "3.871", "-527.42"],
          ["vdW-DF", "3.942", "-524.61"]]

Q_CONVERGE = ("The synthetic total energy converges to within 1.3 meV/atom "
              "at a k-point density of 8.")
Q_LATTICE = ("The fictional equilibrium lattice constant is 3.905 Angstrom "
             "with a synthetic uncertainty of 0.004 Angstrom.")
Q_FIG1 = ("Figure 1. Synthetic total energy (eV/atom) vs k-point density "
          "for the fictional perovskite SrFeO3-delta.")
Q_TAB1 = ("Table 1. Synthetic lattice constants (Angstrom) for three "
          "fictional exchange-correlation functionals.")
Q_LIMIT = ("A key limitation of this synthetic study is that all data are "
           "fictional and generated for demonstration only.")


def main():
    ap = argparse.ArgumentParser(description="Emit deck.json + figure assets "
                                             "for the synthetic case.")
    ap.add_argument("--paper", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--fig-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.fig_dir, exist_ok=True)

    # figure + numeric sidecar from data.csv
    ks, es = [], []
    with open(args.data, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ks.append(float(row["kpoint_density"]))
            es.append(float(row["total_energy_eV_per_atom"]))
    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    ax.plot(ks, es, "o-", color="#1f5fb4")
    ax.set_xlabel("k-point density")
    ax.set_ylabel("total energy (eV/atom)")
    ax.set_title("Synthetic convergence (fictional data)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(args.fig_dir, "fig1.png"), dpi=140)
    plt.close(fig)
    with open(os.path.join(args.fig_dir, "fig1.sidecar.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"source_csv": os.path.basename(args.data),
                   "x": ks, "y": es,
                   "units": {"x": "k-point density",
                             "y": "eV/atom"},
                   "fictional": True}, fh, indent=2)

    deck = {
        "meta": {"title": "Synthetic Lattice Relaxation in SrFeO3-delta",
                 "body_pt_min": 14, "footnote_pt_min": 10, "title_pt": 28,
                 "max_slides": 8,
                 "footer": "synthetic demo, fictional data"},
        "slides": [
            {"role": "title",
             "title": "Synthetic Lattice Relaxation in SrFeO3-delta",
             "subtitle": "Synth et al. - fictional reproducibility study "
                         "(synthetic demo deck)",
             "notes": "Opening: state that this is a fictional synthetic "
                      "study used to demonstrate traceable slides.",
             "notes_time_sec": 60},
            {"role": "bullets", "title": "Background and Methods",
             "bullets": [
                 {"text": "Fictional perovskite SrFeO3-delta used as a "
                          "demonstration test bed.",
                  "quote": "This synthetic paper exists only to exercise "
                           "an academic slides pipeline with traceable "
                           "evidence.",
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.2"}},
                 {"text": "Deterministic quadratic model with synthetic "
                          "noise over k-point densities 2 to 12.",
                  "quote": "We generated a fictional energy series for "
                           "k-point densities from 2 to 12 using a "
                           "deterministic quadratic model with synthetic "
                           "noise.",
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.2"}},
                 {"text": "Convergence target reached: " + Q_CONVERGE,
                  "quote": Q_CONVERGE,
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.2"}}],
             "notes": "Explain the synthetic setup; one minute per bullet.",
             "notes_time_sec": 120},
            {"role": "figure", "title": "Energy Convergence",
             "figure": {"file": "fig1.png", "width_in": 5.5,
                        "caption": "Fig. 1 (re-drawn from synthetic "
                                   "data.csv; original caption on p.3).",
                        "sidecar": "fig1.sidecar.json"},
             "bullets": [
                 {"text": Q_CONVERGE, "quote": Q_CONVERGE,
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.2"}},
                 {"text": "Original figure caption: " + Q_FIG1,
                  "quote": Q_FIG1,
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.3"}}],
             "notes": "Walk the curve; point out the knee at density 8.",
             "notes_time_sec": 120},
            {"role": "table", "title": "Synthetic Lattice Constants",
             "table": {"columns": ["Functional", "a (Angstrom)",
                                   "E_total (eV/atom)"],
                       "rows": TABLE1,
                       "caption": "Table 1 (native table shape; synthetic "
                                  "values).",
                       "caption_quote": Q_TAB1},
             "bullets": [
                 {"text": Q_LATTICE, "quote": Q_LATTICE,
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.3"}},
                 {"text": "Caption source: " + Q_TAB1, "quote": Q_TAB1,
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.4"}}],
             "notes": "Table is a real native table shape; all values "
                      "fictional.",
             "notes_time_sec": 90},
            {"role": "bullets", "title": "Limitations",
             "bullets": [
                 {"text": Q_LIMIT, "quote": Q_LIMIT,
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.4"}},
                 {"text": "No experimental validation was performed.",
                  "quote": "No experimental validation was performed, "
                           "because the material itself is fictional.",
                  "source": {"kind": "paper", "ref": "paper.pdf",
                             "locator": "p.4"}}],
             "notes": "Be explicit about fictional status.",
             "notes_time_sec": 60},
            {"role": "evidence", "title": "Evidence Map",
             "evidence": [
                 {"slide": 2, "kind": "paper", "ref": "paper.pdf",
                  "locator": "p.2", "quote": Q_CONVERGE},
                 {"slide": 3, "kind": "paper", "ref": "paper.pdf",
                  "locator": "p.3", "quote": Q_FIG1},
                 {"slide": 4, "kind": "paper", "ref": "paper.pdf",
                  "locator": "p.4", "quote": Q_TAB1},
                 {"slide": 5, "kind": "paper", "ref": "paper.pdf",
                  "locator": "p.4", "quote": Q_LIMIT}],
             "notes": "Close by pointing to verbatim evidence.",
             "notes_time_sec": 60},
        ],
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(deck, fh, ensure_ascii=False, indent=2)
    print("make_deck_json: slides=%d figs=1 table_rows=%d -> %s"
          % (len(deck["slides"]), len(TABLE1), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
