#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_lab.py — 复算实验室一键管线。

  python3 run_lab.py --input /input --work /app/work --output /app/output [--claims claims.json]

1. partial-first 落 result.json 骨架；
2. 扫描 /input 全部两列以上数值文件，逐文件生成双通道复算账本
   -> /app/work/ledgers/<file>.ledger.json，汇总 /app/work/ledger_index.json；
3. 若提供 --claims（Agent 撰写结论前登记的数值清单），运行 claim_audit；
4. 预填 result.json 契约字段（复算可负责部分），渲染 report.md。

交付规则：claims 审计 deliverable=false 时 result.json 不得 status=success。
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import claim_audit  # noqa: E402

META = ("case_id", "status", "limitations", "sources", "uncertainty", "change_records")


def contract_of(case):
    cid = case.get("case_id") or case.get("id") or "unknown_case"
    oc = case.get("output_contract") or {}
    fields = []
    if isinstance(oc, dict):
        f = oc.get("fields") or oc.get("required_fields") or oc.get("properties")
        if isinstance(f, dict):
            fields = list(f)
        elif isinstance(f, list):
            fields = [i if isinstance(i, str) else i.get("name") for i in f]
        if not fields:
            fields = [k for k, v in oc.items() if isinstance(v, (str, dict))]
    return cid, [x for x in fields if x]


def numeric_files(input_dir):
    out = []
    for ext in ("*.csv", "*.txt", "*.dat", "*.tsv"):
        out += glob.glob(os.path.join(input_dir, "**", ext), recursive=True)
    return sorted(p for p in out if not os.path.basename(p).startswith("."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--claims", default=None)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.output, exist_ok=True)
    led_dir = os.path.join(a.work, "ledgers")
    os.makedirs(led_dir, exist_ok=True)
    result_path = os.path.join(a.output, "result.json")
    case_path = os.path.join(a.input, "case.json")
    case = json.load(open(case_path, encoding="utf-8")) if os.path.exists(case_path) \
        else {"case_id": "unknown_case", "output_contract": {}}
    cid, fields = contract_of(case)
    res = {"case_id": cid, "status": "partial",
           "limitations": ["复算骨架已建立"],
           "sources": [], "uncertainty": [], "change_records": ["run_lab partial-first"]}
    for f in fields:
        res[f] = None
    json.dump(res, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 2) 逐文件复算账本
    index = []
    for p in numeric_files(a.input):
        for mode, extra in (("series", ["--col", "1"]),
                            ("fit", ["--xcol", "0", "--ycol", "1"])):
            out = subprocess.run([sys.executable,
                                  os.path.join(HERE, "two_channel.py"), mode,
                                  "--file", p] + extra,
                                 capture_output=True, text=True)
            if out.returncode != 0:
                continue
            led = json.loads(out.stdout)
            name = os.path.basename(p) + "." + mode + ".ledger.json"
            json.dump(led, open(os.path.join(led_dir, name), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            index.append({"file": p, "mode": mode, "ledger": "ledgers/" + name,
                          "overall": led["summary"]["overall"],
                          "quantities": sorted(led["quantities"].keys())})
    json.dump(index, open(os.path.join(a.work, "ledger_index.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    n_dis = sum(1 for i in index if i["overall"] == "DISAGREE")

    # 3) claims 审计
    audit_rep = None
    if a.claims and os.path.exists(a.claims):
        rep = claim_audit.audit(json.load(open(a.claims, encoding="utf-8")))
        audit_path = os.path.join(a.work, "claims_audit.json")
        json.dump(rep, open(audit_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        audit_rep = rep

    # 4) 预填
    blocks = {
        "复核": "第二人复核: 重跑 run_lab.py 复算全部账本；逐 claim 对照 claims_audit.json；"
                "任何 DISAGREE 项不得写入结论。",
        "依据": "全部数值结论依据双通道复算账本（/app/work/ledgers/，容差 abs=1e-9, rel=1e-9）；"
                "风险: 容差外的有效数字进位差异须由 Agent 判断。",
        "风险": None,
        "确认": "需专家确认: 报告中采用的容差（rel_tol）是否符合领域惯例。",
    }
    filled, unfilled = [], []
    summary_txt = ("复算覆盖 %d 个文件 %d 个账本；通道不一致账本 %d 个。"
                   % (len({i['file'] for i in index}), len(index), n_dis))
    if audit_rep:
        summary_txt += (" claims 审计: %d/%d 未确认。"
                        % (audit_rep["summary"]["not_confirmed"],
                           audit_rep["summary"]["total"]))
    for f in fields:
        val = None
        for key, v in blocks.items():
            if key in f and v:
                val = v
                break
        if val is None and any(k in f for k in ("趋势", "异常", "数据", "统计", "质量")):
            val = "（复算概览）" + summary_txt + " 详见 ledger_index.json 与各账本。"
        if val:
            res[f] = val
            filled.append(f)
        else:
            unfilled.append(f)
    res["sources"] += ["ledger_index.json", "ledgers/ 目录全部账本"]
    if audit_rep:
        res["sources"].append("claims_audit.json")
    res["uncertainty"].append("双通道一致仅排除实现错误，不排除方法本身不适用（如非线性段做线性拟合）")
    if n_dis:
        res["uncertainty"].append("%d 个账本存在通道不一致，对应文件的统计量暂不可报" % n_dis)
    deliverable = (n_dis == 0) and (audit_rep is None or audit_rep["summary"]["deliverable"])
    if unfilled or not deliverable:
        res["status"] = "partial"
        lims = []
        if unfilled:
            lims.append("待 Agent 撰写字段: " + ", ".join(unfilled))
        if not deliverable:
            lims.append("存在通道不一致或 claims 未确认，按规则不得 success")
        res["limitations"] = lims
    else:
        res["status"] = "success"
        res["limitations"] = []
    res["change_records"].append("run_lab 完成: " + summary_txt)
    json.dump(res, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(os.path.join(a.output, "report.md"), "w", encoding="utf-8") as fp:
        fp.write("# 复算实验室报告\n\n- case_id: `%s`\n- status: %s\n- %s\n"
                 % (cid, res["status"], summary_txt))
    print("[run_lab] ledgers=%d disagree=%d claims=%s status=%s"
          % (len(index), n_dis,
             "n/a" if audit_rep is None else audit_rep["summary"],
             res["status"]))


if __name__ == "__main__":
    main()
