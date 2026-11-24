#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_audit.py — 结论数值审计：把 Agent 准备写进结论的每个数，与复算账本核对。

输入 claims.json（Agent 撰写结论前必须登记）:
[
  {"claim_id": "C1", "text": "载荷均值 812.3 N", "quantity": "mean",
   "value": 812.3, "source_file": "traces/all.txt", "col": 1,
   "rel_tol": 0.001, "abs_tol": null}
]

流程：对每个 claim 调用 two_channel.py 复算 → 比对 → verdict:
  CONFIRMED    |claim - A| 在容差内且 A/B AGREE
  TOLERANCE_MISS 复算成功但数值超容差 → 结论必须改数或改容差并说明
  CHANNEL_DISAGREE A/B 通道不一致 → 该数不可报，须排查
  UNVERIFIABLE  缺 quantity/source_file 等 → 不可交付

  python3 claim_audit.py --claims claims.json --out audit.json
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def recompute(claim):
    q = claim.get("quantity")
    f = claim.get("source_file")
    if not q or not f or not os.path.exists(f):
        return None
    col = claim.get("col", 1)
    if q in ("mean", "variance_pop", "median", "max"):
        out = subprocess.run([sys.executable, os.path.join(HERE, "two_channel.py"),
                              "series", "--file", f, "--col", str(col)],
                             capture_output=True, text=True)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    if q in ("slope", "auc_trapz"):
        out = subprocess.run([sys.executable, os.path.join(HERE, "two_channel.py"),
                              "fit", "--file", f,
                              "--xcol", str(claim.get("xcol", 0)),
                              "--ycol", str(col)],
                             capture_output=True, text=True)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    return None


def audit(claims):
    results = []
    for c in claims:
        r = {"claim_id": c.get("claim_id"), "text": c.get("text")}
        led = recompute(c)
        if led is None:
            r["verdict"] = "UNVERIFIABLE"
            r["reason"] = "缺 quantity/source_file，或文件不存在，或复算失败"
            results.append(r)
            continue
        q = c["quantity"]
        entry = led["quantities"].get(q)
        if entry is None:
            r["verdict"] = "UNVERIFIABLE"
            r["reason"] = "账本中无该统计量"
            results.append(r)
            continue
        if entry["verdict"] == "DISAGREE":
            r["verdict"] = "CHANNEL_DISAGREE"
            r["ledger_entry"] = entry
            results.append(r)
            continue
        rel_tol = c.get("rel_tol", 1e-6)
        abs_tol = c.get("abs_tol")
        d = abs(c["value"] - entry["A"])
        scale = max(abs(entry["A"]), 1e-300)
        ok = (abs_tol is not None and d <= abs_tol) or (d / scale <= rel_tol)
        r["verdict"] = "CONFIRMED" if ok else "TOLERANCE_MISS"
        r["recomputed"] = entry["A"]
        r["claimed"] = c["value"]
        r["rel_diff"] = d / scale
        r["rel_tol"] = rel_tol
        results.append(r)
    n_bad = sum(1 for r in results if r["verdict"] != "CONFIRMED")
    return {"claims": results,
            "summary": {"total": len(results), "not_confirmed": n_bad,
                        "deliverable": n_bad == 0}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    claims = json.load(open(a.claims, encoding="utf-8"))
    rep = audit(claims)
    json.dump(rep, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[claim_audit] total=%d not_confirmed=%d deliverable=%s"
          % (rep["summary"]["total"], rep["summary"]["not_confirmed"],
             rep["summary"]["deliverable"]))
    sys.exit(0 if rep["summary"]["deliverable"] else 1)


if __name__ == "__main__":
    main()
