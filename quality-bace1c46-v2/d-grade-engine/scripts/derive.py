#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""derive.py — 由维度级判定按版本化量表派生域级与总评等级。

用法:
    python3 derive.py --verdicts verdicts.jsonl --workdir /app/work [--scale thresholds.json]

判定行 (verdicts.jsonl, 每行一个 JSON 对象):
    {"doc_id": "...", "dimension": "design_adequacy", "level": "low_concern",
     "evidence_ref": "可选", "note": "可选"}

行为契约:
    - 维度 id / 等级 一律对照量表校验; 未知者写入 workdir/rejected_verdicts.jsonl
      并给出 reason, 运行继续 (绝不静默丢弃, 也绝不中止)。
    - 所有聚合仅由量表规则完成 (按序求值, 首个命中生效), 本脚本不含任何
      硬编码阈值; 一切阈值来自 scale 文件。
    - 弃权 (insufficient_evidence) 按量表 abstain_policy 沿链传播, 绝不平均。
    - 每个发出的等级都携带 derivation_chain (规则 id + 输入计数)。
    - 输出: workdir/grades.json, workdir/derivation_report.md,
      workdir/rejected_verdicts.jsonl (可能为空)。

退出码: 0 = 正常完成; 1 = 运行期错误; 2 = 用法/输入文件错误。
仅依赖 Python 3 标准库。
"""

import argparse
import json
import os
import sys
import datetime

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2

LEVEL_IDS = None  # 由量表装载后填充


def log(msg):
    sys.stderr.write("[derive] %s\n" % msg)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_scale_path():
    # 相对脚本文件解析, 使安装后的 bundle 无需额外配置即可找到量表。
    return os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "references", "thresholds.json"))


def load_scale(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            scale = json.load(f)
    except FileNotFoundError:
        log("量表文件不存在: %s" % path)
        sys.exit(EXIT_USAGE)
    except (OSError, json.JSONDecodeError) as e:
        log("量表文件读取/解析失败: %s: %s" % (path, e))
        sys.exit(EXIT_USAGE)
    for key in ("scale_version", "levels", "dimensions", "domains",
                "domain_rules", "overall_rules", "fallback_rules"):
        if key not in scale:
            log("量表缺少必需键: %s" % key)
            sys.exit(EXIT_USAGE)
    return scale


def read_verdicts(path, scale):
    """读取并校验 verdicts.jsonl。返回 (accepted, rejected)。

    accepted: dict doc_id -> {dimension: row}; rejected: list of dict。
    """
    dim_ids = {d["id"] for d in scale["dimensions"]}
    level_ids = {lv["id"] for lv in scale["levels"]}
    accepted, rejected = {}, []
    try:
        f = open(path, "r", encoding="utf-8")
    except FileNotFoundError:
        log("判定文件不存在: %s" % path)
        sys.exit(EXIT_USAGE)
    except OSError as e:
        log("判定文件读取失败: %s: %s" % (path, e))
        sys.exit(EXIT_USAGE)
    with f:
        for lineno, line in enumerate(f, 1):
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as e:
                rejected.append({"line": lineno, "raw": raw[:200],
                                 "reason": "invalid_json: %s" % e})
                continue
            if not isinstance(row, dict):
                rejected.append({"line": lineno, "raw": raw[:200],
                                 "reason": "not_a_json_object"})
                continue
            doc_id = row.get("doc_id")
            dim = row.get("dimension")
            level = row.get("level")
            if not isinstance(doc_id, str) or not doc_id.strip():
                rejected.append({"line": lineno, "row": row,
                                 "reason": "missing_or_invalid_doc_id"})
                continue
            if dim not in dim_ids:
                rejected.append({"line": lineno, "row": row,
                                 "reason": "unknown_dimension: %r (量表未定义)" % dim})
                continue
            if level not in level_ids:
                rejected.append({"line": lineno, "row": row,
                                 "reason": "unknown_level: %r (量表未定义)" % level})
                continue
            doc = accepted.setdefault(doc_id, {})
            if dim in doc:
                rejected.append({"line": lineno, "row": row,
                                 "reason": "duplicate_verdict: (%s, %s) 已存在, 保留首条"
                                           % (doc_id, dim)})
                continue
            doc[dim] = {"dimension": dim, "level": level,
                        "evidence_ref": row.get("evidence_ref"),
                        "note": row.get("note")}
    return accepted, rejected


# ---------------- 规则求值器: 所有条件类型均来自量表文件 ----------------

def _domain_pool(scale, selector):
    domains = scale["domains"]
    if selector == "core":
        return [d for d in domains if d.get("core")]
    if selector == "non_core":
        return [d for d in domains if not d.get("core")]
    return list(domains)


def eval_domain_rule(cond, member_levels):
    """member_levels: list of level ids (仅含已提交判定的成员)。"""
    if "any_member_level" in cond:
        return cond["any_member_level"] in member_levels
    if "all_member_level" in cond:
        return bool(member_levels) and all(
            lv == cond["all_member_level"] for lv in member_levels)
    return False


def eval_overall_rule(cond, dim_levels, domain_grades, scale):
    if "min_count_dimension_level" in cond:
        spec = cond["min_count_dimension_level"]
        return sum(1 for lv in dim_levels if lv == spec["level"]) >= spec["min"]
    if "min_count_domain_level" in cond:
        spec = cond["min_count_domain_level"]
        pool = _domain_pool(scale, spec.get("domains", "all"))
        return sum(1 for d in pool
                   if domain_grades.get(d["id"], {}).get("grade") == spec["level"]) >= spec["min"]
    if "any_domain_level" in cond:
        pool = _domain_pool(scale, cond.get("domains", "all"))
        return any(domain_grades.get(d["id"], {}).get("grade") == cond["any_domain_level"]
                   for d in pool)
    if "all_domain_level" in cond:
        pool = _domain_pool(scale, cond.get("domains", "all"))
        return bool(pool) and all(
            domain_grades.get(d["id"], {}).get("grade") == cond["all_domain_level"]
            for d in pool)
    return False


def rule_inputs_domain(rule, domain, verdicts):
    counts = {}
    for m in domain["members"]:
        lv = verdicts.get(m, {}).get("level")
        if lv is not None:
            counts[lv] = counts.get(lv, 0) + 1
    return {"domain": domain["id"], "members": domain["members"],
            "member_level_counts": counts}


def rule_inputs_overall(rule, dim_levels, domain_grades, scale):
    dim_counts = {}
    for lv in dim_levels:
        dim_counts[lv] = dim_counts.get(lv, 0) + 1
    return {"dimension_level_counts": dim_counts,
            "domain_grades": {k: v.get("grade") for k, v in domain_grades.items()},
            "condition": rule.get("if")}


def derive_doc(doc_id, verdicts, scale):
    """对单篇文献执行 维度→域→总评 推导, 返回结构化结果。"""
    chain = []
    # 缺失维度: 已定义但未提交判定的维度
    all_dims = [d["id"] for d in scale["dimensions"]]
    missing = [d for d in all_dims if d not in verdicts]

    # 1) 域级
    domain_grades = {}
    for domain in scale["domains"]:
        member_levels = [verdicts[m]["level"] for m in domain["members"] if m in verdicts]
        fired, grade = None, None
        for rule in scale["domain_rules"]:
            if eval_domain_rule(rule["if"], member_levels):
                fired, grade = rule, rule["then"]
                break
        if fired is None:
            fb = scale["fallback_rules"]["domain"]
            fired, grade = {"id": fb["id"], "description_zh": fb["description_zh"],
                            "if": None}, fb["then"]
        entry = {"stage": "domain", "target": domain["id"],
                 "rule_id": fired["id"],
                 "description_zh": fired.get("description_zh"),
                 "inputs": rule_inputs_domain(fired, domain, verdicts),
                 "output": grade}
        chain.append(entry)
        domain_grades[domain["id"]] = {"grade": grade, "derivation": entry}

    # 2) 总评
    dim_levels = [v["level"] for v in verdicts.values()]
    fired, overall = None, None
    for rule in scale["overall_rules"]:
        if eval_overall_rule(rule["if"], dim_levels, domain_grades, scale):
            fired, overall = rule, rule["then"]
            break
    if fired is None:
        fb = scale["fallback_rules"]["overall"]
        fired, overall = {"id": fb["id"], "description_zh": fb["description_zh"],
                          "if": None}, fb["then"]
    ov_entry = {"stage": "overall", "target": "overall",
                "rule_id": fired["id"],
                "description_zh": fired.get("description_zh"),
                "inputs": rule_inputs_overall(fired, dim_levels, domain_grades, scale),
                "output": overall}
    chain.append(ov_entry)

    return {
        "doc_id": doc_id,
        "dimension_verdicts": [verdicts[d] for d in all_dims if d in verdicts],
        "missing_dimensions": missing,
        "domain_grades": domain_grades,
        "overall_grade": overall,
        "derivation_chain": chain,
        "scale_version": scale["scale_version"],
    }


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_change_record(workdir, action, detail):
    rec = {"ts": now_iso(), "actor": "d-grade-engine/scripts/derive.py",
           "action": action, "detail": detail}
    try:
        with open(os.path.join(workdir, "change_records.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        log("change_records 写入失败 (不致命): %s" % e)


def render_report(results, rejected, scale):
    lines = ["# 等级推导报告 (derivation report)", "",
             "- 量表版本: `%s`" % scale["scale_version"],
             "- 文献数: %d" % len(results),
             "- 被拒绝判定行: %d" % len(rejected), ""]
    for r in results:
        lines.append("## %s → 总评: **%s**" % (r["doc_id"], r["overall_grade"]))
        if r["missing_dimensions"]:
            lines.append("- 缺失维度判定: %s" % ", ".join(r["missing_dimensions"]))
        lines.append("- 维度判定:")
        for v in r["dimension_verdicts"]:
            ev = " (证据: %s)" % v["evidence_ref"] if v.get("evidence_ref") else ""
            lines.append("  - `%s` = **%s**%s" % (v["dimension"], v["level"], ev))
        lines.append("- 推导链:")
        for e in r["derivation_chain"]:
            lines.append("  - [%s] `%s` ← 规则 `%s`: %s | 输入: `%s`" % (
                e["stage"], e["target"], e["rule_id"], e.get("description_zh"),
                json.dumps(e["inputs"], ensure_ascii=False)))
        lines.append("")
    if rejected:
        lines.append("## 被拒绝的判定行")
        for rj in rejected:
            lines.append("- 行 %s: %s" % (rj.get("line", "?"), rj.get("reason")))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="按版本化量表从维度判定派生域级与总评等级")
    ap.add_argument("--verdicts", required=True, help="verdicts.jsonl 路径")
    ap.add_argument("--workdir", required=True, help="工作目录 (输出写于此)")
    ap.add_argument("--scale", default=default_scale_path(),
                    help="量表 thresholds.json 路径 (默认: 相对脚本解析)")
    args = ap.parse_args(argv)  # argparse 用法错误自动 exit 2

    os.makedirs(args.workdir, exist_ok=True)
    scale = load_scale(args.scale)
    accepted, rejected = read_verdicts(args.verdicts, scale)

    rej_path = os.path.join(args.workdir, "rejected_verdicts.jsonl")
    with open(rej_path, "w", encoding="utf-8") as f:
        for rj in rejected:
            f.write(json.dumps(rj, ensure_ascii=False) + "\n")
    if rejected:
        log("已拒绝 %d 条非法判定, 详见 %s (运行继续)" % (len(rejected), rej_path))

    results = []
    for doc_id in sorted(accepted):
        try:
            results.append(derive_doc(doc_id, accepted[doc_id], scale))
        except Exception as e:  # 防御: 单篇失败不影响其余
            log("doc %s 推导失败: %s" % (doc_id, e))
            results.append({"doc_id": doc_id, "error": str(e),
                            "dimension_verdicts": [], "missing_dimensions": [],
                            "domain_grades": {}, "overall_grade": None,
                            "derivation_chain": [],
                            "scale_version": scale["scale_version"]})

    out = {"scale_version": scale["scale_version"],
           "verdicts_file": os.path.abspath(args.verdicts),
           "docs": results,
           "rejected_count": len(rejected),
           "generated_at": now_iso()}
    write_json(os.path.join(args.workdir, "grades.json"), out)
    with open(os.path.join(args.workdir, "derivation_report.md"), "w", encoding="utf-8") as f:
        f.write(render_report(results, rejected, scale))
    append_change_record(args.workdir, "derive_grades",
                         "docs=%d, rejected=%d, scale=%s"
                         % (len(results), len(rejected), scale["scale_version"]))
    log("完成: %d 篇文献, %d 条拒绝; 输出于 %s" % (len(results), len(rejected), args.workdir))
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        log("未预期错误: %s" % e)
        sys.exit(EXIT_ERROR)
