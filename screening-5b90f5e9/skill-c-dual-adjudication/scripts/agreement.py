#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agreement.py — 合并 S1/S2 标注，输出一致性报告与分歧清单。

用法:
    python3 agreement.py [--s1 /app/work/annotations_s1.jsonl]
                         [--s2 /app/work/annotations_s2.jsonl] [--work /app/work]

输出:
    <work>/agreement_report.json
      {n_records, n_agree, n_disagree, percent_agreement,
       three_class: {labels, contingency, kappa},
       binary_include_vs_rest: {labels, contingency, kappa}}
    <work>/disagreements.json
      逐条 {record_id, title, abstract, s1:{decision,reason_code,evidence_quote},
            s2:{...}} —— 附题录供仲裁者一次性引用。

Cohen's kappa 纯 Python 按列联表实现: kappa = (po - pe) / (1 - pe)。
S1/S2 记录集不一致（条目数或 record_id 集合不同）→ exit 3。

退出码: 0=成功, 2=用法或IO错误, 3=校验失败
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

LABELS3 = ["include", "exclude", "uncertain"]


def eprint(*a):
    print(*a, file=sys.stderr)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def cohens_kappa(pairs, labels):
    """pairs: [(s1_label, s2_label), ...]；返回 (列联表, po, pe, kappa)。"""
    idx = {l: i for i, l in enumerate(labels)}
    k = len(labels)
    table = [[0] * k for _ in range(k)]
    for a, b in pairs:
        table[idx[a]][idx[b]] += 1
    n = len(pairs)
    if n == 0:
        return table, 0.0, 0.0, None
    po = sum(table[i][i] for i in range(k)) / n
    row = [sum(r) for r in table]
    col = [sum(table[i][j] for i in range(k)) for j in range(k)]
    pe = sum(row[i] * col[i] for i in range(k)) / (n * n)
    kappa = None if pe >= 1.0 else (po - pe) / (1 - pe)
    return table, po, pe, kappa


def binarize(d):
    return "include" if d == "include" else "non_include"


def main():
    ap = argparse.ArgumentParser(description="合并 S1/S2 标注并计算一致率与 Cohen's kappa")
    ap.add_argument("--s1", default=None)
    ap.add_argument("--s2", default=None)
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    work = Path(args.work)
    p1 = Path(args.s1) if args.s1 else work / "annotations_s1.jsonl"
    p2 = Path(args.s2) if args.s2 else work / "annotations_s2.jsonl"
    for p in (p1, p2):
        if not p.exists():
            eprint(f"[agreement] 缺少 {p}")
            return 2

    r1 = load_jsonl(p1)
    r2 = load_jsonl(p2)
    m1 = {r["record_id"]: r for r in r1}
    m2 = {r["record_id"]: r for r in r2}
    if len(r1) != len(m1) or len(r2) != len(m2):
        eprint("[agreement] 标注表内 record_id 重复")
        return 3
    if set(m1) != set(m2) or len(r1) != len(r2):
        eprint(f"[agreement] S1({len(r1)}条) 与 S2({len(r2)}条) 记录集不一致: "
               f"仅S1={sorted(set(m1) - set(m2))} 仅S2={sorted(set(m2) - set(m1))}")
        return 3

    rec_text = {}
    dedup_path = work / "records_dedup.jsonl"
    if dedup_path.exists():
        for r in load_jsonl(dedup_path):
            rec_text[r["record_id"]] = r

    pairs3, pairs2, disagreements = [], [], []
    n_agree = 0
    for rid in sorted(m1):
        d1, d2 = m1[rid]["decision"], m2[rid]["decision"]
        pairs3.append((d1, d2))
        pairs2.append((binarize(d1), binarize(d2)))
        if d1 == d2:
            n_agree += 1
        else:
            rec = rec_text.get(rid, {})
            disagreements.append({
                "record_id": rid,
                "title": rec.get("title", ""),
                "abstract": rec.get("abstract", ""),
                "s1": {"decision": d1,
                       "reason_code": m1[rid].get("reason_code", ""),
                       "evidence_quote": m1[rid].get("evidence_quote", "")},
                "s2": {"decision": d2,
                       "reason_code": m2[rid].get("reason_code", ""),
                       "evidence_quote": m2[rid].get("evidence_quote", "")},
            })

    n = len(pairs3)
    t3, po3, pe3, k3 = cohens_kappa(pairs3, LABELS3)
    t2, po2, pe2, k2 = cohens_kappa(pairs2, ["include", "non_include"])
    report = {
        "n_records": n,
        "n_agree": n_agree,
        "n_disagree": n - n_agree,
        "percent_agreement": round(n_agree / n, 4) if n else None,
        "three_class": {
            "labels": LABELS3, "contingency": t3,
            "observed": round(po3, 4), "expected": round(pe3, 4),
            "kappa": round(k3, 4) if k3 is not None else None,
        },
        "binary_include_vs_rest": {
            "labels": ["include", "non_include"], "contingency": t2,
            "observed": round(po2, 4), "expected": round(pe2, 4),
            "kappa": round(k2, 4) if k2 is not None else None,
        },
        "note": "列联表行=S1、列=S2；kappa 纯 Python 按列联表计算。",
    }
    (work / "agreement_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "disagreements.json").write_text(
        json.dumps(disagreements, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[agreement] n={n} agree={n_agree} disagree={n - n_agree} "
          f"kappa_3class={report['three_class']['kappa']} "
          f"kappa_binary={report['binary_include_vs_rest']['kappa']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[agreement] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
