#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_gate.py — 独立审计门（第 3 步，不过门不交付）

汇总 align_map 与 editlog_check 的结果，执行四项检查：
  1. unsupported_draft_sentences：无 unsupported 稿句，或全部列入待确认
  2. key_source_coverage：关键源句全覆盖，或有合法 omit/condense 记录
  3. editlog_legal：edit_log 全部条目合法
  4. numeric_anchors：稿件中的数字均能在源文中找到字面出现（术语锚点）

降级规则：若 alignment 处于 degraded 模式或全局低置信，则不判 FAIL，
改判 MANUAL_REVIEW（交人工复核），但已查出的硬错误仍判 FAIL。

退出码：
  0  PASS（过门，可交付）
  5  FAIL（不过门，不得交付）
  6  MANUAL_REVIEW（降级，需人工复核）
  2  输入错误
  1  内部错误
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

VERSION = "1.0.0"
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")


def squash(s):
    """去掉全部空白后的字面比较文本（NFKC）。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def main():
    ap = argparse.ArgumentParser(description="审计门汇总判定")
    ap.add_argument("--alignment", required=True, help="alignment.json")
    ap.add_argument("--editlog-report", required=True, help="editlog_report.json")
    ap.add_argument("--source", required=True, help="源文（用于数字锚点核对）")
    ap.add_argument("--draft", required=True, help="改写稿（用于数字锚点核对）")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录")
    ap.add_argument("--prefix", default="gate_verdict", help="输出文件前缀")
    args = ap.parse_args()

    paths = {k: Path(v) for k, v in
             [("alignment", args.alignment), ("editlog_report", args.editlog_report),
              ("source", args.source), ("draft", args.draft)]}
    for name, p in paths.items():
        if not p.is_file():
            print(f"ERROR: 文件不存在: {name}={p}", file=sys.stderr)
            return 2
    try:
        alignment = json.loads(paths["alignment"].read_text(encoding="utf-8"))
        editlog = json.loads(paths["editlog_report"].read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 解析失败: {e}", file=sys.stderr)
        return 2
    src_text = squash(paths["source"].read_text(encoding="utf-8"))
    drf_raw = paths["draft"].read_text(encoding="utf-8")
    drf_text = squash(drf_raw)

    checks = []

    # 检查 1：unsupported 稿句
    unsupported = [r for r in alignment.get("draft_sentences", [])
                   if r.get("verdict") == "unsupported"]
    pending_locs = set()
    for p in editlog.get("pending", []):
        if isinstance(p.get("locator"), str):
            pending_locs.update(t.upper() for t in p["locator"].split("-"))
    unack = [r for r in unsupported if r["id"] not in pending_locs]
    checks.append({
        "name": "unsupported_draft_sentences",
        "verdict": "PASS" if not unack else "FAIL",
        "detail": (f"unsupported 稿句 {len(unsupported)} 条"
                   + (f"，其中 {len(unack)} 条未列入待确认："
                      + ",".join(r["id"] for r in unack) if unack else "，均已列入待确认")),
        "items": [{"id": r["id"], "text": r["text"], "score": r["score"]}
                  for r in unsupported],
    })

    # 检查 2：关键源句覆盖
    missing_cov = editlog.get("coverage", {}).get("missing", [])
    checks.append({
        "name": "key_source_coverage",
        "verdict": "PASS" if not missing_cov else "FAIL",
        "detail": (f"未覆盖关键源句均有合法 omit/condense 记录"
                   if not missing_cov else
                   f"{len(missing_cov)} 条关键源句被删减但无合法记录："
                   + ",".join(m["id"] for m in missing_cov)),
        "items": missing_cov,
    })

    # 检查 3：edit_log 合法性
    checks.append({
        "name": "editlog_legal",
        "verdict": "PASS" if editlog.get("verdict") == "PASS" else "FAIL",
        "detail": f"editlog_check 判定 {editlog.get('verdict')}，"
                  f"错误 {editlog.get('stats', {}).get('errors', '?')} 条",
        "items": editlog.get("errors", []),
    })

    # 检查 4：数字锚点（稿件数字须在源文中字面出现）
    tokens = sorted(set(NUM_RE.findall(drf_text)))
    missing_tokens = [t for t in tokens if t not in src_text]
    checks.append({
        "name": "numeric_anchors",
        "verdict": "PASS" if not missing_tokens else "FAIL",
        "detail": (f"稿件数字 {len(tokens)} 个全部在源文中字面出现"
                   if not missing_tokens else
                   f"稿件数字无法在源文中找到字面出现：{missing_tokens}"),
        "items": missing_tokens,
    })

    degraded = (alignment.get("meta", {}).get("mode") == "degraded"
                or alignment.get("meta", {}).get("low_global_confidence"))

    n_fail = sum(1 for c in checks if c["verdict"] == "FAIL")
    if n_fail:
        overall, code = "FAIL", 5
    elif degraded:
        overall, code = "MANUAL_REVIEW", 6
    else:
        overall, code = "PASS", 0

    result = {
        "meta": {
            "tool": "audit_gate.py",
            "version": VERSION,
            "alignment": str(paths["alignment"]),
            "editlog_report": str(paths["editlog_report"]),
            "degraded": degraded,
            "degrade_reasons": alignment.get("meta", {}).get("degrade_reasons", []),
        },
        "verdict": overall,
        "exit_code": code,
        "checks": checks,
        "pending_questions": editlog.get("pending", []),
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{args.prefix}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / f"{args.prefix}.md").write_text(render_md(result), encoding="utf-8")
    print(f"{overall} {args.prefix}.json/md -> {outdir}  exit={code}")
    return code


def render_md(res):
    lines = [
        "# 审计门判定（gate verdict）",
        "",
        f"## 总判定：**{res['verdict']}**（退出码 {res['exit_code']}）",
        "",
    ]
    if res["meta"]["degraded"]:
        lines.append("> 降级模式：" + "；".join(res["meta"]["degrade_reasons"]))
        lines.append("")
    lines += ["## 检查项", "", "| 检查 | 判定 | 说明 |", "|---|---|---|"]
    for c in res["checks"]:
        mark = "✅" if c["verdict"] == "PASS" else "❌"
        lines.append(f"| {c['name']} | {mark} {c['verdict']} | {c['detail']} |")
    lines += ["", "## 待确认问题（随交付一并提交原作者）", ""]
    if res["pending_questions"]:
        for p in res["pending_questions"]:
            lines.append(f"- ❓ [{p.get('action')}] {p.get('locator')}：{p.get('reason')}")
    else:
        lines.append("- 无")
    lines += [
        "",
        "---",
        "PASS=可交付；FAIL=不过门不得交付；MANUAL_REVIEW=降级为人工复核清单。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"INTERNAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)
