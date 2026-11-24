#!/usr/bin/env python3
"""ground_guard.py — 落地守卫：检查草稿中的每个数字与事实性论断能否回溯到台账。

用法：
  python3 ground_guard.py --facts facts.jsonl --draft 修订稿.md [--draft 回复信.md ...] \
      --out ground_report.json [--whitelist whitelist.txt] [--strict]

判定：
  - 抽取草稿中的全部数字 token（形态同 fact_ledger）与引号论断（“…”/「…」/"…"）。
  - 数字：surface（数值字符串，忽略区间端点差异）不在 facts.jsonl 任一 number 事实的
    surface 集合中，且不在白名单 → 记 material_external。
  - 引号论断：引号内文本不是任一事实 quote 的子串，且不在白名单 → 记 material_external。
  - CHG 标记内的 change_id（CHG-01 等）、编号类（第 1 条、Reviewer 2）默认豁免，
    可通过白名单显式管理。

白名单文件：每行一条；以 "re:" 开头按正则处理，否则按字面字符串处理。

--strict：存在 material_external 时 exit 1；否则 exit 0。
仅 Python 3 标准库。
"""
import argparse
import json
import os
import re
import sys

NUM_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?(?:×10\^?[−\-]?\d+|e[+\-]?\d+)"),
    re.compile(r"\d+(?:–|—|~|(?<=\d)-(?=\d))\d+"),
    re.compile(r"\d+(?:\.\d+)?%"),
    re.compile(r"(?<![\w\-\.^])\d+(?:\.\d+)?(?![\w.])"),
]

QUOTE_RE = re.compile(r"[“\"「『]([^”\"」』\n]{4,120})[”\"」』]")
CHG_RE = re.compile(r"<!--\s*CHG-\d+\s+(?:begin|end)\s*-->")
# 豁免：纯编号语境（第3条、图2、表1、Reviewer 1、CHG-01、F0001）
EXEMPT_RE = re.compile(
    r"(?:第\s*\d+\s*[条条款节段落]|图\s*\d+|表\s*\d+|Figure\s*\d+|Table\s*\d+|"
    r"Reviewer\s*\d+|审稿人\s*\d+|意见\s*\d+|CHG-\d+|F\d{4}|SYNTH-[\w-]+)")


def load_whitelist(path):
    literal, regex = set(), []
    if not path:
        return literal, regex
    if not os.path.isfile(path):
        print("WARN whitelist not found: %s" % path, file=sys.stderr)
        return literal, regex
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("re:"):
                regex.append(re.compile(line[3:]))
            else:
                literal.add(line)
    return literal, regex


def whitelisted(token, literal, regex):
    if token in literal:
        return True
    return any(r.search(token) for r in regex)


def extract_number_tokens(text):
    found = []
    occupied = []
    for pat in NUM_PATTERNS:
        for m in pat.finditer(text):
            s, e = m.span()
            if any(not (e <= a or s >= b) for a, b in occupied):
                continue
            found.append((m.group(0), (s, e)))
            occupied.append((s, e))
    return found


def main():
    ap = argparse.ArgumentParser(description="落地守卫")
    ap.add_argument("--facts", required=True)
    ap.add_argument("--draft", action="append", required=True,
                    help="草稿文件，可重复")
    ap.add_argument("--out", required=True)
    ap.add_argument("--whitelist", default=None)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    fact_numbers, fact_quotes = set(), []
    with open(args.facts, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("kind") == "number":
                fact_numbers.add(obj["surface"])
                # 区间端点也允许
                mm = re.match(r"^(\d+)(?:–|—|~|-)(\d+)$", obj["surface"])
                if mm:
                    fact_numbers.update(mm.groups())
            q = (obj.get("source") or {}).get("quote")
            if q:
                fact_quotes.append(q)
            if obj.get("kind") == "claim":
                fact_quotes.append(obj["surface"])

    literal, regex = load_whitelist(args.whitelist)

    issues, checked = [], 0
    for draft in args.draft:
        if not os.path.isfile(draft):
            issues.append({"file": draft, "token": None, "type": "draft_missing",
                           "detail": "草稿文件不存在"})
            continue
        with open(draft, "r", encoding="utf-8") as f:
            text = f.read()
        text_nochg = CHG_RE.sub("", text)
        # 豁免命中区间
        exempt_spans = [m.span() for m in EXEMPT_RE.finditer(text_nochg)]

        def exempted(span):
            s, e = span
            return any(not (e <= a or s >= b) for a, b in exempt_spans)

        for token, span in extract_number_tokens(text_nochg):
            checked += 1
            norm = token.rstrip("%")
            if (norm not in fact_numbers and token not in fact_numbers
                    and not whitelisted(token, literal, regex)
                    and not exempted(span)):
                ctx = text_nochg[max(0, span[0] - 60):span[1] + 60].replace("\n", " ")
                issues.append({"file": draft, "token": token,
                               "type": "material_external",
                               "detail": "数字不在 facts.jsonl 且不在白名单",
                               "context": ctx})
        for m in QUOTE_RE.finditer(text_nochg):
            claim = m.group(1).strip()
            checked += 1
            if (not any(claim in q for q in fact_quotes)
                    and not whitelisted(claim, literal, regex)
                    and not exempted(m.span(1))):
                issues.append({"file": draft, "token": claim,
                               "type": "material_external",
                               "detail": "引号论断不在台账 quote 中且不在白名单"})

    n_ext = sum(1 for i in issues if i["type"] == "material_external")
    report = {"drafts": args.draft, "facts": args.facts,
              "tokens_checked": checked,
              "material_external_count": n_ext,
              "status": "pass" if n_ext == 0 else "violations_found",
              "issues": issues}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("ground_guard: %d tokens checked, %d material_external -> %s"
          % (checked, n_ext, args.out))
    if args.strict and n_ext > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
