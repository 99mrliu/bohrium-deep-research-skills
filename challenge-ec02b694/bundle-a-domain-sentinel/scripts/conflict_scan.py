#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
conflict_scan.py — 可行域内部一致性扫描（domain-sentinel 第 2 步）

输入：
  --domain  extract_domain.py 生成的 domain.json
  --out     conflicts.json 输出路径

检查项（每条冲突给出 recommended_action: degrade / handoff / terminate）：
  1) inverted_bounds           单条约束 lower > upper                      -> handoff
  2) effective_bounds_inverted 多来源合并后 max(lower) > min(upper)        -> handoff
  3) target_outside_domain     case 目标值越出可行域（安全相关 -> terminate，
                               否则 -> degrade：以约束界限替代并显式声明）
  4) ungrounded_target         目标参数在 domain 中无任何约束依据           -> handoff
  5) invalid_step              step <= 0 或步进使区间无可达格点             -> handoff
  6) mutex_degenerate          互斥组只有一个成员（语义不完整）             -> degrade
  7) mutex_unsatisfiable       互斥组中 >=2 个成员被固定为单点值            -> handoff

退出码：0 = 无冲突；3 = 发现冲突；1 = 参数级错误（仍尝试落盘）。
任何输入不得 traceback 崩溃。
"""
import json
import os
import sys

SCHEMA_VERSION = "1.0"
TOL = 1e-9


def normalize_name(name):
    if not name:
        return ""
    return "".join(str(name).split()).lower().replace("_", "")


def to_float(x):
    try:
        if x is None or isinstance(x, bool):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def evidence_of(c):
    return (c or {}).get("source")


def scan(domain):
    conflicts = []
    constraints = (domain or {}).get("constraints", []) or []
    targets = (domain or {}).get("targets", {}) or {}
    by_param = {}
    for c in constraints:
        if not isinstance(c, dict):
            continue
        name = c.get("parameter")
        if name:
            by_param.setdefault(normalize_name(name), []).append(c)

    # 1) 单条倒置
    for c in constraints:
        lo, hi = to_float(c.get("lower")), to_float(c.get("upper"))
        if lo is not None and hi is not None and lo > hi + TOL:
            conflicts.append({
                "type": "inverted_bounds",
                "parameters": [c.get("parameter")],
                "detail": u"单条约束 lower(%s) > upper(%s)" % (lo, hi),
                "evidence": evidence_of(c),
                "recommended_action": "handoff",
            })

    # 2) 合并后倒置
    merged = {}
    for norm, entries in by_param.items():
        lowers = [to_float(e.get("lower")) for e in entries]
        lowers = [v for v in lowers if v is not None]
        uppers = [to_float(e.get("upper")) for e in entries]
        uppers = [v for v in uppers if v is not None]
        lo = max(lowers) if lowers else None
        hi = min(uppers) if uppers else None
        merged[norm] = (lo, hi, entries)
        if lo is not None and hi is not None and lo > hi + TOL:
            conflicts.append({
                "type": "effective_bounds_inverted",
                "parameters": [entries[0].get("parameter")],
                "detail": u"多来源合并后 max(lower)=%s > min(upper)=%s，可行域为空" % (lo, hi),
                "evidence": [evidence_of(e) for e in entries],
                "recommended_action": "handoff",
            })

    # 3)/4) 目标值检查
    for tname, tval in targets.items():
        tv = to_float(tval)
        if tv is None:
            continue
        norm = normalize_name(tname)
        if norm not in merged:
            conflicts.append({
                "type": "ungrounded_target",
                "parameters": [tname],
                "detail": u"目标值 %s=%s 在 domain 中无任何约束依据，无法验证可行性" % (tname, tv),
                "evidence": None,
                "recommended_action": "handoff",
            })
            continue
        lo, hi, entries = merged[norm]
        outside = (lo is not None and tv < lo - TOL) or (hi is not None and tv > hi + TOL)
        if outside:
            safety = any(e.get("safety_related") for e in entries)
            conflicts.append({
                "type": "target_outside_domain",
                "parameters": [entries[0].get("parameter")],
                "detail": u"目标值 %s 越出可行域 [%s, %s]%s" % (
                    tv, lo, hi, u"（涉及安全/耐温约束）" if safety else ""),
                "evidence": [evidence_of(e) for e in entries],
                "recommended_action": "terminate" if safety else "degrade",
            })

    # 5) 步进
    for c in constraints:
        s = to_float(c.get("step"))
        if s is None:
            continue
        if s <= 0:
            conflicts.append({
                "type": "invalid_step",
                "parameters": [c.get("parameter")],
                "detail": u"step <= 0 (%s)" % s,
                "evidence": evidence_of(c),
                "recommended_action": "handoff",
            })
            continue
        lo, hi = to_float(c.get("lower")), to_float(c.get("upper"))
        if lo is not None and hi is not None and hi >= lo:
            import math
            n = int(math.floor((hi - lo) / s + TOL)) + 1
            if n < 1:
                conflicts.append({
                    "type": "invalid_step",
                    "parameters": [c.get("parameter")],
                    "detail": u"区间 [%s, %s] 内无步进 %s 可达的格点" % (lo, hi, s),
                    "evidence": evidence_of(c),
                    "recommended_action": "handoff",
                })

    # 6)/7) 互斥
    groups = {}
    for c in constraints:
        g = c.get("mutex_group")
        if g:
            groups.setdefault(str(g), []).append(c)
    for g, members in groups.items():
        uniq = {normalize_name(m.get("parameter")): m for m in members}
        if len(uniq) < 2:
            conflicts.append({
                "type": "mutex_degenerate",
                "parameters": [m.get("parameter") for m in members],
                "detail": u"互斥组 '%s' 仅 %d 个成员，语义不完整" % (g, len(uniq)),
                "evidence": [evidence_of(m) for m in members],
                "recommended_action": "degrade",
            })
            continue
        fixed = []
        for norm, m in uniq.items():
            lo, hi = to_float(m.get("lower")), to_float(m.get("upper"))
            if lo is not None and hi is not None and abs(lo - hi) <= TOL:
                fixed.append(m.get("parameter"))
        if len(fixed) >= 2:
            conflicts.append({
                "type": "mutex_unsatisfiable",
                "parameters": fixed,
                "detail": u"互斥组 '%s' 中 %d 个成员被固定为单点值，无法同时满足" % (g, len(fixed)),
                "evidence": [evidence_of(m) for m in members],
                "recommended_action": "handoff",
            })
    return conflicts


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="domain-sentinel: 可行域一致性扫描")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--out", default="/app/output/conflicts.json")
    args = parser.parse_args(argv)

    domain, err = None, None
    try:
        with open(args.domain, "r", encoding="utf-8") as f:
            domain = json.load(f)
    except Exception as e:
        err = "%s: %s" % (args.domain, e)

    if err:
        out = {"schema_version": SCHEMA_VERSION, "generated_by": "conflict_scan.py",
               "status": "error", "errors": [err], "conflicts": []}
        code = 1
    else:
        conflicts = scan(domain)
        out = {"schema_version": SCHEMA_VERSION, "generated_by": "conflict_scan.py",
               "domain_file": args.domain,
               "status": "conflicts_found" if conflicts else "ok",
               "summary": {"conflict_count": len(conflicts),
                           "by_action": {
                               "degrade": sum(1 for c in conflicts if c["recommended_action"] == "degrade"),
                               "handoff": sum(1 for c in conflicts if c["recommended_action"] == "handoff"),
                               "terminate": sum(1 for c in conflicts if c["recommended_action"] == "terminate"),
                           }},
               "conflicts": conflicts}
        code = 3 if conflicts else 0

    try:
        outdir = os.path.dirname(os.path.abspath(args.out))
        if outdir and not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stderr.write("conflict_scan: 无法写出 %s: %s\n" % (args.out, e))
        return 1
    sys.stderr.write("conflict_scan: %s (%d conflicts) -> %s (exit %d)\n"
                     % (out["status"], len(out.get("conflicts", [])), args.out, code))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # 兜底：绝不 traceback 崩溃
        sys.stderr.write("conflict_scan: 未捕获异常（已抑制 traceback）: %s\n" % e)
        sys.exit(1)
