#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage.py — 核算义务覆盖度并渲染台账与比较矩阵。

输入 obligations.jsonl（可能部分 open），输出三份产物：
  coverage.json          总关闭率、per-dimension、per-document、open 清单
  obligation-ledger.md   义务 × 状态台账（机器渲染，非手工产物）
  comparison-matrix.md   已关闭 field_cell 义务的取值视图 + 可比性判定表

用法：
  python3 coverage.py --obligations obligations.jsonl --out-dir OUTDIR
"""
import argparse
import json
import os
import sys
from collections import OrderedDict

STATUS_LABEL = {
    "open": "⚠ OPEN",
    "answered_with_evidence": "已回答",
    "not_reported_confirmed": "未报告（已确认）",
    "conflict_preserved": "冲突（已保留）",
    "out_of_scope": "范围外",
}


def load_jsonl(path):
    recs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def group_key(o):
    if o["kind"] == "field_cell":
        return "field:%s" % o["field"]
    if o["kind"] == "comparability":
        return "dim:%s" % o["dimension"]
    return "question"


def docs_of(o):
    if o.get("document_id"):
        return [o["document_id"]]
    if o.get("doc_pair"):
        return list(o["doc_pair"])
    return ["(all)"]


def cell_text(o):
    s = o["status"]
    c = o.get("closure") or {}
    if s == "answered_with_evidence":
        v = str(c.get("value", ""))
        if c.get("unit"):
            v += " " + str(c["unit"])
        src = c.get("source_document_id") or ""
        pid = c.get("paragraph_id") or ""
        return "%s 〔%s#%s〕" % (v, src, pid) if src else v
    if s == "conflict_preserved":
        return "冲突保留：%s" % (c.get("value") or c.get("note", ""))
    return STATUS_LABEL.get(s, s)


def main():
    ap = argparse.ArgumentParser(description="核算覆盖度并渲染台账/矩阵")
    ap.add_argument("--obligations", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    obligations = load_jsonl(args.obligations)
    total = len(obligations)
    closed = [o for o in obligations if o["status"] != "open"]
    open_obl = [o for o in obligations if o["status"] == "open"]

    def bucket_stats(keys_func):
        buckets = OrderedDict()
        for o in obligations:
            for k in keys_func(o):
                b = buckets.setdefault(k, {"total": 0, "closed": 0, "open_ids": []})
                b["total"] += 1
                if o["status"] == "open":
                    b["open_ids"].append(o["obligation_id"])
                else:
                    b["closed"] += 1
        return {
            k: {
                "total": b["total"],
                "closed": b["closed"],
                "open": b["total"] - b["closed"],
                "closure_rate": round(b["closed"] / b["total"], 4) if b["total"] else 0.0,
                "open_ids": b["open_ids"],
            }
            for k, b in buckets.items()
        }

    coverage = {
        "total": total,
        "closed": len(closed),
        "open": len(open_obl),
        "closure_rate": round(len(closed) / total, 4) if total else 0.0,
        "by_status": {},
        "by_dimension": bucket_stats(lambda o: [group_key(o)]),
        "by_document": bucket_stats(docs_of),
        "open_obligations": [o["obligation_id"] for o in open_obl],
    }
    for o in obligations:
        coverage["by_status"][o["status"]] = coverage["by_status"].get(o["status"], 0) + 1

    os.makedirs(args.out_dir, exist_ok=True)
    cov_path = os.path.join(args.out_dir, "coverage.json")
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    # ---- obligation-ledger.md ----
    lines = [
        "# 义务台账（obligation ledger）",
        "",
        "总义务 %d 条；已关闭 %d（%.1f%%）；仍 open %d。"
        % (total, len(closed), 100.0 * coverage["closure_rate"], len(open_obl)),
        "",
        "| obligation_id | 类型 | 维度/字段 | 文档 | 状态 | 取值/说明 |",
        "|---|---|---|---|---|---|",
    ]
    for o in obligations:
        dim_field = o.get("dimension") or o.get("field") or "-"
        docs = o.get("document_id") or (" × ".join(o["doc_pair"]) if o.get("doc_pair") else "-")
        c = o.get("closure") or {}
        detail = c.get("value") or c.get("note") or ""
        detail = str(detail).replace("|", "\\|")
        if len(detail) > 80:
            detail = detail[:77] + "…"
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            o["obligation_id"], o["kind"], dim_field, docs,
            STATUS_LABEL.get(o["status"], o["status"]), detail))
    if open_obl:
        lines += ["", "## 未关闭义务（必须豁免或写入 result.json 的 uncertainty）", ""]
        for o in open_obl:
            lines.append("- `%s`（%s）" % (o["obligation_id"], o["kind"]))
    ledger_path = os.path.join(args.out_dir, "obligation-ledger.md")
    with open(ledger_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # ---- comparison-matrix.md ----
    fields = sorted({o["field"] for o in obligations if o["kind"] == "field_cell"})
    docs = sorted({d for o in obligations for d in docs_of(o) if d != "(all)"})
    cellmap = {(o["field"], o["document_id"]): o for o in obligations if o["kind"] == "field_cell"}
    m = ["# 比较矩阵（台账关闭义务的渲染视图）", ""]
    m.append("| 字段 \\ 文档 | " + " | ".join(docs) + " |")
    m.append("|" + "---|" * (len(docs) + 1))
    for field in fields:
        row = ["| " + field]
        for d in docs:
            o = cellmap.get((field, d))
            row.append(cell_text(o).replace("|", "\\|") if o else "—")
        m.append(" | ".join(row) + " |")
    cmps = [o for o in obligations if o["kind"] == "comparability"]
    if cmps:
        m += ["", "## 可比性判定（维度 × 文档对）", "",
              "| 维度 | 文档对 | 判定 | 证据 |", "|---|---|---|---|"]
        for o in cmps:
            c = o.get("closure") or {}
            verdict = (c.get("value") if o["status"] != "open" else None) or STATUS_LABEL[o["status"]]
            ev = ""
            if c.get("source_document_id"):
                ev = "%s#%s" % (c["source_document_id"], c.get("paragraph_id", ""))
            if c.get("secondary_source_document_id"):
                ev += " ↔ %s#%s" % (c["secondary_source_document_id"], c.get("secondary_paragraph_id", ""))
            m.append("| %s | %s | %s | %s |" % (
                o["dimension"], " × ".join(o["doc_pair"]),
                str(verdict).replace("|", "\\|"), ev))
    matrix_path = os.path.join(args.out_dir, "comparison-matrix.md")
    with open(matrix_path, "w", encoding="utf-8") as f:
        f.write("\n".join(m) + "\n")

    print("[coverage] 总关闭率 %.1f%%（%d/%d）；open %d 条" % (100.0 * coverage["closure_rate"], len(closed), total, len(open_obl)))
    for k, v in coverage["by_dimension"].items():
        print("  %-28s %d/%d" % (k, v["closed"], v["total"]))
    print("[coverage] 写出：%s, %s, %s" % (cov_path, ledger_path, matrix_path))
    if open_obl:
        print("[coverage] 警告：仍有 open 义务：%s" % coverage["open_obligations"], file=sys.stderr)


if __name__ == "__main__":
    main()
