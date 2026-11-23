#!/usr/bin/env python3
"""Strict mathtext rendering of formula transcriptions to PNG.

Every entry in work/formulas.json is rendered with matplotlib mathtext.
Constructs the engine cannot typeset are reported as `unrenderable` with the
engine's error message — never silently dropped. When matplotlib is absent,
all targets are reported `renderer_unavailable` and the run degrades instead
of pretending. Stdlib + matplotlib.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output/render")
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    formulas = json.loads((work / "formulas.json").read_text(encoding="utf-8")).get("formulas", [])
    report = {"rendered": [], "unrenderable": [], "renderer": "matplotlib-mathtext"}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        report["renderer"] = "unavailable"
        report["unrenderable"] = [
            {"id": f.get("id"), "reason": "renderer_unavailable: matplotlib not installed"}
            for f in formulas]
        (work / "render_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("matplotlib unavailable; %d targets degraded" % len(formulas))
        return

    for f in formulas:
        fid, latex = f.get("id", "unnamed"), f.get("latex", "")
        try:
            fig = plt.figure(figsize=(6, 1.2))
            fig.text(0.5, 0.5, "$%s$" % latex, ha="center", va="center", fontsize=16)
            target = out / ("formula_%s.png" % fid)
            fig.savefig(target, dpi=150, bbox_inches="tight", transparent=False,
                        facecolor="white")
            plt.close(fig)
            report["rendered"].append({"id": fid, "png": str(target),
                                       "bytes": target.stat().st_size,
                                       "source": f.get("source")})
        except Exception as exc:
            report["unrenderable"].append(
                {"id": fid, "reason": "%s: %s" % (type(exc).__name__, str(exc)[:200]),
                 "latex": latex})
    (work / "render_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("rendered %d, unrenderable %d -> %s"
          % (len(report["rendered"]), len(report["unrenderable"]),
             work / "render_report.json"))


if __name__ == "__main__":
    main()
