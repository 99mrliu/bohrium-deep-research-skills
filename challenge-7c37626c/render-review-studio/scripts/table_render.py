#!/usr/bin/env python3
"""Render the variable table (work/variables.json) to a paginated PNG.

Columns are the union of row keys in declaration order. Stdlib + matplotlib.
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output/render")
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = json.loads((work / "variables.json").read_text(encoding="utf-8")).get("rows", [])
    if not rows:
        print("no variable rows; table skipped")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib unavailable; table skipped")
        return

    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    per_page = 14
    paths = []
    for start in range(0, len(rows), per_page):
        chunk = rows[start:start + per_page]
        fig, ax = plt.subplots(figsize=(11, 0.55 * len(chunk) + 1.2))
        ax.axis("off")
        table = ax.table(
            cellText=[[str(r.get(c, ""))[:60] for c in cols] for r in chunk],
            colLabels=cols, loc="center", cellLoc="left")
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.4)
        target = out / ("variables_p%d.png" % (start // per_page + 1))
        fig.tight_layout()
        fig.savefig(target, dpi=140, facecolor="white")
        plt.close(fig)
        paths.append({"png": str(target), "bytes": target.stat().st_size,
                      "rows": len(chunk)})
    (work / "table_report.json").write_text(
        json.dumps({"pages": paths, "total_rows": len(rows)},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print("variable table: %d rows, %d pages -> %s"
          % (len(rows), len(paths), work / "table_report.json"))


if __name__ == "__main__":
    main()
