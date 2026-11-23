#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关系条件 linter：缺失条件 → partial/uncertain，绝不补造。

规则：
  C1 比较型关系缺 metric/basis 或 comparator → status=uncertain + 记录
     （不得把无指标的比较升级为“全局更优”）
  C2 measurement 有 value 但缺 unit 或缺条件作用域 → 数值降级为
     unscoped_value_note，status=partial（数值不进入图谱）
  C3 证据型关系完全无 conditions → status=partial + 记录“条件缺失”
  C4 voice 缺失 → 保持错误（由校验器拦截），此处仅记录
用法：
  python3 condition_lint.py --relations relations.json --out relations_linted.json \
      --findings lint_findings.json
"""
import argparse
import copy
import sys

from relation_common import COMPARATIVE, SCOPE_KEYS, load_json, dump_json


def lint_edge(edge):
    """返回 (linted_edge, findings)。不修改输入。"""
    e = copy.deepcopy(edge)
    findings = []
    rel = e.get("relation")
    cond = e.get("conditions") or {}
    if rel in COMPARATIVE:
        missing = []
        if not (cond.get("metric") or e.get("basis")):
            missing.append("metric/basis")
        if not e.get("comparator"):
            missing.append("comparator")
        if missing:
            e["status"] = "uncertain"
            e.setdefault("notes", []).append(
                "C1: 比较缺少 %s，保持 uncertain，不推断全局优劣" % "/".join(missing))
            findings.append({"edge_id": e.get("edge_id"), "rule": "C1",
                             "missing": missing})
    meas = e.get("measurement")
    if meas and meas.get("value") is not None:
        scoped = any(cond.get(k) for k in SCOPE_KEYS)
        if not meas.get("unit") or not scoped:
            e["unscoped_value_note"] = (
                "C2: 数值 %r 因缺%s被降级，未作为条件化测量入图"
                % (meas.get("value"),
                   "单位" if not meas.get("unit") else "条件作用域"))
            e.pop("measurement", None)
            e["status"] = "partial"
            findings.append({"edge_id": e.get("edge_id"), "rule": "C2"})
    if rel and rel not in COMPARATIVE and not cond:
        e["status"] = "partial"
        e.setdefault("notes", []).append("C3: 条件缺失，保持 partial，不补造条件")
        findings.append({"edge_id": e.get("edge_id"), "rule": "C3"})
    if not e.get("voice"):
        findings.append({"edge_id": e.get("edge_id"), "rule": "C4",
                         "message": "voice 缺失（校验器 R3 已判错误）"})
    for f in findings:
        f.setdefault("message", "")
    return e, findings


def main(argv=None):
    ap = argparse.ArgumentParser(description="关系条件 linter")
    ap.add_argument("--relations", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--findings", required=True)
    args = ap.parse_args(argv)

    doc = load_json(args.relations)
    linted_edges, all_findings = [], []
    for edge in doc.get("edges", []):
        e, fs = lint_edge(edge)
        linted_edges.append(e)
        all_findings.extend(fs)
    out = dict(doc)
    out["edges"] = linted_edges
    dump_json(out, args.out)
    dump_json({"n_findings": len(all_findings), "findings": all_findings},
              args.findings)
    print("lint: edges=%d findings=%d -> %s"
          % (len(linted_edges), len(all_findings), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
