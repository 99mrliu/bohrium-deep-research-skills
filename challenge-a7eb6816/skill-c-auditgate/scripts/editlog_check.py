#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""editlog_check.py — 改动清单合法性校验（审计门第 2 步）

校验 edit_log.jsonl（每行 {"locator": ..., "action": ..., "reason": ...}）：
  1) action ∈ {retain, rephrase, move, condense, omit, translate}
  2) reason 非空且去空白后长度 ≥ 4
  3) locator 可解析：GLOBAL，或 S<号> / D<号> / P<号>，可用 "-" 连接两个引用
     （如 S3、D5、S3-D2）
  4) 覆盖性：align_map 报告中的 uncovered_key_source（被删减/大改的关键源句）
     必须存在至少一条「合法」的 omit/condense 条目且 locator 引用该源句
  5) 待确认问题（needs_confirmation: true，或 reason 以「待确认」开头）单独汇总

退出码：
  0  PASS（全部合法且覆盖完整）
  4  FAIL（存在非法条目或删减无记录）
  2  输入错误
  1  内部错误
"""
import argparse
import json
import re
import sys
from pathlib import Path

VERSION = "1.0.0"
ACTIONS = {"retain", "rephrase", "move", "condense", "omit", "translate"}
LOC_RE = re.compile(r"^(GLOBAL|[SDP]\d+)(-[SDP]\d+)?$", re.IGNORECASE)
MIN_REASON = 4


def parse_locator(loc):
    """返回 (是否合法, 引用列表)。引用统一大写，如 ['S3','D2']。"""
    if not isinstance(loc, str):
        return False, []
    loc = loc.strip()
    m = LOC_RE.match(loc)
    if not m:
        return False, []
    refs = [t.upper() for t in loc.split("-")]
    return True, refs


def main():
    ap = argparse.ArgumentParser(description="改动清单 edit_log.jsonl 合法性校验")
    ap.add_argument("editlog", help="edit_log.jsonl 路径")
    ap.add_argument("--alignment", required=True,
                    help="align_map.py 生成的 alignment.json（用于删减覆盖性校验）")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录")
    ap.add_argument("--prefix", default="editlog_report",
                    help="输出文件前缀（默认 editlog_report）")
    args = ap.parse_args()

    log_path = Path(args.editlog)
    aln_path = Path(args.alignment)
    for p in (log_path, aln_path):
        if not p.is_file():
            print(f"ERROR: 文件不存在: {p}", file=sys.stderr)
            return 2
    try:
        alignment = json.loads(aln_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: alignment.json 解析失败: {e}", file=sys.stderr)
        return 2

    entries = []
    errors = []
    pending = []
    for lineno, raw in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            errors.append({"line": lineno, "type": "invalid_json", "detail": str(e)})
            continue
        loc = obj.get("locator")
        action = obj.get("action")
        reason = obj.get("reason")
        ent_errors = []
        ok_loc, refs = parse_locator(loc)
        if not ok_loc:
            ent_errors.append({"line": lineno, "type": "bad_locator",
                               "detail": f"locator 无法解析: {loc!r}"})
        if action not in ACTIONS:
            ent_errors.append({"line": lineno, "type": "bad_action",
                               "detail": f"action 非法: {action!r}，"
                                         f"须为 {sorted(ACTIONS)} 之一"})
        if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
            ent_errors.append({"line": lineno, "type": "bad_reason",
                               "detail": f"reason 缺失或过短（< {MIN_REASON} 字）: "
                                         f"{reason!r}"})
        errors.extend(ent_errors)
        entry = {
            "line": lineno, "locator": loc, "refs": refs, "action": action,
            "reason": reason, "legal": not ent_errors,
            "needs_confirmation": bool(obj.get("needs_confirmation")),
        }
        entries.append(entry)
        if entry["needs_confirmation"] or (
                isinstance(reason, str) and reason.strip().startswith("待确认")):
            pending.append({"line": lineno, "locator": loc, "action": action,
                            "reason": reason})

    # 覆盖性：uncovered_key_source 必须有合法 omit/condense 记录
    uncovered = alignment.get("uncovered_key_source", [])
    covered_ids, missing = [], []
    for rec in uncovered:
        sid = rec.get("id")
        hit = any(
            e["legal"] and e["action"] in ("omit", "condense") and sid in e["refs"]
            for e in entries
        )
        if hit:
            covered_ids.append(sid)
        else:
            missing.append({"id": sid, "text": rec.get("text", "")})
            errors.append({"line": None, "type": "omit_not_logged",
                           "detail": f"关键源句 {sid} 被删减/大改，但 edit_log 中无"
                                     f"合法的 omit/condense 记录: "
                                     f"{rec.get('text', '')[:60]}"})

    verdict = "PASS" if not errors else "FAIL"
    report = {
        "meta": {
            "tool": "editlog_check.py",
            "version": VERSION,
            "editlog": str(log_path),
            "alignment": str(aln_path),
            "allowed_actions": sorted(ACTIONS),
            "min_reason_chars": MIN_REASON,
        },
        "verdict": verdict,
        "stats": {"entries": len(entries), "errors": len(errors),
                  "pending": len(pending)},
        "errors": errors,
        "pending": pending,
        "coverage": {
            "uncovered_key_source": [r.get("id") for r in uncovered],
            "covered_by_log": covered_ids,
            "missing": missing,
        },
        "entries": entries,
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{args.prefix}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / f"{args.prefix}.md").write_text(render_md(report), encoding="utf-8")
    print(f"{verdict} {args.prefix}.json/md -> {outdir}  "
          f"entries={len(entries)} errors={len(errors)} pending={len(pending)}")
    return 0 if verdict == "PASS" else 4


def render_md(rep):
    lines = [
        "# 改动清单校验报告（editlog）",
        "",
        f"- 总判定：**{rep['verdict']}**",
        f"- 条目数 {rep['stats']['entries']}，错误 {rep['stats']['errors']}，"
        f"待确认 {rep['stats']['pending']}",
        "",
        "## 错误明细",
        "",
    ]
    if rep["errors"]:
        for e in rep["errors"]:
            loc = f"第 {e['line']} 行" if e["line"] else "覆盖性检查"
            lines.append(f"- ❌ [{e['type']}]（{loc}）{e['detail']}")
    else:
        lines.append("- 无")
    lines += ["", "## 删减覆盖性", ""]
    cov = rep["coverage"]
    lines.append(f"- 未覆盖关键源句：{cov['uncovered_key_source'] or '无'}")
    lines.append(f"- 已有合法 omit/condense 记录：{cov['covered_by_log'] or '无'}")
    if cov["missing"]:
        for mrec in cov["missing"]:
            lines.append(f"- ⚠ 缺记录：{mrec['id']}：{mrec['text']}")
    lines += ["", "## 待确认问题（交原作者复核）", ""]
    if rep["pending"]:
        for p in rep["pending"]:
            lines.append(f"- ❓ 第 {p['line']} 行 [{p['action']}] "
                         f"{p['locator']}：{p['reason']}")
    else:
        lines.append("- 无")
    lines += ["", "## 全部条目", ""]
    for e in rep["entries"]:
        mark = "✅" if e["legal"] else "❌"
        lines.append(f"- {mark} 第 {e['line']} 行 [{e['action']}] "
                     f"{e['locator']}：{e['reason']}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"INTERNAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)
