#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mine_near_misses.py — 险漏队列挖掘（near-miss mining）+ 复核工作清单（recheck worklist）。

只消费上游已完成的 judgments/decisions（本技能不做初筛判定本身）。
触发器（命中任一即入复核队列，针对 decision=exclude 的记录）：
  - single_criterion_exclusion：恰好一条判据 verdict=not_met 导致排除；
  - uncertain_verdict：任一判据 verdict=uncertain；
  - weak_evidence_anchor：证据片段 anchor_strength=weak；
  - excluded_without_not_met：被排除但没有任何 not_met 判据（排除依据最脆弱）。
decision=include 但含 uncertain 判据的记录单列 included_uncertain（防错误纳入，不进险漏队列）。

产物：work/near_misses.json、work/recheck_worklist.json；并增量填充 result.json 的
near_misses / recheck_worklist / sources / change_records 字段。

退出码：0=通过；2=judgments 缺失（诚实降级，result.json 记 uncertainty）；3=校验失败。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

EXIT_OK, EXIT_INSUFFICIENT, EXIT_INVALID = 0, 2, 3

RISK_WEIGHTS = {
    "excluded_without_not_met": 4,
    "single_criterion_exclusion": 3,
    "uncertain_verdict": 2,
    "weak_evidence_anchor": 2,
}

SUGGESTED_ACTIONS = {
    "excluded_without_not_met":
        "最高优先：该排除没有任何 not_met 判据支撑，须双人独立复核原始题录后重新判定",
    "single_criterion_exclusion":
        "复核唯一否决判据的判定是否过严，核对证据片段是否支持 not_met",
    "uncertain_verdict":
        "补充证据（如全文/方法段）后重判该 uncertain 判据",
    "weak_evidence_anchor":
        "证据锚定弱：回查标题/摘要原文，确认证据片段真实支撑判定",
}


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_material(input_dir, case, key, fallbacks):
    """按 case.json materials 声明定位材料文件，失败则按备选名探测。"""
    cands = []
    mats = (case or {}).get("materials") or {}
    if mats.get(key):
        cands.append(os.path.join(input_dir, mats[key]))
    cands.extend(os.path.join(input_dir, name) for name in fallbacks)
    for path in cands:
        if os.path.exists(path):
            return path
    return None


def load_judgments(path):
    """接受 {"items": [...]} 或裸 list 两种容器。"""
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError("judgments 文件结构不识别：应为 list 或含 items 的 object")


def ensure_result(result_path, case_id):
    if os.path.exists(result_path):
        return load_json(result_path)
    return {"case_id": case_id, "status": "partial",
            "sources": [], "uncertainty": [], "change_records": []}


def add_source(result, path, role):
    entry = {"path": path, "sha256": sha256_of(path), "role": role}
    sources = [s for s in (result.get("sources") or []) if s.get("path") != path]
    sources.append(entry)
    result["sources"] = sources


def add_uncertainty(result, note):
    unc = result.get("uncertainty") or []
    if note not in unc:
        unc.append(note)
    result["uncertainty"] = unc


def analyze_exclusion(item):
    """对一条 exclude 判定计算触发器与风险分。"""
    criteria = item.get("criteria") or []
    not_met = [c for c in criteria if c.get("verdict") == "not_met"]
    triggers = []
    if not not_met:
        triggers.append({"type": "excluded_without_not_met", "criterion": None})
    elif len(not_met) == 1:
        triggers.append({"type": "single_criterion_exclusion",
                         "criterion": not_met[0].get("criterion_id")})
    for c in criteria:
        if c.get("verdict") == "uncertain":
            triggers.append({"type": "uncertain_verdict",
                             "criterion": c.get("criterion_id")})
        ev = c.get("evidence") or {}
        if ev.get("anchor_strength") == "weak":
            triggers.append({"type": "weak_evidence_anchor",
                             "criterion": c.get("criterion_id")})
    score = sum(RISK_WEIGHTS[t["type"]] for t in triggers)
    actions = sorted({SUGGESTED_ACTIONS[t["type"]] for t in triggers})
    return triggers, score, actions


def main():
    ap = argparse.ArgumentParser(description="险漏队列挖掘与复核工作清单生成")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    try:
        os.makedirs(args.work, exist_ok=True)
        os.makedirs(args.output_dir, exist_ok=True)
        result_path = os.path.join(args.output_dir, "result.json")
        case_path = os.path.join(args.input_dir, "case.json")
        case = load_json(case_path) if os.path.exists(case_path) else {}
        result = ensure_result(result_path, case.get("case_id"))

        judgments_path = find_material(args.input_dir, case, "judgments",
                                       ["judgments.json", "decisions.json"])
        if not judgments_path:
            result["near_misses"] = None
            result["recheck_worklist"] = None
            add_uncertainty(result,
                            "字段 near_misses、recheck_worklist 置 null：输入中未发现 "
                            "judgments/decisions 文件；本技能不做初筛判定，需上游先产出"
                            "逐条判定后方可执行险漏挖掘（诚实降级）。")
            result["change_records"].append({
                "ts": utcnow(),
                "action": "mine_near_misses: judgments missing, degraded",
                "files": [result_path]})
            save_json(result_path, result)
            print("judgments 缺失：已在 result.json 记 uncertainty 并降级", file=sys.stderr)
            return EXIT_INSUFFICIENT

        try:
            items = load_judgments(judgments_path)
        except (ValueError, json.JSONDecodeError) as e:
            print("judgments 校验失败: %s" % e, file=sys.stderr)
            return EXIT_INVALID

        queue, included_uncertain = [], []
        n_excluded = 0
        for item in items:
            decision = item.get("decision")
            criteria = item.get("criteria") or []
            if decision == "exclude":
                n_excluded += 1
                triggers, score, actions = analyze_exclusion(item)
                if triggers:
                    queue.append({
                        "record_id": item.get("record_id"),
                        "primary_reason_code": item.get("primary_reason_code"),
                        "triggers": triggers,
                        "risk_score": score,
                        "suggested_actions": actions,
                    })
            elif decision == "include":
                unc = [c.get("criterion_id") for c in criteria
                       if c.get("verdict") == "uncertain"]
                if unc:
                    included_uncertain.append({
                        "record_id": item.get("record_id"),
                        "uncertain_criteria": unc,
                        "note": "已纳入但含 uncertain 判据，属错误纳入风险（非遗漏风险），建议抽查",
                    })

        queue.sort(key=lambda q: (-q["risk_score"], str(q.get("record_id"))))
        worklist = []
        for rank, entry in enumerate(queue, start=1):
            worklist.append({
                "rank": rank,
                "record_id": entry["record_id"],
                "risk_score": entry["risk_score"],
                "trigger_types": [t["type"] for t in entry["triggers"]],
                "suggested_actions": entry["suggested_actions"],
                "status": "pending_human_recheck",
            })

        near_misses = {
            "generated_by": "mine_near_misses.py v1.0.0",
            "total_judgments": len(items),
            "total_excluded": n_excluded,
            "queue_size": len(queue),
            "queue": queue,
            "included_uncertain": included_uncertain,
        }
        recheck = {
            "generated_by": "mine_near_misses.py v1.0.0",
            "ranking_basis": "risk_score 降序；同分按 record_id 字典序",
            "risk_weights": RISK_WEIGHTS,
            "worklist": worklist,
        }
        nm_path = os.path.join(args.work, "near_misses.json")
        wl_path = os.path.join(args.work, "recheck_worklist.json")
        save_json(nm_path, near_misses)
        save_json(wl_path, recheck)

        result["near_misses"] = near_misses
        result["recheck_worklist"] = recheck
        add_source(result, judgments_path, "judgments")
        result["change_records"].append({
            "ts": utcnow(),
            "action": "mine_near_misses: queue=%d/%d excluded" % (len(queue), n_excluded),
            "files": [nm_path, wl_path, result_path]})
        save_json(result_path, result)
        print("险漏队列 %d 条（排除总数 %d）；工作清单已排序" % (len(queue), n_excluded))
        return EXIT_OK
    except Exception as e:
        print("mine_near_misses 未预期失败: %s" % e, file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
