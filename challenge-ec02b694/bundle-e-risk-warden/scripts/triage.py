#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""triage.py — 异常分流（risk-warden 第二步）。

输入：案例状态事实 JSON（由 Agent 汇总），字段（均为可选，缺省视为空）：
  {
    "case_id": "...",                       # 可选
    "feasible": true/false,                 # 可选；false 视为无可行解
    "constraint_conflicts":  [{"id","description","resolvable":true/false,"evidence"}],
    "infeasible_constraints":[{"id","description","evidence"}],
    "missing_materials":     [{"path","critical":true/false,"reason"}],
    "metric_conflicts":      [{"description","critical":true/false,"evidence"}],
    "device_errors":         [{"code","severity":"fatal"/"recoverable","description"}],
    "permission_issues":     [{"description","evidence"}]
  }

显式规则矩阵（按序评估，全部命中均记录；最终动作取优先级最高者）：
  R_PERM_01 permission_issues 非空                       -> handoff_to_human        (permission_issue)
  R_DEV_01  存在 severity=fatal 的 device_errors          -> terminate               (device_error)
  R_DEV_02  device_errors 非空且均可恢复                  -> proceed_with_degradation (device_error)
  R_INF_01  infeasible_constraints 非空 或 feasible=false -> terminate               (infeasible_constraints)
  R_CON_01  存在 resolvable=false 的约束冲突              -> handoff_to_human        (constraint_conflict)
  R_CON_02  约束冲突全部可消解                            -> proceed_with_degradation (constraint_conflict)
  R_MIS_01  存在 critical=true 的缺失材料                 -> handoff_to_human        (missing_data)
  R_MIS_02  缺失材料均非关键                              -> proceed_with_degradation (missing_data)
  R_MET_01  存在 critical=true 的指标矛盾                 -> handoff_to_human        (metric_conflict)
  R_MET_02  指标矛盾均非关键                              -> proceed_with_degradation (metric_conflict)
  R_OK_01   未命中任何上述规则                            -> proceed                  (feasible)

动作优先级：terminate > handoff_to_human > proceed_with_degradation > proceed

输出：triage.json，含触发的每条规则 {rule_id, condition, evidence, action} 与最终动作。
退出码：最终动作为 handoff_to_human 或 terminate 时 exit 3；否则 exit 0。
输入缺失/不可解析时：写出 R0_FACTS_UNREADABLE -> handoff_to_human 的 triage.json 并 exit 3。
任何输入不得产生 traceback。
"""
import argparse
import json
import os
import sys
import time

EXIT_OK = 0
EXIT_ESCALATE = 3

PRIORITY = {"proceed": 0, "proceed_with_degradation": 1, "handoff_to_human": 2, "terminate": 3}

LIST_FIELDS = ("constraint_conflicts", "infeasible_constraints", "missing_materials",
               "metric_conflicts", "device_errors", "permission_issues")


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def as_list(v):
    return v if isinstance(v, list) else []


def brief(items, limit=5):
    """把触发现场的条目压缩成可写入证据的短文本。"""
    out = []
    for it in items[:limit]:
        try:
            out.append(json.dumps(it, ensure_ascii=False)[:200])
        except Exception:  # noqa: BLE001
            out.append(str(it)[:200])
    if len(items) > limit:
        out.append("... 共 %d 条" % len(items))
    return out


def load_facts(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None, "事实 JSON 顶层不是对象"
        return data, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def evaluate(facts):
    """返回 (triggered_rules, final_action, final_category)。"""
    triggered = []

    def hit(rule_id, condition, evidence, action, category):
        triggered.append({
            "rule_id": rule_id,
            "category": category,
            "condition": condition,
            "evidence": evidence,
            "action": action,
        })

    perms = as_list(facts.get("permission_issues"))
    devs = as_list(facts.get("device_errors"))
    infs = as_list(facts.get("infeasible_constraints"))
    cons = as_list(facts.get("constraint_conflicts"))
    miss = as_list(facts.get("missing_materials"))
    mets = as_list(facts.get("metric_conflicts"))

    if perms:
        hit("R_PERM_01", "permission_issues 非空", brief(perms),
            "handoff_to_human", "permission_issue")

    fatal_devs = [d for d in devs if isinstance(d, dict) and d.get("severity") == "fatal"]
    if fatal_devs:
        hit("R_DEV_01", "存在 severity=fatal 的设备报错", brief(fatal_devs),
            "terminate", "device_error")
    elif devs:
        hit("R_DEV_02", "device_errors 非空且均可恢复", brief(devs),
            "proceed_with_degradation", "device_error")

    if infs or facts.get("feasible") is False:
        ev = brief(infs) if infs else ["facts.feasible == false"]
        hit("R_INF_01", "infeasible_constraints 非空 或 feasible=false（无可行解）", ev,
            "terminate", "infeasible_constraints")

    unresolvable = [c for c in cons if isinstance(c, dict) and c.get("resolvable") is False]
    if unresolvable:
        hit("R_CON_01", "存在 resolvable=false 的约束冲突（消解需改变既定目标，须人裁决）",
            brief(unresolvable), "handoff_to_human", "constraint_conflict")
    elif cons:
        hit("R_CON_02", "约束冲突全部 resolvable=true（可降级消解）", brief(cons),
            "proceed_with_degradation", "constraint_conflict")

    critical_miss = [m for m in miss if isinstance(m, dict) and m.get("critical") is True]
    if critical_miss:
        hit("R_MIS_01", "存在 critical=true 的缺失材料", brief(critical_miss),
            "handoff_to_human", "missing_data")
    elif miss:
        hit("R_MIS_02", "缺失材料均非关键", brief(miss),
            "proceed_with_degradation", "missing_data")

    critical_mets = [m for m in mets if isinstance(m, dict) and m.get("critical") is True]
    if critical_mets:
        hit("R_MET_01", "存在 critical=true 的指标矛盾", brief(critical_mets),
            "handoff_to_human", "metric_conflict")
    elif mets:
        hit("R_MET_02", "指标矛盾均非关键", brief(mets),
            "proceed_with_degradation", "metric_conflict")

    if not triggered:
        hit("R_OK_01", "未命中任何异常规则", [], "proceed", "feasible")

    final = max(triggered, key=lambda r: PRIORITY.get(r["action"], 0))
    return triggered, final["action"], final["category"]


def safe_write_json(path, obj):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[triage] 写文件失败 %s: %s\n" % (path, exc))
        return False


def main():
    ap = argparse.ArgumentParser(description="risk-warden 异常分流")
    ap.add_argument("--facts", required=True, help="案例状态事实 JSON 路径")
    ap.add_argument("--out", default="triage.json", help="triage.json 输出路径")
    args = ap.parse_args()

    facts, err = load_facts(args.facts)
    if facts is None:
        report = {
            "generated_at": utc_now(),
            "case_id": "unknown",
            "triggered_rules": [{
                "rule_id": "R0_FACTS_UNREADABLE",
                "category": "missing_data",
                "condition": "事实 JSON 缺失或不可解析，无法判定可继续性",
                "evidence": [err or "unknown error"],
                "action": "handoff_to_human",
            }],
            "final_action": "handoff_to_human",
            "final_category": "missing_data",
            "note": "事实不可读时一律转人工，绝不默许继续",
        }
        safe_write_json(args.out, report)
        sys.stderr.write("[triage] 事实 JSON 不可读: %s\n" % err)
        return EXIT_ESCALATE

    # 归一化：非 list 的字段视为空，绝不崩溃
    for k in LIST_FIELDS:
        if k in facts and not isinstance(facts[k], list):
            facts[k] = []

    triggered, final_action, final_category = evaluate(facts)
    report = {
        "generated_at": utc_now(),
        "case_id": facts.get("case_id", "unknown"),
        "triggered_rules": triggered,
        "final_action": final_action,
        "final_category": final_category,
        "note": {
            "proceed": "无可判定异常，可继续主体工作",
            "proceed_with_degradation": "允许降级继续：必须在 result.json 的 uncertainty/change_log 中记录降级内容",
            "handoff_to_human": "转人工：停止自主决策，写明待裁决事项后交付 partial",
            "terminate": "终止：无可行解或致命设备故障，写明终止理由，status=unable_to_determine 或 partial",
        }[final_action],
    }
    safe_write_json(args.out, report)
    sys.stdout.write("[triage] final_action=%s rules=%d\n" % (final_action, len(triggered)))
    return EXIT_ESCALATE if final_action in ("handoff_to_human", "terminate") else EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 —— 兜底：任何输入不得 traceback
        sys.stderr.write("[triage] 未预期异常（已捕获，不崩溃）: %s\n" % exc)
        safe_write_json(os.path.abspath("triage.json"), {
            "generated_at": utc_now(),
            "case_id": "unknown",
            "triggered_rules": [{
                "rule_id": "R0_INTERNAL_ERROR", "category": "missing_data",
                "condition": "triage 内部异常", "evidence": [str(exc)],
                "action": "handoff_to_human",
            }],
            "final_action": "handoff_to_human",
            "final_category": "missing_data",
            "note": "triage 自身异常时一律转人工",
        })
        sys.exit(EXIT_ESCALATE)
