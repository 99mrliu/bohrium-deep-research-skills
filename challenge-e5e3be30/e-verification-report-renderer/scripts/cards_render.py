#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cards_render.py — 判定 JSON → schema 校验 → 统一版式证据卡片 Markdown。

用法：
  python3 cards_render.py --verdicts verdicts.json --out evidence-cards.md [--title 标题]

verdicts.json 为判定对象数组，每个对象必须满足内嵌 schema：
  claim_id    str，非空
  claim_text  str，非空（论断原文）
  verdict     枚举：supported / partially_supported / contradicted / insufficient_evidence
  quotes      非空数组；每项 {quote: 非空 str, page: 正整数, paragraph: 可选 str,
                            source: 可选 str}
  rationale   str，非空（判定理由）
  uncertainty str，可为空字符串但键必须存在
  conflicts   可选数组；每项 {side_a: {quote,page,source?}, side_b: {quote,page,source?},
                            note: 可选 str}——冲突双方原话并列，不下结论时并列呈现。

schema 校验任一失败：打印全部错误，exit 1；用法/IO 错误 exit 2；成功 exit 0。
卡片版式遵循 references/card-template.md。仅依赖 Python3 标准库。
"""
import argparse
import json
import sys

VERDICT_ENUM = ["supported", "partially_supported", "contradicted",
                "insufficient_evidence"]
VERDICT_ZH = {
    "supported": "支持",
    "partially_supported": "部分支持",
    "contradicted": "反驳",
    "insufficient_evidence": "证据不足",
}


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 解析失败 {path}: {e}", file=sys.stderr)
        sys.exit(2)


def _is_pos_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _check_quote(q, where, errors):
    if not isinstance(q, dict):
        errors.append(f"{where}: 必须是对象")
        return
    if not isinstance(q.get("quote"), str) or not q["quote"].strip():
        errors.append(f"{where}.quote: 必须是非空字符串（逐字证据）")
    if not _is_pos_int(q.get("page")):
        errors.append(f"{where}.page: 必须是正整数")


def validate_verdict(v, idx):
    """返回该条判定的错误列表；空列表表示通过。"""
    errors = []
    where = f"verdicts[{idx}]"
    if not isinstance(v, dict):
        return [f"{where}: 必须是对象"]
    cid = v.get("claim_id")
    if isinstance(cid, str) and cid.strip():
        where = f"verdicts[{idx}]({cid})"
    else:
        errors.append(f"{where}.claim_id: 必须是非空字符串")
    if not isinstance(v.get("claim_text"), str) or not v["claim_text"].strip():
        errors.append(f"{where}.claim_text: 必须是非空字符串（论断原文）")
    if v.get("verdict") not in VERDICT_ENUM:
        errors.append(f"{where}.verdict: 非法值 {v.get('verdict')!r}，"
                      f"应为 {VERDICT_ENUM} 之一")
    quotes = v.get("quotes")
    if not isinstance(quotes, list) or not quotes:
        errors.append(f"{where}.quotes: 必须是非空数组（至少一条逐字证据）")
    else:
        for i, q in enumerate(quotes):
            _check_quote(q, f"{where}.quotes[{i}]", errors)
    if not isinstance(v.get("rationale"), str) or not v["rationale"].strip():
        errors.append(f"{where}.rationale: 必须是非空字符串（判定理由）")
    if "uncertainty" not in v or not isinstance(v.get("uncertainty"), str):
        errors.append(f"{where}.uncertainty: 键必须存在且为字符串（可为空串）")
    conflicts = v.get("conflicts", [])
    if conflicts is None:
        conflicts = []
    if not isinstance(conflicts, list):
        errors.append(f"{where}.conflicts: 如给出必须是数组")
    else:
        for i, c in enumerate(conflicts):
            cw = f"{where}.conflicts[{i}]"
            if not isinstance(c, dict) or "side_a" not in c or "side_b" not in c:
                errors.append(f"{cw}: 必须含 side_a 与 side_b")
                continue
            _check_quote(c["side_a"], f"{cw}.side_a", errors)
            _check_quote(c["side_b"], f"{cw}.side_b", errors)
    return errors


def cell(text):
    """Markdown 表格单元格转义：竖线与换行。"""
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def render_card(v, seq):
    lines = []
    verdict = v["verdict"]
    zh = VERDICT_ZH.get(verdict, verdict)
    lines.append(f"## 证据卡片 {v['claim_id']}")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    lines.append(f"| 论断原文 | {cell(v['claim_text'])} |")
    lines.append(f"| 判定 | **{verdict}**（{zh}） |")
    lines.append(f"| 判定理由 | {cell(v['rationale'])} |")
    lines.append(f"| 不确定性 | {cell(v.get('uncertainty') or '（无）')} |")
    lines.append("")
    lines.append(f"### 逐字证据（{len(v['quotes'])} 条）")
    lines.append("")
    lines.append("| # | 引用（逐字） | 页码 | 段落 | 来源 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for i, q in enumerate(v["quotes"], 1):
        lines.append(f"| {i} | “{cell(q['quote'])}” | 第 {q['page']} 页 | "
                     f"{cell(q.get('paragraph', '—'))} | {cell(q.get('source', '—'))} |")
    lines.append("")
    conflicts = v.get("conflicts") or []
    if conflicts:
        lines.append("### 冲突证据并列（双方原话，不作取舍）")
        lines.append("")
        for i, c in enumerate(conflicts, 1):
            lines.append(f"冲突 {i}" + (f"：{cell(c.get('note'))}" if c.get("note") else ""))
            lines.append("")
            lines.append("| 立场 | 引用（逐字） | 页码 | 来源 |")
            lines.append("| --- | --- | --- | --- |")
            for side, label in (("side_a", "甲方"), ("side_b", "乙方")):
                s = c[side]
                lines.append(f"| {label} | “{cell(s['quote'])}” | 第 {s['page']} 页 | "
                             f"{cell(s.get('source', '—'))} |")
            lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="判定 JSON → schema 校验 → 统一版式证据卡片 Markdown")
    p.add_argument("--verdicts", required=True, help="verdicts.json（判定对象数组）")
    p.add_argument("--out", required=True, help="证据卡片 Markdown 输出路径")
    p.add_argument("--title", default="证据卡片集", help="文档标题")
    args = p.parse_args(argv)

    data = load_json(args.verdicts)
    if not isinstance(data, list):
        print("ERROR: verdicts.json 顶层必须是数组", file=sys.stderr)
        return 2
    all_errors = []
    for i, v in enumerate(data):
        all_errors.extend(validate_verdict(v, i))
    ids = [v.get("claim_id") for v in data if isinstance(v, dict)]
    if len(ids) != len(set(ids)):
        all_errors.append("claim_id 存在重复")
    if all_errors:
        for e in all_errors:
            print(f"ERROR: {e}")
        print(f"FAIL: schema 校验未通过，共 {len(all_errors)} 个错误")
        return 1

    parts = [f"# {args.title}", "",
             f"共 {len(data)} 条论断的判定卡片。判定四级枚举："
             f"supported（支持）/ partially_supported（部分支持）/ "
             f"contradicted（反驳）/ insufficient_evidence（证据不足）。", ""]
    for i, v in enumerate(data, 1):
        parts.append(render_card(v, i))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"OK: {len(data)} 张证据卡片已渲染到 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
