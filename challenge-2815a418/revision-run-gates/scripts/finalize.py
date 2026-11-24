#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py — 交付闸门。

1. 校验 result.json 含原始 case_id 与 output_contract 全部字段，且各 artifact 路径真实存在；
2. 由 qc_report 与各字段完成情况重算诚实总体 status
   （success / partial / unable_to_determine，不由 Agent 拍脑袋）：
     - 基线缺失               → unable_to_determine
     - 有无法补做/警告/失败项  → partial
     - 全部落实且 QC 通过      → success
3. 把 uncertainties 与 change_records 镜像进 result.json；
4. 打印交付摘要。

校验失败 exit 1（诚实 result.json 仍落盘）。仅用 Python 3 标准库。
"""
import argparse
import datetime
import json
import os
import sys


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args(argv)

    errs = []
    case = load(a.case)
    if case is None:
        print("FINALIZE-ERROR: case.json 缺失或无法解析")
        return 2
    case_id = case.get("case_id")
    contract = list((case.get("output_contract") or {}).keys())

    res_p = os.path.join(a.output, "result.json")
    res = load(res_p) or {"case_id": case_id}
    if res.get("case_id") != case_id:
        errs.append("case_id 不匹配：result=%r case=%r" % (res.get("case_id"), case_id))
    for f in contract:
        v = res.get(f)
        if not v:
            errs.append("output_contract 字段 %s 为空" % f)
            continue
        p = v if os.path.isabs(v) else os.path.join(a.output, v)
        if not os.path.exists(p):
            errs.append("字段 %s 的产物路径不存在：%s" % (f, v))

    qc = load(os.path.join(a.work, "qc_report.json"))
    if qc is None:
        errs.append("qc_report.json 缺失（qc 阶段未运行？）")
        qc_overall, qc_warns = "missing", []
    else:
        qc_overall = qc.get("overall")
        qc_warns = qc.get("warnings", [])
        if qc_overall != "pass":
            errs.append("QC 未通过（overall=%s）" % qc_overall)

    decisions = load(os.path.join(a.work, "decisions.json")) or {}
    judgments = decisions.get("judgments", [])
    cannots = [j for j in judgments if j.get("action") == "cannot"]

    mstate = load(os.path.join(a.work, "state", "materials.json")) or {}
    base_missing = any(str(x).startswith("BASELINE_MISSING")
                       for x in (mstate.get("failures") or []))

    uncertainties = ["%s 无法补做：%s" % (j.get("req_id"), j.get("rationale", ""))
                     for j in cannots]
    uncertainties += ["QC 警告：" + str(w) for w in qc_warns]
    uncertainties += ["交付不完整：" + e for e in errs]

    if base_missing:
        status = "unable_to_determine"
    elif errs or cannots or qc_warns:
        status = "partial"
    else:
        status = "success"

    changes = load(os.path.join(a.work, "changes.json")) or {}
    res["case_id"] = case_id
    res["status"] = status
    res["status_note"] = {
        "success": "全部子要求已处理且 QC 通过",
        "partial": "诚实部分完成：存在无法补做/警告/失败项，见 uncertainty",
        "unable_to_determine": "关键材料缺失，无法判断",
    }[status]
    res["sources"] = ["materials/manuscript-baseline.md",
                      "materials/reviewer-comments.md"]
    res["uncertainty"] = uncertainties
    res["change_records"] = [
        {"chg_id": c.get("chg_id"), "req_id": c.get("req_id"),
         "anchor_quote": c.get("anchor_quote"), "status": "applied"}
        for c in changes.get("applied", [])
    ] + [
        {"chg_id": f.get("chg_id"), "req_id": f.get("req_id"),
         "anchor_quote": f.get("anchor_quote"), "status": "failed:" + str(f.get("error"))}
        for f in changes.get("failures", [])
    ]
    res["finalized_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    tmp = res_p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, res_p)

    print("== 交付摘要 ==")
    print("case_id: %s" % case_id)
    print("status: %s" % status)
    print("qc: %s" % qc_overall)
    print("无法补做: %d 项；uncertainty: %d 条" % (len(cannots), len(uncertainties)))
    for f in contract:
        print("  %s -> %s" % (f, res.get(f)))
    if errs:
        print("FINALIZE-ERROR:")
        for e in errs:
            print("  - " + e)
        return 1
    print("FINALIZE-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
