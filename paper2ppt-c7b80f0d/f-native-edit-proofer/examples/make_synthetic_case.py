#!/usr/bin/env python3
"""make_synthetic_case.py -- generate a synthetic platform-style input case.

Produces, in --out-dir:
  paper.pdf            >=4 pages, pure ASCII text + one simple figure,
                       Figure 1 / Table 1 captions, values with units,
                       a limitations sentence. All content is fictional.
  target-template.pptx python-pptx template with title/content placeholders
  data.csv             synthetic numeric series
  case.json            case_id + output_contract (platform field names)
  task.md              audience / 10 minutes / <=8 slides / template rule

Usage:
    python3 make_synthetic_case.py --out-dir ../runs/c/input
"""
import argparse
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

OUTPUT_CONTRACT = ["case_id", "status", "editable_source", "export_artifact",
                   "content_map", "compliance_checks", "exceptions"]

# ---- verbatim paper lines (deck.json quotes must match these exactly) ----
P1 = ["Synthetic Lattice Relaxation in the Fictional Perovskite",
      "SrFeO3-delta: A Reproducibility Study",
      "",
      "Synth A. Author, Fictional B. Coauthor, and Demo C. Writer",
      "Institute of Synthetic Materials (fictional affiliation)",
      "",
      "Abstract",
      "We present a fully synthetic study of lattice relaxation in the",
      "fictional perovskite SrFeO3-delta. All numbers in this paper are",
      "invented for demonstration only and must not be cited as real",
      "science. The synthetic dataset converges smoothly and illustrates",
      "how a paper-to-slides pipeline can trace every claim to a page."]

P2 = ["1. Introduction",
      "Perovskite oxides are a standard test bed for computational",
      "demonstrations. This synthetic paper exists only to exercise an",
      "academic slides pipeline with traceable evidence.",
      "",
      "2. Methods",
      "We generated a fictional energy series for k-point densities from",
      "2 to 12 using a deterministic quadratic model with synthetic noise.",
      "The synthetic total energy converges to within 1.3 meV/atom at a",
      "k-point density of 8."]

P3 = ["3. Results",
      "Figure 1 shows the synthetic convergence curve of total energy",
      "versus k-point density.",
      "",
      "Figure 1. Synthetic total energy (eV/atom) vs k-point density for",
      "the fictional perovskite SrFeO3-delta.",
      "",
      "The fictional equilibrium lattice constant is 3.905 Angstrom with",
      "a synthetic uncertainty of 0.004 Angstrom."]

P4 = ["Table 1. Synthetic lattice constants (Angstrom) for three",
      "fictional exchange-correlation functionals.",
      "",
      "PBE 3.905 | HSE 3.871 | vdW-DF 3.942 (all values fictional)",
      "",
      "4. Limitations",
      "A key limitation of this synthetic study is that all data are",
      "fictional and generated for demonstration only.",
      "No experimental validation was performed, because the material",
      "itself is fictional."]

KS = [2, 4, 6, 8, 10, 12]
ENERGIES = [-521.40, -524.10, -524.86, -525.0013 - 0.0, -525.02, -525.03]
TABLE1 = [["PBE", "3.905", "-525.00"],
          ["HSE", "3.871", "-527.42"],
          ["vdW-DF", "3.942", "-524.61"]]


def make_paper(path):
    with PdfPages(path) as pdf:
        for i, lines in enumerate((P1, P2, P3, P4), start=1):
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(0.08, 0.96, "\n".join(lines), va="top", ha="left",
                     fontsize=11, family="monospace")
            fig.text(0.5, 0.02, "synthetic page %d (fictional)" % i,
                     ha="center", fontsize=9)
            if i == 3:  # simple figure on the results page
                ax = fig.add_axes([0.15, 0.38, 0.7, 0.28])
                ax.plot(KS, ENERGIES, "o-", color="#1f5fb4")
                ax.set_xlabel("k-point density")
                ax.set_ylabel("total energy (eV/atom)")
                ax.set_title("Figure 1 (synthetic)")
                ax.grid(alpha=0.3)
            pdf.savefig(fig)
            plt.close(fig)


def make_template(path):
    from pptx import Presentation
    prs = Presentation()  # default theme: Calibri/Calibri Light placeholders
    prs.save(path)


def make_csv(path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["kpoint_density", "total_energy_eV_per_atom"])
        for k, e in zip(KS, ENERGIES):
            w.writerow([k, "%.4f" % e])


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic input case "
                                     "(fictional content only).")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    make_paper(os.path.join(args.out_dir, "paper.pdf"))
    make_template(os.path.join(args.out_dir, "target-template.pptx"))
    make_csv(os.path.join(args.out_dir, "data.csv"))
    with open(os.path.join(args.out_dir, "case.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"case_id": "synthetic-c-001",
                   "output_contract": OUTPUT_CONTRACT}, fh,
                  ensure_ascii=False, indent=2)
    with open(os.path.join(args.out_dir, "task.md"), "w",
              encoding="utf-8") as fh:
        fh.write("# Synthetic task (fictional)\n\n"
                 "- Audience: academic committee (synthetic demo)\n"
                 "- Duration: 10 minutes\n"
                 "- Slide limit: <= 8 slides\n"
                 "- Template: use /input/target-template.pptx theme\n"
                 "- Requirement: natively editable pptx, real tables, "
                 "traceable quotes, speaker notes.\n")
    print("make_synthetic_case: wrote paper.pdf, target-template.pptx, "
          "data.csv, case.json, task.md -> %s" % args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
