#!/usr/bin/env python3
"""make_synthetic.py — 生成合成长文（4 章节、20+ 段、题注与公式）。确定性输出。"""
import argparse

SENTS = [
    "The reactor was operated at {T} °C for {N} hours under a constant flow of {F} mL/min.",
    "Conversion reached {P}% after {N} cycles, and the selectivity remained above {Q}%.",
    "We attribute the decline to surface fouling, which was confirmed by SEM imaging.",
    "The catalyst loading was {W} mg per gram of support, following the protocol of [1].",
    "Figure {FIG} summarizes the pressure drop across the bed as a function of time.",
    "No significant deactivation was observed below {T} °C (p = {p}).",
    "The apparent activation energy is {E} kJ/mol, consistent with earlier reports [2, 3].",
    "Table {FIG} lists the textural properties of the three prepared samples.",
    "Error bars denote one standard deviation from three independent runs (n = 3).",
    "The model reproduces the data with a root-mean-square error of {R}.",
    "We note that the observed trend may reflect mass-transfer limitations at high flow.",
    "Blank experiments showed no measurable conversion under identical conditions.",
    "The pore size distribution was centered near {D} nm for the calcined sample.",
    "Reproducibility across batches was within ±{P}%.",
    "Long-term stability tests extended to {N} hours without measurable loss.",
]

SECTIONS = [("Introduction", 3), ("Methods", 5), ("Results and Discussion", 9), ("Conclusion", 3)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    L, k = [], 0
    L.append("Continuous-Flow Catalytic Upgrading of Bio-Oils: A Synthetic Long-Form Example")
    L.append("")
    fig_no = 1
    for title, n in SECTIONS:
        L.append(title)
        L.append("")
        for i in range(n):
            s = SENTS[k % len(SENTS)].format(T=280 + 10 * (k % 5), N=6 * (k % 8 + 1),
                                             F=2.5 * (k % 4 + 1), P=3 * (k % 7 + 2),
                                             Q=88 + (k % 5), W=25 + 5 * (k % 4),
                                             F2=fig_no, p=f"0.0{k % 9 + 1}",
                                             E=45 + 3 * (k % 6), R=f"0.{k % 9 + 1}{k % 9}",
                                             D=8 + (k % 6), FIG=fig_no)
            L.append(s)
            L.append("")
            k += 1
            if (title, i) == ("Results and Discussion", 4):
                L.append(f"Figure {fig_no}. Pressure drop and conversion as functions of time on stream.")
                L.append("")
                L.append("(1) X = 1 − exp(−k·τ)")
                L.append("")
                fig_no += 1
    L.append(f"Table 1. Textural properties of the synthesized catalysts (synthetic data).")
    L.append("")
    open(a.out, "w", encoding="utf-8").write("\n".join(L))
    print(f"synthetic long document -> {a.out}")

if __name__ == "__main__":
    main()
