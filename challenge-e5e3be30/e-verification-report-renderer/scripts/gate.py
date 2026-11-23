#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate.py — 提交前总闸门。任一 ERROR 以 exit 1 结束，全部通过 exit 0。

用法：
  python3 gate.py --case case.json --result result.json \
      --pages pages.jsonl [--cards evidence-cards.md]

三道检查：
  1. 契约校验：复用 contract_assemble.validate_result
     （case_id 一致、契约字段齐全、status 自洽）。
  2. 逐字证据回查：result.json verdicts 中每条 quote 经归一化
     （Unicode NFKC、弯引号→直引号、连字符归一、空白折叠）后，
     必须是其声明页码的分页文本的子串。pages.jsonl 每行 {"page": int, "text": str}。
  3. 卡片-结果一致性（提供 --cards 时）：evidence-cards.md 中每张卡片的
     claim_id 与判定值必须与 result.json verdicts 一一对应、数值一致。

退出码：0 全部通过 / 1 存在 ERROR / 2 用法或 IO 错误。
仅依赖 Python3 标准库。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import contract_assemble as ca
except ImportError:  # pragma: no cover
    print("ERROR: 无法导入同目录 contract_assemble.py", file=sys.stderr)
    sys.exit(2)

QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "‐": "-", "‑": "-",
    " ": " ", " ": " ", "　": " ",
}


def normalize(s):
    """归一化：NFKC → 弯引号/连字符/特殊空格归一 → 空白折叠。"""
    s = unicodedata.normalize("NFKC", s)
    for k, v in QUOTE_MAP.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


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


def load_pages(path):
    pages = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"ERROR: pages.jsonl 第 {ln} 行 JSON 解析失败: {e}")
                    sys.exit(2)
                page = rec.get("page")
                text = rec.get("text")
                if not isinstance(page, int) or not isinstance(text, str):
                    print(f"ERROR: pages.jsonl 第 {ln} 行须含 int 型 page 与 str 型 text")
                    sys.exit(2)
                pages[page] = pages.get(page, "") + "\n" + text
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    if not pages:
        print(f"ERROR: pages.jsonl 为空: {path}", file=sys.stderr)
        sys.exit(2)
    return pages


def check_contract(case, result, errors):
    for e in ca.validate_result(case, result):
        errors.append(f"[契约] {e}")


def iter_quotes(verdicts):
    """产出 (claim_id, where, quote, page)：含冲突双方原话。"""
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        cid = v.get("claim_id", "?")
        for i, q in enumerate(v.get("quotes") or []):
            if isinstance(q, dict):
                yield cid, f"quotes[{i}]", q.get("quote"), q.get("page")
        for i, c in enumerate(v.get("conflicts") or []):
            if not isinstance(c, dict):
                continue
            for side in ("side_a", "side_b"):
                s = c.get(side)
                if isinstance(s, dict):
                    yield cid, f"conflicts[{i}].{side}", s.get("quote"), s.get("page")


def check_quotes(result, pages, errors, warnings):
    verdicts = result.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        errors.append("[回查] result.json 缺少非空 verdicts 数组，无法执行证据回查")
        return
    norm_pages = {p: normalize(t) for p, t in pages.items()}
    n_ok = 0
    for cid, where, quote, page in iter_quotes(verdicts):
        loc = f"{cid}.{where}"
        if not isinstance(quote, str) or not quote.strip():
            errors.append(f"[回查] {loc}: quote 为空或非字符串")
            continue
        if not isinstance(page, int) or page < 1:
            errors.append(f"[回查] {loc}: page 非法（{page!r}）")
            continue
        if page not in norm_pages:
            errors.append(f"[回查] {loc}: 第 {page} 页在 pages.jsonl 中不存在"
                          f"（可用页: {sorted(norm_pages)}）")
            continue
        if normalize(quote) in norm_pages[page]:
            n_ok += 1
        else:
            snippet = normalize(quote)[:80]
            errors.append(f"[回查] {loc}: 引用未在第 {page} 页原文中逐字找到"
                          f"（归一化后仍不匹配）: “{snippet}…”")
    print(f"INFO: 证据回查 {n_ok} 条通过")


def check_cards_consistency(result, cards_path, errors, warnings):
    verdicts = result.get("verdicts")
    if not isinstance(verdicts, list):
        errors.append("[一致性] result.json 缺少 verdicts 数组")
        return
    rv = {v.get("claim_id"): v.get("verdict")
          for v in verdicts if isinstance(v, dict)}
    try:
        with open(cards_path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        errors.append(f"[一致性] 卡片文件不存在: {cards_path}")
        return
    card_verdicts = {}
    sections = re.split(r"(?m)^## 证据卡片\s+", text)
    for sec in sections[1:]:
        m_id = re.match(r"(\S+)", sec)
        m_v = re.search(r"\|\s*判定\s*\|\s*\*\*([a-z_]+)\*\*", sec)
        if not m_id:
            errors.append("[一致性] 存在无法解析 claim_id 的卡片")
            continue
        if not m_v:
            errors.append(f"[一致性] 卡片 {m_id.group(1)} 未找到判定行")
            continue
        card_verdicts[m_id.group(1)] = m_v.group(1)
    for cid, verdict in rv.items():
        if cid not in card_verdicts:
            errors.append(f"[一致性] result.json 中 {cid} 在卡片文件里无对应卡片")
        elif card_verdicts[cid] != verdict:
            errors.append(f"[一致性] {cid} 判定不一致: result={verdict} "
                          f"卡片={card_verdicts[cid]}")
    for cid in card_verdicts:
        if cid not in rv:
            errors.append(f"[一致性] 卡片 {cid} 在 result.json verdicts 中不存在")
    if len(card_verdicts) != len(rv):
        warnings.append(f"[一致性] 卡片数({len(card_verdicts)}) 与 "
                        f"verdicts 数({len(rv)}) 不等")
    print(f"INFO: 卡片-结果一致性检查 {len(card_verdicts)} 张卡片")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="提交前总闸门：契约校验 + 逐字证据回查 + 卡片-结果一致性")
    p.add_argument("--case", required=True, help="case.json 路径")
    p.add_argument("--result", required=True, help="result.json 路径")
    p.add_argument("--pages", required=True,
                   help="pages.jsonl（每行 {\"page\": int, \"text\": str}）")
    p.add_argument("--cards", help="可选：evidence-cards.md（做卡片-结果一致性检查）")
    args = p.parse_args(argv)

    case = load_json(args.case)
    result = load_json(args.result)
    pages = load_pages(args.pages)

    errors, warnings = [], []
    check_contract(case, result, errors)
    check_quotes(result, pages, errors, warnings)
    if args.cards:
        check_cards_consistency(result, args.cards, errors, warnings)

    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"GATE: FAIL（{len(errors)} 个 ERROR，{len(warnings)} 个 WARN）——禁止提交")
        return 1
    print(f"GATE: PASS（0 个 ERROR，{len(warnings)} 个 WARN）——允许提交")
    return 0


if __name__ == "__main__":
    sys.exit(main())
