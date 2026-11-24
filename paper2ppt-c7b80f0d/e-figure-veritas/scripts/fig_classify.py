#!/usr/bin/env python3
"""fig_classify.py — 种类门禁：schematic / data-figure / table-image / unknown。

规则（按优先级）：
  1. caption 命中 schematic|diagram|illustration|overview|workflow → schematic (0.9)
  2. manifest 中 tables 段 → table-image (0.95)
  3. caption 命中 measured|data|curve|spectrum|plot|response|result|distribution|
     histogram|intensity|profile → data-figure (0.8)
  4. 抽取方式为 embedded-bitmap 且无关键词 → data-figure (0.5，低置信)
  5. 其余 → unknown：必须由 Agent 人工裁决，本脚本在报告中留出 adjudication 记录位。

同时把裁决后的 kind 回写 manifest（幂等），供 fig_binding_lint.py 使用。
退出码：0 正常（unknown 不视为错误，只要求留记录）；2 输入错误。
"""
import argparse
import json
import os
import re
import sys

SCHEMATIC_RE = re.compile(
    r"\b(schematic|diagram|illustration|overview|workflow)\b", re.I)
DATA_RE = re.compile(
    r"\b(measured|data|curve|spectrum|spectra|plot|response|results?|distribution|"
    r"histogram|intensity|profile)\b", re.I)

KINDS = ("schematic", "data-figure", "table-image", "unknown")


def classify_figure(fig):
    caption = fig.get("caption", "") or ""
    reasons = []
    m = SCHEMATIC_RE.search(caption)
    if m:
        reasons.append(f"caption keyword '{m.group(1)}' indicates schematic")
        return "schematic", 0.9, reasons
    m = DATA_RE.search(caption)
    if m:
        reasons.append(f"caption keyword '{m.group(1)}' indicates measured data")
        return "data-figure", 0.8, reasons
    if fig.get("extraction") == "embedded-bitmap":
        reasons.append("embedded raster bitmap present; no schematic keyword")
        return "data-figure", 0.5, reasons
    reasons.append("no decisive keyword and no embedded bitmap; needs adjudication")
    return "unknown", 0.0, reasons


def main():
    ap = argparse.ArgumentParser(
        description="Classify manifest figures into schematic/data-figure/table-image/unknown.")
    ap.add_argument("manifest", help="figure_manifest.json from fig_harvest.py")
    ap.add_argument("--report", default="classify_report.json")
    args = ap.parse_args()

    if not os.path.isfile(args.manifest):
        sys.stderr.write(f"error: manifest not found: {args.manifest}\n")
        return 2
    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)

    entries = []
    for fig in manifest.get("figures", []):
        kind, conf, reasons = classify_figure(fig)
        fig["kind"] = kind  # 回写 manifest（幂等）
        entries.append({
            "id": fig["id"],
            "page": fig.get("page"),
            "kind": kind,
            "confidence": conf,
            "reasons": reasons,
            "adjudication": ("REQUIRED: unknown kind must be decided by the agent "
                             "and recorded in change_records"
                             if kind == "unknown" else "not-needed"),
        })
    for tab in manifest.get("tables", []):
        tab["kind"] = "table-image"
        entries.append({
            "id": tab["id"],
            "page": tab.get("page"),
            "kind": "table-image",
            "confidence": 0.95,
            "reasons": ["caption starts with 'Table'"],
            "adjudication": "not-needed",
        })

    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    counts = {k: 0 for k in KINDS}
    for e in entries:
        counts[e["kind"]] += 1
    report = {
        "manifest": os.path.abspath(args.manifest),
        "generated_by": "fig_classify.py",
        "counts": counts,
        "entries": entries,
        "unknown_policy": "unknown figures must not be used until the agent "
                          "adjudicates and records the decision",
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print("classified: " + " ".join(f"{k}={v}" for k, v in counts.items())
          + f" -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
