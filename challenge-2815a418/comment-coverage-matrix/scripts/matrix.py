#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix.py — 覆盖矩阵的校验与统计。

子命令:
  validate <matrix.json>   校验完整性；有问题逐条列 issues 并 exit 1
  stats    <matrix.json>   按 type/severity/decision 统计（供回复信总述使用），输出 JSON

校验规则:
  - 每子要求: decision ∈ {采纳,部分采纳,不采纳}; decision_reason 与 response_summary 非空
  - 补做类动作 {补实验,补数据,补文献,重做分析}: evidence.status ∈ {到位,部分到位,无法补做}
  - evidence.status == 无法补做: alternative_explanation 非空
  - type/severity/action 取值为受控词表
  - sub_id 唯一且形如 <comment_id>.<n>
"""
import json, sys

TYPES = {"方法", "数据", "写作", "格式", "伦理", "其他"}
SEVERITIES = {"major", "minor"}
ACTIONS = {"修改文本", "补实验", "补数据", "补文献", "重做分析", "澄清解释"}
DECISIONS = {"采纳", "部分采纳", "不采纳"}
EVIDENCE_ACTIONS = {"补实验", "补数据", "补文献", "重做分析"}
EVIDENCE_STATUS = {"到位", "部分到位", "无法补做"}
RELATIONS = {"并列", "前置依赖", "互斥"}


def iter_subs(matrix):
    for c in matrix.get("comments", []):
        for s in c.get("subrequirements", []):
            yield c, s


def validate(matrix):
    issues, warnings = [], []
    if not matrix.get("comments"):
        issues.append("matrix.comments 为空：没有任何意见块")
    seen = set()
    all_sub_ids = set()
    for c, s in iter_subs(matrix):
        all_sub_ids.add(s.get("sub_id", ""))
    for c, s in iter_subs(matrix):
        sid = s.get("sub_id", "<missing>")
        cid = c.get("comment_id", "<missing>")
        if not sid or not sid.startswith(cid + "."):
            issues.append("%s: sub_id 必须以意见编号开头（形如 %s.N）" % (sid or "?", cid))
        if sid in seen:
            issues.append("%s: sub_id 重复" % sid)
        seen.add(sid)
        if not s.get("raw_text", "").strip():
            issues.append("%s: raw_text 为空（子要求必须有逐字摘录）" % sid)
        if s.get("type") not in TYPES:
            issues.append("%s: type 非法（%r），须 ∈ %s" % (sid, s.get("type"), sorted(TYPES)))
        if s.get("severity") not in SEVERITIES:
            issues.append("%s: severity 非法（%r），须 ∈ major/minor" % (sid, s.get("severity")))
        if s.get("action") not in ACTIONS:
            issues.append("%s: action 非法（%r），须 ∈ %s" % (sid, s.get("action"), sorted(ACTIONS)))
        if s.get("relation", "并列") not in RELATIONS:
            issues.append("%s: relation 非法（%r），须 ∈ %s" % (sid, s.get("relation"), sorted(RELATIONS)))
        for dep in s.get("depends_on", []):
            if dep not in all_sub_ids:
                issues.append("%s: depends_on 指向不存在的子要求 %s" % (sid, dep))
        d = s.get("decision")
        if d not in DECISIONS:
            issues.append("%s: decision 缺失或非法（%r），须 ∈ 采纳/部分采纳/不采纳（骨架的“待定”必须由 Agent 裁决）" % (sid, d))
        if not s.get("decision_reason", "").strip():
            issues.append("%s: decision_reason 为空（每个裁决必须有理由）" % sid)
        if not s.get("response_summary", "").strip():
            issues.append("%s: response_summary 为空（回复信用语必填）" % sid)
        if s.get("action") in EVIDENCE_ACTIONS:
            ev = s.get("evidence") or {}
            st = ev.get("status", "")
            if st not in EVIDENCE_STATUS:
                issues.append("%s: 补做类动作（%s）必须有 evidence.status ∈ 到位/部分到位/无法补做" % (sid, s.get("action")))
            elif st == "无法补做" and not (ev.get("alternative_explanation") or "").strip():
                issues.append("%s: evidence.status=无法补做 时必须填 alternative_explanation" % sid)
            elif st in ("到位", "部分到位") and not (ev.get("source") or "").strip():
                warnings.append("%s: evidence.status=%s 建议填写 source（证据出处）" % (sid, st))
        if s.get("action") == "修改文本" and s.get("decision") == "采纳":
            if not s.get("locations") and not (s.get("no_change_explanation") or "").strip():
                warnings.append("%s: 采纳的修改文本类子要求尚无 CHG 定位，也无 no_change_explanation（coverage_check 会强制检查）" % sid)
    return issues, warnings


def stats(matrix):
    by_type, by_sev, by_dec, by_act = {}, {}, {}, {}
    total = 0
    for _, s in iter_subs(matrix):
        total += 1
        by_type[s.get("type", "?")] = by_type.get(s.get("type", "?"), 0) + 1
        by_sev[s.get("severity", "?")] = by_sev.get(s.get("severity", "?"), 0) + 1
        by_dec[s.get("decision", "?")] = by_dec.get(s.get("decision", "?"), 0) + 1
        by_act[s.get("action", "?")] = by_act.get(s.get("action", "?"), 0) + 1
    return {
        "comments": len(matrix.get("comments", [])),
        "subrequirements": total,
        "by_type": by_type, "by_severity": by_sev,
        "by_decision": by_dec, "by_action": by_act,
    }


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("validate", "stats"):
        print("usage: matrix.py {validate|stats} <matrix.json>", file=sys.stderr)
        sys.exit(2)
    cmd, path = sys.argv[1], sys.argv[2]
    try:
        matrix = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("[matrix] FATAL: 无法读取 %s: %s" % (path, e), file=sys.stderr)
        sys.exit(2)
    if cmd == "validate":
        issues, warnings = validate(matrix)
        for w in warnings:
            print("[matrix] WARN: %s" % w)
        if issues:
            print("[matrix] VALIDATE FAILED: %d issue(s)" % len(issues), file=sys.stderr)
            for i in issues:
                print("  ISSUE: %s" % i, file=sys.stderr)
            sys.exit(1)
        st = stats(matrix)
        print("[matrix] VALIDATE OK: comments=%d subrequirements=%d" % (st["comments"], st["subrequirements"]))
    else:
        print(json.dumps(stats(matrix), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
