#!/usr/bin/env python3
"""suff_verdict.py — 充分性法庭第 4 步：五级裁决 + 裁决一致性校验（确定性，stdlib-only）。

机器裁决（machine verdict）由覆盖矩阵与冲突登记机械推导：
  L5 充分可答      全部证据面命中，且无相关冲突
  L4 基本可答      覆盖率 ≥0.75，或相关冲突均已可由版本/来源规则消解
  L3 部分可答      覆盖率 ≥0.4：可答已知部分，必须逐面列出未知部分
  L2 证据不足      覆盖率 <0.4：拒答并写明缺什么（哪些证据面无命中）
  L1 无法判读      库不可用（0 个可索引文件 / 问题无法解析）
模型可在 work/model_verdicts.json 申报自己的裁决，但**申报高于机器等级
两级以上（如机器 L2、模型 L5）会被强制回降并留痕**——措辞不能绕过证据。

输出 /app/output/verdicts.json，并把骨架 result.json 更新到对应状态。
退出码恒 0。
"""
import argparse
import json
import os
import sys
import time

LEVELS = {5: "充分可答", 4: "基本可答", 3: "部分可答", 2: "证据不足拒答", 1: "无法判读"}


def machine_verdict(entry, conflicts, n_ok_files):
    qid = entry["question_id"]
    if n_ok_files == 0:
        return 1, "库内无可读文件"
    cov = entry["coverage"]
    if cov["facets_total"] == 0:
        return 1, "问题无法解析出证据面"
    missing = [f["term"] for f in entry["facets"] if not f["found"]]
    # 相关冲突：冲突主体或上下文与命中行重叠（粗判：术语出现在冲突文本中）
    terms = {f["term"] for f in entry["facets"] if f["found"]}
    related = [c for c in conflicts
               if any(t in (c["subject"] + c["side_a"]["context"] + c["side_b"]["context"])
                      for t in terms)]
    r = cov["ratio"]
    if not missing and not related:
        return 5, "全部 %d 个证据面命中，无相关冲突" % cov["facets_total"]
    if r >= 0.75:
        note = "覆盖率 %.2f≥0.75" % r + ("；存在 %d 条相关冲突须消解" % len(related) if related else "")
        return 4, note
    if r >= 0.4:
        return 3, "覆盖率 %.2f；未命中证据面：%s" % (r, "、".join(missing[:6]))
    return 2, "覆盖率 %.2f<0.4；缺：%s" % (r, "、".join(missing[:6]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    def load(p, default):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    matrix = load(os.path.join(a.out, "coverage_matrix.json"), {"matrix": []})
    conflicts = load(os.path.join(a.out, "conflict_registry.json"), {"conflicts": []})["conflicts"]
    index = load(os.path.join(a.work, "suff_index.json"), {"files": []})
    n_ok = sum(1 for e in index["files"] if e["text_status"] == "ok")
    model_v = load(os.path.join(a.work, "model_verdicts.json"), {"verdicts": []})
    model_by_q = {v["question_id"]: v for v in model_v.get("verdicts", [])}

    verdicts, demotions = [], []
    for entry in matrix["matrix"]:
        qid = entry["question_id"]
        level, basis = machine_verdict(entry, conflicts, n_ok)
        rec = {"question_id": qid, "machine_level": level,
               "machine_verdict": LEVELS[level], "basis": basis,
               "coverage": entry["coverage"],
               "missing_facets": [f["term"] for f in entry["facets"] if not f["found"]],
               "model_level": None, "final_level": level}
        mv = model_by_q.get(qid)
        if mv:
            rec["model_level"] = mv.get("level")
            if isinstance(mv.get("level"), int):
                if mv["level"] - level >= 2:
                    rec["final_level"] = level + 1
                    rec["demoted"] = True
                    demotions.append({"question_id": qid,
                                      "model": mv["level"], "machine": level,
                                      "rule": "申报高于机器等级≥2级，回降至机器等级+1"})
                else:
                    rec["final_level"] = mv["level"] if mv["level"] < level else level
                    rec["demoted"] = mv["level"] > level
        verdicts.append(rec)

    out = {"schema": "kbqa-abstention-court/verdicts/v1",
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "levels": LEVELS, "verdicts": verdicts, "demotions": demotions}
    with open(os.path.join(a.out, "verdicts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 更新 result.json（若存在）
    rp = os.path.join(a.out, "result.json")
    result = load(rp, {})
    if result:
        by_q = {v["question_id"]: v for v in verdicts}
        for ans in result.get("answers", []):
            v = by_q.get(ans.get("question_id"))
            if v:
                ans["verdict"] = "%d-%s" % (v["final_level"], LEVELS[v["final_level"]])
                ans["missing"] = v["missing_facets"] or None
                if v["final_level"] <= 2 and not ans.get("answer"):
                    ans["answer"] = "证据不足，拒答。缺少证据面：%s" % (
                        "、".join(v["missing_facets"]) or "（无法解析）")
        result["uncertainty"] = [u for u in result.get("uncertainty", [])
                                 if u != "skeleton written at init"]
        for d in demotions:
            result["uncertainty"].append(
                "问题 %(question_id)s 模型申报 L%(model)s 被机器裁决回降（机器 L%(machine)s）" % d)
        result.setdefault("change_log", []).append(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "event": "verdicts applied: %d questions, %d demotions"
                      % (len(verdicts), len(demotions))})
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"verdicts": [{"q": v["question_id"], "machine": v["machine_level"],
                                    "final": v["final_level"]} for v in verdicts],
                      "demotions": len(demotions)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
