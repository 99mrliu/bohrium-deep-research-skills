#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
domain_audit.py — 硬闸门审计器（domain-sentinel 第 3 步，提交前必过）

输入：
  --domain    extract_domain.py 生成的 domain.json
  --proposal  拟提交方案 JSON：{"parameters": {参数名: 值}} 或扁平 {参数名: 值}
              值支持四种形态：数值 / {"value": v} / [lo, hi] / {"range": [lo, hi]}
  --out       audit_report.json 输出路径

逐参数核验：
  1) grounded：参数必须存在于 domain，否则 verdict=ungrounded（按违规处理）；
  2) bounds：值（或区间两端点）必须落在合并后的 [lower, upper] 内
     （多来源时取最紧：lower=max, upper=min）；
  3) step：值必须落在以 lower（无 lower 时以 0）为基准、step 为间隔的格点上，
     存在多个 step 依据时必须同时满足；
  4) mutex：同一 mutex_group 的成员不得在方案中同时被赋非空值。

退出码：0 = 全部通过；3 = 任一 violation/ungrounded；1 = 参数级错误（仍尝试落盘）。
任何输入不得 traceback 崩溃。
"""
import json
import os
import sys

SCHEMA_VERSION = "1.0"
META_KEYS = {"case_id", "status", "notes", "sources", "uncertainty",
             "change_log", "gate", "schema_version"}
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


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, "%s: %s" % (path, e)


def index_domain(domain):
    """参数（规范化名）-> 约束条目列表；mutex 组 -> 成员集合。"""
    by_param, mutex_groups = {}, {}
    for c in (domain or {}).get("constraints", []) or []:
        if not isinstance(c, dict):
            continue
        name = c.get("parameter")
        if not name or name == u"__mutex_note__":
            continue
        by_param.setdefault(normalize_name(name), []).append(c)
        g = c.get("mutex_group")
        if g:
            mutex_groups.setdefault(str(g), set()).add(normalize_name(name))
    return by_param, mutex_groups


def effective_bounds(entries):
    lowers = [to_float(e.get("lower")) for e in entries]
    lowers = [v for v in lowers if v is not None]
    uppers = [to_float(e.get("upper")) for e in entries]
    uppers = [v for v in uppers if v is not None]
    steps = [to_float(e.get("step")) for e in entries]
    steps = [v for v in steps if v is not None and v > 0]
    lower = max(lowers) if lowers else None
    upper = min(uppers) if uppers else None
    return lower, upper, steps


def binding_entry(entries, key, fn):
    """返回提供生效界限（最紧）的那条约束，用于证据定位。"""
    cand = [(to_float(e.get(key)), e) for e in entries]
    cand = [(v, e) for v, e in cand if v is not None]
    if not cand:
        return None
    return fn(cand, key=lambda t: t[0])[1]


def parse_proposal_values(proposal):
    """返回 {参数名: [数值, ...]}（区间展开为端点），以及原始描述。"""
    if not isinstance(proposal, dict):
        return {}, {}
    params = proposal.get("parameters")
    if not isinstance(params, dict):
        params = {k: v for k, v in proposal.items() if k not in META_KEYS}
    values, raw = {}, {}
    for name, spec in params.items():
        pts = []
        if isinstance(spec, (int, float)) and not isinstance(spec, bool):
            pts = [float(spec)]
        elif isinstance(spec, dict):
            v = to_float(spec.get("value"))
            if v is not None:
                pts = [v]
            else:
                rng = spec.get("range")
                if isinstance(rng, (list, tuple)) and len(rng) == 2:
                    a, b = to_float(rng[0]), to_float(rng[1])
                    pts = [x for x in (a, b) if x is not None]
                else:
                    a, b = to_float(spec.get("min")), to_float(spec.get("max"))
                    pts = [x for x in (a, b) if x is not None]
        elif isinstance(spec, (list, tuple)) and len(spec) == 2:
            a, b = to_float(spec[0]), to_float(spec[1])
            pts = [x for x in (a, b) if x is not None]
        values[str(name)] = pts
        raw[str(name)] = spec
    return values, raw


def step_ok(value, step, base):
    k = (value - base) / step
    return abs(k - round(k)) <= TOL * max(1.0, abs(k))


def audit(domain, proposal):
    by_param, mutex_groups = index_domain(domain)
    values, raw = parse_proposal_values(proposal)
    results = []

    # 互斥预检：同组 >=2 个成员被提案
    proposed_norm = {normalize_name(n): n for n in values if values[n]}
    mutex_violators = {}
    for group, members in mutex_groups.items():
        hit = sorted(m for m in members if m in proposed_norm)
        if len(hit) >= 2:
            for m in hit:
                mutex_violators.setdefault(m, []).append(group)

    for name, pts in values.items():
        checks = []
        verdict = "pass"
        norm = normalize_name(name)
        entries = by_param.get(norm)

        if not entries:
            results.append({
                "parameter": name,
                "proposed": raw.get(name),
                "verdict": "ungrounded",
                "checks": [{
                    "check": "grounded",
                    "passed": False,
                    "detail": u"参数不存在于 domain.json：无约束依据，按违规处理；"
                              u"请回到材料中定位证据，或从方案中移除该参数",
                    "evidence": None,
                }],
            })
            continue

        lower, upper, steps = effective_bounds(entries)
        lo_entry = binding_entry(entries, "lower", max)
        hi_entry = binding_entry(entries, "upper", min)
        step_entries = [e for e in entries if to_float(e.get("step"))]

        if not pts:
            verdict = "violation"
            checks.append({"check": "parse", "passed": False,
                           "detail": u"无法解析的建议值形态（支持 数值/{value}/[lo,hi]/{range})",
                           "evidence": None})
        for v in pts:
            if lower is not None and v < lower - TOL:
                verdict = "violation"
                checks.append({
                    "check": "lower_bound", "passed": False,
                    "detail": u"%s < 下限 %s %s" % (v, lower, (entries[0].get("unit") or "")),
                    "evidence": (lo_entry or entries[0]).get("source"),
                })
            if upper is not None and v > upper + TOL:
                verdict = "violation"
                checks.append({
                    "check": "upper_bound", "passed": False,
                    "detail": u"%s > 上限 %s %s" % (v, upper, (entries[0].get("unit") or "")),
                    "evidence": (hi_entry or entries[0]).get("source"),
                })
            base = lower if lower is not None else 0.0
            for s, se in zip(steps, step_entries):
                if not step_ok(v, s, base):
                    verdict = "violation"
                    checks.append({
                        "check": "step", "passed": False,
                        "detail": u"%s 不满足步进 %s（基准 %s）" % (v, s, base),
                        "evidence": se.get("source"),
                    })
        if norm in mutex_violators:
            verdict = "violation"
            groups = mutex_violators[norm]
            checks.append({
                "check": "mutex", "passed": False,
                "detail": u"互斥组 %s 中多个成员被同时赋值" % groups,
                "evidence": next((e.get("source") for e in entries
                                  if e.get("mutex_group") in groups), entries[0].get("source")),
            })
        if not checks:
            checks.append({
                "check": "bounds+step+mutex", "passed": True,
                "detail": u"在可行域内（lower=%s, upper=%s, steps=%s）" % (lower, upper, steps),
                "evidence": (hi_entry or lo_entry or entries[0]).get("source"),
            })
        results.append({"parameter": name, "proposed": raw.get(name),
                        "verdict": verdict, "checks": checks})

    n_v = sum(1 for r in results if r["verdict"] == "violation")
    n_u = sum(1 for r in results if r["verdict"] == "ungrounded")
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "domain_audit.py",
        "results": results,
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r["verdict"] == "pass"),
            "violation": n_v,
            "ungrounded": n_u,
        },
        "status": "fail" if (n_v or n_u) else "pass",
    }
    return report


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="domain-sentinel: 硬闸门审计")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--out", default="/app/output/audit_report.json")
    args = parser.parse_args(argv)

    domain, err1 = load_json(args.domain)
    proposal, err2 = load_json(args.proposal)
    fatal = [e for e in (err1, err2) if e]
    if fatal:
        report = {"schema_version": SCHEMA_VERSION, "generated_by": "domain_audit.py",
                  "results": [], "summary": {"total": 0, "pass": 0, "violation": 0,
                                             "ungrounded": 0},
                  "status": "fail",
                  "errors": fatal}
        code = 3
    else:
        report = audit(domain, proposal)
        report["domain_file"] = args.domain
        report["proposal_file"] = args.proposal
        code = 0 if report["status"] == "pass" else 3

    try:
        outdir = os.path.dirname(os.path.abspath(args.out))
        if outdir and not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stderr.write("domain_audit: 无法写出 %s: %s\n" % (args.out, e))
        return 1
    sys.stderr.write("domain_audit: status=%s violations=%d ungrounded=%d -> %s (exit %d)\n"
                     % (report["status"], report["summary"]["violation"],
                        report["summary"]["ungrounded"], args.out, code))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # 兜底：绝不 traceback 崩溃
        sys.stderr.write("domain_audit: 未捕获异常（已抑制 traceback）: %s\n" % e)
        sys.exit(1)
