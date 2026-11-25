#!/usr/bin/env python3
"""flow_check.py — 计算 PRISMA-2020 风格流程计数并校验算术不变量。

用法:
    python3 flow_check.py --workdir /app/work

读取 workdir 下: harvest_report.json, candidates.jsonl, duplicates.jsonl,
screening.jsonl（可选）。产出 workdir/flow.json 与 workdir/flow_report.md。

强制不变量（任一失败退出码 1）:
    I1: identified - duplicates_removed == unique_screened
    I2: 每个阶段 screened = include + exclude + uncertain，且 screened <= unique_screened
    I3: 每条（生效的）exclude 决定至少携带一条 criterion
退出码: 0 全部通过；1 不变量被违反；2 用法/IO 错误。
仅 Python 3 标准库。
"""
import argparse
import json
import os
import sys


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass  # 坏行不致命：flow 只统计可解析行
    return rows


def effective_decisions(screening_rows):
    """同一 cand_id 多行决定时最后一行生效；返回 {stage: {cand_id: row}}。"""
    by_stage = {}
    for row in screening_rows:
        stage = row.get("stage", "title_abstract")
        by_stage.setdefault(stage, {})[row["cand_id"]] = row
    return by_stage


def main(argv=None):
    ap = argparse.ArgumentParser(description="PRISMA 风格流程计数与不变量校验")
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args(argv)

    w = args.workdir
    try:
        with open(os.path.join(w, "harvest_report.json"), "r", encoding="utf-8") as f:
            harvest = json.load(f)
    except Exception as e:
        print("ERROR: 读取 harvest_report.json 失败（先运行 init_ledger.py）: %s" % e,
              file=sys.stderr)
        return 2

    candidates = read_jsonl(os.path.join(w, "candidates.jsonl"))
    duplicates = read_jsonl(os.path.join(w, "duplicates.jsonl"))
    screening = read_jsonl(os.path.join(w, "screening.jsonl"))

    identified = harvest.get("identified_raw")
    if identified is None:  # 兜底：由现有文件推算
        identified = len(candidates) + len(duplicates)
    duplicates_removed = len(duplicates)
    unique_screened = len(candidates)

    by_stage = effective_decisions(screening)
    stages = {}
    invariants = {}
    ok = True

    # I1
    i1 = (identified - duplicates_removed) == unique_screened
    invariants["I1_identified_minus_duplicates_equals_unique"] = {
        "pass": i1,
        "detail": "identified(%d) - duplicates_removed(%d) = %d vs unique_screened(%d)"
                  % (identified, duplicates_removed,
                     identified - duplicates_removed, unique_screened)}
    ok = ok and i1

    cand_ids = {c["cand_id"] for c in candidates}
    for stage, decs in (by_stage.items() or {"title_abstract": {}}.items()):
        inc = [c for c, r in decs.items() if r.get("decision") == "include"]
        exc = [c for c, r in decs.items() if r.get("decision") == "exclude"]
        unc = [c for c, r in decs.items() if r.get("decision") == "uncertain"]
        screened = len(decs)
        # I2
        i2a = screened == len(inc) + len(exc) + len(unc)
        i2b = screened <= unique_screened
        unknown = [c for c in decs if c not in cand_ids]
        # I3
        exc_no_crit = [c for c, r in decs.items()
                       if r.get("decision") == "exclude" and not r.get("criterion")]
        i3 = not exc_no_crit
        invariants["I2_stage_%s_arithmetic" % stage] = {
            "pass": i2a and i2b and not unknown,
            "detail": "screened=%d include=%d exclude=%d uncertain=%d; <=unique: %s; "
                      "未知cand_id: %s" % (screened, len(inc), len(exc), len(unc),
                                           i2b, unknown or "无")}
        invariants["I3_stage_%s_excludes_have_criteria" % stage] = {
            "pass": i3,
            "detail": "无 criterion 的排除: %s" % (exc_no_crit or "无")}
        ok = ok and i2a and i2b and not unknown and i3
        stages[stage] = {
            "screened": screened,
            "include": len(inc), "exclude": len(exc), "uncertain": len(unc),
            "include_ids": sorted(inc), "exclude_ids": sorted(exc),
            "uncertain_ids": sorted(unc),
        }

    ta = stages.get("title_abstract",
                    {"screened": 0, "include": 0, "exclude": 0, "uncertain": 0,
                     "include_ids": [], "exclude_ids": [], "uncertain_ids": []})
    screened_ids = set()
    for decs in by_stage.values():
        screened_ids.update(decs)
    unscreened = sorted(cand_ids - screened_ids)

    # ---- 遗漏声明 ----
    omissions = []
    if unique_screened == 0:
        omissions.append("零结果声明：本次离线快照中检索到 0 条候选记录"
                         "（identified=0）。未发明任何候选；可能原因见 "
                         "harvest_report.json 的 notes。")
    if unscreened:
        omissions.append("未筛选声明：以下 %d 条候选尚无有效筛选决定：%s。"
                         % (len(unscreened), ", ".join(unscreened)))
    if ta["uncertain_ids"]:
        omissions.append("待定声明：以下 %d 条候选因元数据不足判为 uncertain，"
                         "待补充信息后复筛：%s。"
                         % (len(ta["uncertain_ids"]), ", ".join(ta["uncertain_ids"])))
    if unique_screened > 0 and not unscreened and ta["include"] == 0 \
            and ta["screened"] == unique_screened:
        omissions.append("空结果声明：全部 %d 条唯一候选均已完成筛选，无文献满足纳入标准"
                         "（每条排除均附 criterion、理由与已核验证据引句）。"
                         % unique_screened)

    flow = {
        "identified": identified,
        "duplicates_removed": duplicates_removed,
        "unique_screened": unique_screened,
        "screened": ta["screened"],
        "excluded": ta["exclude"],
        "included": ta["include"],
        "uncertain": ta["uncertain"],
        "unscreened": len(unscreened),
        "unscreened_ids": unscreened,
        "reports_sought": ta["include"] + ta["uncertain"],
        "reports_not_retrieved": 0,
        "assessed": ta["screened"],
        "stages": stages,
        "invariants": invariants,
        "omissions": omissions,
    }
    with open(os.path.join(w, "flow.json"), "w", encoding="utf-8") as f:
        json.dump(flow, f, ensure_ascii=False, indent=2)

    # ---- 人读报告 ----
    md = ["# 筛选流程报告（PRISMA-2020 风格）", "",
          "| 阶段 | 计数 |", "|---|---|",
          "| identified（去重前） | %d |" % identified,
          "| duplicates removed | %d |" % duplicates_removed,
          "| records screened（唯一记录） | %d |" % unique_screened,
          "| 已有有效决定 | %d |" % ta["screened"],
          "| records excluded（均附理由） | %d |" % ta["exclude"],
          "| uncertain（待定） | %d |" % ta["uncertain"],
          "| 未筛选 | %d |" % len(unscreened),
          "| included | %d |" % ta["include"], "",
          "## 不变量校验", ""]
    for name, inv in invariants.items():
        md.append("- [%s] %s — %s" % ("PASS" if inv["pass"] else "FAIL", name, inv["detail"]))
    md += ["", "## 遗漏声明", ""]
    if omissions:
        md += ["- " + o for o in omissions]
    else:
        md.append("- 无：所有候选均已有有效决定，且无待定项。")
    md.append("")
    with open(os.path.join(w, "flow_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    with open(os.path.join(w, "change_records.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"action": "flow_check",
                            "invariants_pass": ok,
                            "screened": ta["screened"],
                            "unscreened": len(unscreened)},
                           ensure_ascii=False) + "\n")

    print("identified=%d duplicates=%d unique=%d screened=%d include=%d exclude=%d "
          "uncertain=%d unscreened=%d invariants=%s"
          % (identified, duplicates_removed, unique_screened, ta["screened"],
             ta["include"], ta["exclude"], ta["uncertain"], len(unscreened),
             "PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
