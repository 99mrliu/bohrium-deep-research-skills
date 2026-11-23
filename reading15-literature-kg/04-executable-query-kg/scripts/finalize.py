#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py — 汇总产物，生成 /app/output/result.json（仅标准库）。

契约要求：result.json 必须包含 case_id，并【动态镜像】case.json 中
output_contract 的全部原始键——逐键给出实际产物或如实标注未产出，
不凭题面字面猜测键名，也不静默丢弃任何键。

另含诚实字段：status（success/partial/blocked）、partial、sources、
uncertainty、changes、artifacts（含 sha256）、validation/query 摘要。
"""

import argparse
import hashlib
import json
import os
import sys


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(path, default=None):
    if not path or not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def _artifact(out_dir, name):
    p = os.path.join(out_dir, name)
    if os.path.isfile(p):
        return {"path": p, "sha256": _sha_file(p), "bytes": os.path.getsize(p)}
    return None


# output_contract 键 → 产物映射的启发式（只做键名归类，不假定题面内容）
def _match_contract_key(key):
    k = key.lower()
    if any(t in k for t in ("graph", "图谱", "kg")):
        return "graph"
    if any(t in k for t in ("quer", "查询", "question", "answer", "答案")):
        return "queries"
    if any(t in k for t in ("evidence", "证据", "valid", "核验", "check")):
        return "evidence"
    if any(t in k for t in ("merge", "合并", "align", "对齐")):
        return "merge"
    if any(t in k for t in ("preview", "预览", "svg", "markdown", "md", "report", "报告")):
        return "preview"
    return None


def build_result(case, out_dir, status, uncertainty, changes, extra=None):
    case = case or {}
    contract = case.get("output_contract")
    if not isinstance(contract, dict):
        contract = {}
    contract_note = []
    mirrored = {}
    art = lambda n: _artifact(out_dir, n)
    for key in contract:
        kind = _match_contract_key(key)
        if kind == "graph":
            arts = [a for a in (art("graph.json"), art("graph.jsonl"),
                                art("nodes.csv"), art("edges.csv")) if a]
            mirrored[key] = {"status": "done" if arts else "not_produced",
                             "artifacts": arts or None}
        elif kind == "queries":
            qr = _load(os.path.join(out_dir, "query_results.json"))
            mirrored[key] = {"status": "done" if qr else "not_produced",
                             "summary": qr.get("summary") if qr else None,
                             "artifact": art("query_results.json")}
        elif kind == "evidence":
            vr = _load(os.path.join(out_dir, "validation_report.json"))
            mirrored[key] = {"status": "done" if vr else "not_produced",
                             "ok": vr.get("ok") if vr else None,
                             "checked_evidence": vr.get("checked_evidence") if vr else None,
                             "artifact": art("validation_report.json")}
        elif kind == "merge":
            gj = _load(os.path.join(out_dir, "graph.json"))
            md = gj.get("merge_decisions") if gj else None
            mirrored[key] = {"status": "done" if md else "not_produced",
                             "n_decisions": len(md) if md else 0,
                             "decisions": md}
        elif kind == "preview":
            arts = [a for a in (art("graph.md"), art("graph.svg")) if a]
            mirrored[key] = {"status": "done" if arts else "not_produced",
                             "artifacts": arts or None}
        else:
            mirrored[key] = {"status": "not_produced",
                             "note": "该 output_contract 键无法映射到本工作流产出，如实留空"}
            contract_note.append(key)
    if contract_note:
        uncertainty = list(uncertainty) + [
            "output_contract 键 %s 未映射到产物（如实标注 not_produced）"
            % "、".join(contract_note)]
    if not contract:
        uncertainty = list(uncertainty) + ["case.json 未提供 output_contract，无法逐键镜像"]

    artifacts = []
    for name in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
        a = _artifact(out_dir, name)
        if a:
            artifacts.append(dict(a, name=name))

    result = {
        "case_id": case.get("case_id", case.get("id", "unknown")),
        "status": status,
        "partial": status != "success",
        "output_contract": mirrored,
        "sources": (extra or {}).get("sources", []),
        "uncertainty": uncertainty,
        "changes": changes,
        "artifacts": artifacts,
    }
    if extra:
        for k in ("graph_hash", "counts", "validation_ok", "query_summary",
                  "snapshot_hash", "label"):
            if k in extra:
                result[k] = extra[k]
    # 契约键同时提升到 result.json 顶层（与既有顶层键冲突时保留真实顶层值），
    # 保证“result.json 含全部 output_contract 字段”可被顶层直接核验。
    for k, v in mirrored.items():
        if k not in result:
            result[k] = v
    return result


def write_result(result, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description="汇总产物生成 result.json")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--out", required=True, help="/app/output")
    ap.add_argument("--status", default="partial",
                    choices=["success", "partial", "blocked"])
    ap.add_argument("--uncertainty", default="", help="分号分隔的不确定性说明")
    ap.add_argument("--changes", default="", help="分号分隔的变更记录")
    args = ap.parse_args(argv)
    case = _load(args.case, {})
    uncertainty = [u for u in args.uncertainty.split(";") if u.strip()]
    changes = [c for c in args.changes.split(";") if c.strip()]
    result = build_result(case, args.out, args.status, uncertainty, changes)
    p = write_result(result, args.out)
    print("已写出 %s（status=%s，镜像 output_contract 键 %d 个）"
          % (p, result["status"], len(result["output_contract"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
