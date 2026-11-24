#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 归一化装配 result.json（诚实兜底，绝不编造）

用法:
    python3 assemble_result.py --case <case.json> --artifacts <dir> --out <result.json>
                               --status <complete|partial|failed> [--note "..."]

行为契约:
    1. 从 case.json 定位 case_id 与 output_contract 字段清单（字段名不固定，按子串启发式填充）。
    2. 扫描 --artifacts 目录下各实算脚本的 JSON 产物（budget/schedule/domains，按 plan_id 归组）。
    3. 结论分级: 超支 / 超出(超期) / out_of_domain = gating fail；其余 unverified 如实列出。
       选首个无 gating fail 的方案为 chosen_plan；全部失败 → chosen_plan_id=null 并写入 uncertainty。
    4. 保证 result.json 含: case_id + output_contract 全部字段 + status + sources
       + uncertainty + change_record。
    5. 若 --out 已存在: 载入并合并 —— 绝不覆盖已有的非空值；缺什么补什么。
       无法由实算产物填充的 contract 字段置 null 并在 uncertainty 说明（不编造）。
    6. 追加一条 change_record（时间戳 + actor + note）。

退出码:
    0  成功
    2  用法错误 / case.json 不可读
"""
import argparse
import glob
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

GATING_BUDGET = {"超支"}
GATING_SCHEDULE = {"超出"}
GATING_DOMAIN = {"out_of_domain"}
EMPTY = (None, "", [], {})


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_key(node, pattern):
    if isinstance(node, dict):
        for k, v in node.items():
            if re.search(pattern, str(k), re.IGNORECASE):
                return v
        for v in node.values():
            r = find_key(v, pattern)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_key(v, pattern)
            if r is not None:
                return r
    return None


def contract_fields(case):
    oc = find_key(case, r"output_contract|输出契约")
    if isinstance(oc, dict):
        props = oc.get("properties")
        if isinstance(props, dict):
            return [str(k) for k in props.keys()]
        return [str(k) for k in oc.keys()]
    return []


def case_id_of(case):
    v = find_key(case, r"^case_?id$")
    return str(v) if v is not None else "UNKNOWN_CASE_ID"


def plan_order(case):
    """按 case.json 中候选方案出现顺序返回 plan_id 列表。"""
    plans = find_key(case, r"plan|方案|candidate")
    order = []
    if isinstance(plans, list):
        for p in plans:
            if isinstance(p, dict):
                pid = p.get("plan_id") or p.get("id")
                if pid is not None:
                    order.append(str(pid))
    return order


def collect_artifacts(art_dir):
    plans = {}
    for fp in sorted(glob.glob(str(Path(art_dir) / "*.json"))):
        try:
            data = load_json(fp)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict) or "kind" not in data or "plan_id" not in data:
            continue
        slot = plans.setdefault(str(data["plan_id"]), {})
        slot[data["kind"]] = data
        slot[data["kind"] + "_file"] = fp
    return plans


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def summarize(plans, order):
    """返回 (per_plan_summary, chosen_plan_id, unverified_items)"""
    ordered = [p for p in order if p in plans] + sorted(p for p in plans if p not in order)
    summaries, unverified_all = [], []
    chosen = None
    for pid in ordered:
        slot = plans[pid]
        gating, unv = [], []
        b, s, d = slot.get("budget"), slot.get("schedule"), slot.get("domains")
        if b:
            if b.get("verdict") in GATING_BUDGET:
                gating.append("budget:%s" % b["verdict"])
            unv += b.get("unverified", [])
        else:
            unv.append("缺少预算实算产物")
        if s:
            if s.get("verdict") in GATING_SCHEDULE:
                gating.append("schedule:%s" % s["verdict"])
        else:
            unv.append("缺少进度实算产物")
        dom_counts = {}
        if d:
            dom_counts = d.get("counts", {})
            if dom_counts.get("out_of_domain", 0) > 0:
                gating.append("domains:out_of_domain×%d" % dom_counts["out_of_domain"])
            unv += d.get("unverified", [])
        else:
            unv.append("缺少参数域判定产物")
        unv = ["[%s] %s" % (pid, u) for u in unv]
        summaries.append({
            "plan_id": pid,
            "budget_verdict": (b or {}).get("verdict"),
            "budget_total": str((b or {}).get("total")) if b else None,
            "budget_delta": str((b or {}).get("delta")) if b else None,
            "schedule_verdict": (s or {}).get("verdict"),
            "schedule_total_hours": str((s or {}).get("total_hours")) if s else None,
            "schedule_delta_hours": str((s or {}).get("delta_hours")) if s else None,
            "critical_path": (s or {}).get("critical_path"),
            "domain_counts": dom_counts,
            "gating_fail": bool(gating),
            "gating_reasons": gating,
        })
        unverified_all += unv
        if chosen is None and not gating:
            chosen = pid
    return summaries, chosen, unverified_all


def fill_field(field, chosen, plans, summaries, unverified):
    f = field.lower()
    slot = plans.get(chosen, {}) if chosen else {}
    b, s, d = slot.get("budget"), slot.get("schedule"), slot.get("domains")
    if "chosen" in f and "reason" not in f:
        return chosen
    if "reason" in f:
        if chosen is None:
            return "所有候选方案均触发 gating fail（超支/超期/越域），无可行方案"
        return "首个无 gating fail（未超支/未超期/未越域）的候选方案；其余方案见 per_plan_summary"
    if "budget" in f and "verdict" in f:
        return (b or {}).get("verdict")
    if "budget" in f and "total" in f:
        return fnum((b or {}).get("total"))
    if "budget" in f and "delta" in f:
        return fnum((b or {}).get("delta"))
    if "schedule" in f and "verdict" in f:
        return (s or {}).get("verdict")
    if "schedule" in f and "total" in f:
        return fnum((s or {}).get("total_hours"))
    if "schedule" in f and "delta" in f:
        return fnum((s or {}).get("delta_hours"))
    if "domain" in f and "verdict" in f:
        if not d:
            return None
        c = d.get("counts", {})
        if c.get("out_of_domain", 0):
            return "has_out_of_domain"
        if c.get("no_domain_found", 0) or c.get("unit_unconvertible", 0):
            return "has_unverified"
        return "all_in_domain"
    if "per_plan" in f or ("plan" in f and "summary" in f):
        return summaries
    if "unverified" in f:
        return unverified
    return None


def main(argv):
    ap = argparse.ArgumentParser(description="装配 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", required=True, choices=["complete", "partial", "failed"])
    ap.add_argument("--note", action="append", default=[])
    args = ap.parse_args(argv[1:])

    try:
        case = load_json(args.case)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("错误(exit 2): 无法读取 case.json: %s\n" % exc)
        return 2

    cid = case_id_of(case)
    fields = contract_fields(case)
    plans = collect_artifacts(args.artifacts)
    order = plan_order(case)
    summaries, chosen, unverified = summarize(plans, order)

    existing = {}
    out_path = Path(args.out)
    if out_path.exists():
        try:
            existing = load_json(out_path)
            if not isinstance(existing, dict):
                existing = {}
        except Exception:  # noqa: BLE001
            existing = {}

    result = dict(existing)
    uncertainty = list(result.get("uncertainty") or [])
    if result.get("case_id") in EMPTY:
        result["case_id"] = cid
    elif result["case_id"] != cid:
        uncertainty.append("result.case_id(%s) 与 case.json(%s) 不一致，保留已有值" % (result["case_id"], cid))

    if chosen is None:
        uncertainty.append("所有候选方案均触发 gating fail；chosen_plan_id 置 null，本结果应标记 partial 并说明限制")
        if args.status == "complete":
            uncertainty.append("调用方声明 status=complete 但无可行方案，请复核（脚本不改写 status，如实记录矛盾）")

    for field in fields:
        cur = result.get(field)
        if cur not in EMPTY:
            continue  # 绝不覆盖非空已有值
        val = fill_field(field, chosen, plans, summaries, unverified)
        if val is None and chosen is None and "chosen" in field.lower() and "reason" not in field.lower():
            val = None  # chosen_plan_id 保持 null
        result[field] = val
        if val is None:
            uncertainty.append("contract 字段 '%s' 无法由实算产物填充，置 null（不编造）" % field)

    for n in args.note:
        if n and n not in uncertainty:
            uncertainty.append(n)

    if result.get("status") in EMPTY:
        result["status"] = args.status
    if result.get("sources") in EMPTY:
        src = find_key(case, r"source|来源|material")
        result["sources"] = src if isinstance(src, list) else ([src] if src else [])
    result["uncertainty"] = uncertainty
    cr = list(result.get("change_record") or [])
    cr.append({"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "actor": "assemble_result.py",
               "note": "; ".join(args.note) if args.note else "装配 result.json（status=%s）" % args.status,
               "status": args.status, "chosen_plan_id": chosen})
    result["change_record"] = cr

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("装配完成: %s" % out_path)
    print("  case_id=%s status=%s chosen_plan_id=%s" % (cid, args.status, chosen))
    print("  contract 字段 %d 个: %s" % (len(fields), ", ".join(fields) if fields else "<未找到 output_contract>"))
    if uncertainty:
        print("  uncertainty %d 条:" % len(uncertainty))
        for u in uncertainty:
            print("    - %s" % u)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
