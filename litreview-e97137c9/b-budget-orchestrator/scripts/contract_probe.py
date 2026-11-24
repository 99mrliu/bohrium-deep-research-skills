#!/usr/bin/env python3
"""contract_probe.py — 契约先行探针（bundle B 签名脚本 1）。

职责：
  1. 读取 work/case_profile.json 中的 output_contract（防御式：list 或 dict 均可），
     逐字段生成产出计划 work/contract_map.json：
       {field, source_artifact, required, null_policy}
  2. 立即在 out 目录写出 status=in_progress 的 partial result.json：
     case_id + status + 全部契约字段先填 null（防中断，任何时刻都有可核对交付物）。
  3. 从 task.md 提取硬性要求行（含"必须/须/不得"的句子）写 work/requirements.md。
"""
import json
import os
import re
import sys

# 契约字段名 → 默认来源产物（路径相对 work/，out_ 前缀表示 out/）
FIELD_ARTIFACT = [
    (("research_product", "product", "review", "draft"), "review_draft.md + themes.json"),
    (("evidence_matrix", "evidence", "ledger", "matrix"), "evidence_ledger.jsonl"),
    (("screening_log", "screening"), "screening_log.json"),
    (("uncertainties", "uncertainty"), "uncertainties.json（各阶段汇总）"),
    (("sources", "source"), "docs.jsonl + run_plan.json"),
    (("change_log", "changes"), "change_log.json（budget_ledger 维护）"),
    (("run_plan", "plan"), "run_plan.json"),
    (("consistency_report", "consistency"), "out:consistency_report.json"),
    (("requirements",), "requirements.md"),
    (("case_id",), "case_profile.json"),
    (("status",), "由 build_result.py 裁定"),
]

HARD_REQ_RE = re.compile(r"必须|须|不得")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def contract_fields(contract):
    """把 output_contract 归一化为字段名列表；无法识别时返回 []。"""
    if isinstance(contract, list):
        return [str(x) for x in contract]
    if isinstance(contract, dict):
        return [str(k) for k in contract.keys()]
    if isinstance(contract, str):
        return [contract]
    return []


def match_artifact(field):
    fl = field.lower()
    for aliases, artifact in FIELD_ARTIFACT:
        if fl in aliases:
            return artifact
    return None


def probe(work, out):
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    case_id = profile.get("case_id", "unknown_case")
    fields = contract_fields(profile.get("output_contract"))

    mapping, unmapped = [], []
    for f in fields:
        artifact = match_artifact(f)
        if artifact is None:
            unmapped.append(f)
            artifact = "（无已知来源产物）"
        mapping.append({
            "field": f,
            "source_artifact": artifact,
            "required": True,
            "null_policy": "产物缺失或无法产出时填 null，并在 uncertainties 记录原因；"
                           "不得编造内容、不得漏字段",
        })

    contract_map = {
        "case_id": case_id,
        "contract_found": bool(fields),
        "fields": mapping,
        "unmapped_fields": unmapped,
        "note": "契约字段逐一镜像到 result.json；null 是合法占位，漏字段不是。",
    }
    with open(os.path.join(work, "contract_map.json"), "w", encoding="utf-8") as f:
        json.dump(contract_map, f, ensure_ascii=False, indent=2)

    # partial result.json：status=in_progress，全部契约字段先填 null
    os.makedirs(out, exist_ok=True)
    partial = {"case_id": case_id, "status": "in_progress",
               "note": "契约探针已落盘：全部契约字段暂为 null，待模型阶段与 finalize 填充。"}
    for f in fields:
        if f not in partial:
            partial[f] = None
    for k in ("sources", "uncertainties", "change_log"):
        partial.setdefault(k, [] if k != "change_log" else [])
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(partial, f, ensure_ascii=False, indent=2)

    # 硬性要求行提取
    task_excerpt = profile.get("task_md_excerpt", "")
    reqs = []
    for line in task_excerpt.splitlines():
        line = line.strip().lstrip("#*-• ").strip()
        if line and HARD_REQ_RE.search(line):
            for sent in re.split(r"(?<=[。；;！!])", line):
                sent = sent.strip()
                if sent and HARD_REQ_RE.search(sent):
                    reqs.append(sent)
    with open(os.path.join(work, "requirements.md"), "w", encoding="utf-8") as f:
        f.write("# 硬性要求清单（从 task.md 自动提取，含\"必须/须/不得\"的句子）\n\n")
        if reqs:
            for i, r in enumerate(reqs, 1):
                f.write(f"- R{i}：{r}\n")
        else:
            f.write("- （task.md 中未检出含\"必须/须/不得\"的硬性要求句）\n")
    return contract_map, reqs


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    cmap, reqs = probe(args.work, args.out)
    print(json.dumps({"contract_fields": len(cmap["fields"]),
                      "unmapped": cmap["unmapped_fields"],
                      "hard_requirements": len(reqs),
                      "partial_result": "written"}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
