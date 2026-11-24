#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_rules.py — 合并 draft_rules 与 resolutions，核验出处，生成覆盖矩阵。

职责：
1. 合并 draft_rules.json（编译产物）与 resolutions.json（人工裁决）。
2. 出处核验：每条最终规则必须带 source（文件+行号+原文），且与源文件实际
   行内容一致；每条裁决必须引用其目标未解析项的原始行号。无出处或出处不符
   的规则一律拒绝 → 退出码 4。
3. 生成 coverage_matrix.csv 三视图：
   - field      数据字段 × 规则覆盖（未覆盖字段 → 原样保留）
   - dict_line  字典行 × 被引用情况（未解析行必须有裁决，否则记缺口）
   - workorder  工单条目 × 规则覆盖（无法执行的条目 → 写明原因）
4. 输出 rules.final.json（规则 + gaps 缺口清单）。

退出码: 0 = 通过；4 = 出处核验失败 / 裁决非法。

确定性: 同一输入必得同一输出；不访问网络；仅使用标准库。
"""
import argparse
import csv
import json
import sys
from pathlib import Path

KNOWN_KINDS = {"sentinel_missing", "range_qc", "physical_bound",
               "lod_below", "unit_scale", "dedup"}
ACTION_TO_KINDS = {
    "sentinel_missing": {"sentinel_missing"},
    "unit_scale": {"unit_scale"},
    "dedup": {"dedup"},
    "range_qc": {"range_qc", "physical_bound"},
    "lod_below": {"lod_below"},
}


class Validator:
    def __init__(self, draft_path):
        self.draft_path = Path(draft_path)
        self.failures = []
        self.lines_cache = {}

    def resolve_file(self, p):
        """按 原路径 / 相对 draft 目录 / 相对 draft 上级目录 依次解析。"""
        for cand in (Path(p), self.draft_path.parent / p,
                     self.draft_path.parent.parent / p):
            if cand.is_file():
                return cand
        return None

    def get_lines(self, p):
        if p not in self.lines_cache:
            f = self.resolve_file(p)
            if f is None:
                self.lines_cache[p] = None
            else:
                self.lines_cache[p] = f.read_text(
                    encoding="utf-8-sig").splitlines()
        return self.lines_cache[p]

    def check_rule_source(self, rule):
        """规则出处核验：文件存在、行号有效、原文一致。"""
        src = rule.get("source") or {}
        f, line, text = src.get("file"), src.get("line"), src.get("text")
        if not f or not isinstance(line, int) or text is None:
            return "缺少 source（文件+行号+原文）"
        lines = self.get_lines(f)
        if lines is None:
            return "出处文件不存在: %s" % f
        if not (1 <= line <= len(lines)):
            return "行号越界: %s:%d（文件共 %d 行）" % (f, line, len(lines))
        if lines[line - 1].strip() != str(text).strip():
            return "原文与源文件实际行内容不一致: %s:%d" % (f, line)
        return None


def main():
    ap = argparse.ArgumentParser(description="规则合并 / 出处核验 / 覆盖矩阵")
    ap.add_argument("--draft", required=True, help="draft_rules.json")
    ap.add_argument("--resolutions", default=None, help="resolutions.json")
    ap.add_argument("--data", required=True, help="待清洗数据 CSV（读取表头）")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
    resolutions = {"resolutions": []}
    if args.resolutions:
        resolutions = json.loads(
            Path(args.resolutions).read_text(encoding="utf-8"))

    v = Validator(args.draft)
    unparsed = {u["unparsed_id"]: u for u in draft.get("unparsed", [])}
    new_rules = []
    reject_notes = {}      # target -> rationale
    resolved_targets = set()

    # ------------------------------------------------------ 裁决处理 ----
    for idx, res in enumerate(resolutions.get("resolutions", []), 1):
        label = "resolutions[%d]" % idx
        target, action = res.get("target"), res.get("action")
        if target not in unparsed:
            v.failures.append("%s: target「%s」不在未解析清单中" % (label, target))
            continue
        u = unparsed[target]
        if action not in ("approve", "adjust", "reject"):
            v.failures.append("%s: action 必须为 approve/adjust/reject" % label)
            continue
        src = res.get("source")
        if (not isinstance(src, dict) or not src.get("file")
                or not isinstance(src.get("line"), int)):
            v.failures.append("%s: 裁决缺少 source（文件+行号）" % label)
            continue
        if src["file"] != u["file"] or src["line"] != u["line"]:
            v.failures.append(
                "%s: 裁决出处 %s:%s 与未解析项 %s 实际位置 %s:%s 不一致"
                % (label, src["file"], src["line"], target,
                   u["file"], u["line"]))
            continue
        lines = v.get_lines(src["file"])
        if lines is None or not (1 <= src["line"] <= len(lines)):
            v.failures.append("%s: 裁决引用的源文件/行号不可读" % label)
            continue
        if not str(res.get("rationale", "")).strip():
            v.failures.append("%s: rationale（裁决依据）不能为空" % label)
            continue
        resolved_targets.add(target)
        if action == "reject":
            reject_notes[target] = res["rationale"]
            continue
        rb = res.get("rule")
        if (not isinstance(rb, dict) or rb.get("kind") not in KNOWN_KINDS
                or not rb.get("field") or not isinstance(rb.get("params"), dict)):
            v.failures.append(
                "%s: approve/adjust 必须给出合法 rule（kind/field/params）" % label)
            continue
        rid = "R%03d" % (100 + len(new_rules) + 1)
        new_rules.append({
            "rule_id": rid, "kind": rb["kind"], "field": rb["field"],
            "params": rb["params"],
            "source": {"file": src["file"], "line": src["line"],
                       "text": lines[src["line"] - 1].strip()},
            "origin": "resolution", "resolution_target": target,
            "rationale": res["rationale"]})

    # ------------------------------------------------------ 出处核验 ----
    draft_rules = draft.get("rules", [])
    for r in draft_rules:
        if r.get("kind") not in KNOWN_KINDS or not r.get("field"):
            v.failures.append("%s: 规则缺少合法 kind/field"
                              % r.get("rule_id", "?"))
            continue
        err = v.check_rule_source(r)
        if err:
            v.failures.append("%s: %s" % (r.get("rule_id", "?"), err))

    final_rules = list(draft_rules) + new_rules

    # ------------------------------------------------------ 覆盖矩阵 ----
    with open(args.data, newline="", encoding="utf-8-sig") as fh:
        header = next(csv.reader(fh))
    data_fields = [h.strip() for h in header]
    for r in final_rules:
        if r["field"] not in data_fields:
            data_fields.append(r["field"])  # 规则指向但数据中缺失的字段也列出

    rules_by_field = {}
    for r in final_rules:
        rules_by_field.setdefault(r["field"], []).append(r["rule_id"])

    matrix = []   # (view, item, detail, covered_by, status, disposition)
    gaps = []

    # 视图一：数据字段 × 规则
    for f in data_fields:
        ids = rules_by_field.get(f, [])
        if ids:
            matrix.append(("field", f, "数据列/规则目标字段",
                           ";".join(ids), "covered", ""))
        else:
            matrix.append(("field", f, "数据列", "", "uncovered", "原样保留"))
            gaps.append({"type": "uncovered_field", "field": f,
                         "disposition": "原样保留，未做任何处理"})

    # 视图二：字典行 × 被引用
    dict_files = {s["file"] for s in draft.get("sources", [])
                  if s.get("role") == "dictionary"}
    for reg in draft.get("line_register", []):
        if reg["file"] not in dict_files:
            continue
        if reg["category"] not in ("parsed", "unparsed"):
            continue
        item = "%s:%d" % (reg["file"], reg["line"])
        detail = reg["text"][:80]
        if reg["category"] == "parsed":
            if reg["rule_ids"]:
                matrix.append(("dict_line", item, detail,
                               ";".join(reg["rule_ids"]), "parsed", ""))
            else:
                matrix.append(("dict_line", item, detail, "",
                               "parsed_no_rule", "描述/登记行，无需规则"))
        else:
            uid = reg.get("unparsed_id")
            if uid in reject_notes:
                matrix.append(("dict_line", item, detail, "", "rejected",
                               "已裁决不执行：%s" % reject_notes[uid]))
            elif uid in resolved_targets:
                rid = [r["rule_id"] for r in new_rules
                       if r.get("resolution_target") == uid]
                matrix.append(("dict_line", item, detail, ";".join(rid),
                               "resolved", "经裁决补全为规则"))
            else:
                matrix.append(("dict_line", item, detail, "", "unresolved",
                               "未裁决，未执行"))
                gaps.append({"type": "unresolved_line", "file": reg["file"],
                             "line": reg["line"], "unparsed_id": uid,
                             "disposition": "未裁决，未执行"})

    # 视图三：工单条目 × 规则
    for wo in draft.get("workorder_items", []):
        pairs = [(f, a) for f in wo["fields"] for a in wo["actions"]]
        covered, missing = [], []
        for f, a in pairs:
            ok = any(r["field"] == f and r["kind"] in ACTION_TO_KINDS[a]
                     for r in final_rules)
            (covered if ok else missing).append((f, a))
        ids = ";".join(r["rule_id"] for r in final_rules
                       if r["field"] in wo["fields"]
                       and any(r["kind"] in ACTION_TO_KINDS[a]
                               for a in wo["actions"]))
        if not pairs:
            status, disp = "uncovered", "无法执行：未识别到字段×动作对"
            gaps.append({"type": "workorder_gap", "wo_id": wo["wo_id"],
                         "disposition": disp})
        elif missing:
            status = "partial"
            disp = "无法执行：%s 无对应可执行规则" % "; ".join(
                "%s/%s" % m for m in missing)
            gaps.append({"type": "workorder_gap", "wo_id": wo["wo_id"],
                         "disposition": disp})
        else:
            status, disp = "covered", ""
        matrix.append(("workorder", wo["wo_id"], wo["text"][:80],
                       ids, status, disp))

    # ------------------------------------------------------ 输出 ----
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "coverage_matrix.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["view", "item", "detail", "covered_by", "status",
                    "disposition"])
        w.writerows(matrix)

    rules_final = {"version": draft.get("version", "1.0"),
                   "sources": draft.get("sources", []),
                   "rules": final_rules, "gaps": gaps,
                   "stats": {"rules": len(final_rules),
                             "draft_rules": len(draft_rules),
                             "resolution_rules": len(new_rules),
                             "rejected": len(reject_notes),
                             "gaps": len(gaps)}}
    (out / "rules.final.json").write_text(
        json.dumps(rules_final, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print("validate_rules: 最终规则 %d 条（编译 %d + 裁决 %d）；缺口 %d 条"
          % (len(final_rules), len(draft_rules), len(new_rules), len(gaps)))
    if v.failures:
        print("出处/裁决核验失败 %d 项：" % len(v.failures), file=sys.stderr)
        for f_ in v.failures:
            print("  - " + f_, file=sys.stderr)
        print("EXIT 4: 存在无出处或出处不符的规则/裁决，一律拒绝执行",
              file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
