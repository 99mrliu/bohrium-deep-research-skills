#!/usr/bin/env python3
"""expand.py — 受控术语扩展: 同义/缩写/拼写/连字符变体, 带扩展预算防止发散。

用法:
  python3 expand.py --terms "passivation,grain boundary" [--max-variants 4] [--table resources/variant_table.tsv]

扩展来源(按序,命中即停,每词最多 max-variants 个变体):
  1. variant_table.tsv(人工整理的小词表, tab 分隔: 规范词<TAB>变体1;变体2)
  2. 自动规则: 美式/英式(-ize/-ise 等)、连字符/空格互换、常见缩写模式(全大写词给
     小写形式,反之长度>=4 的全小写词给首字母大写缩写候选)
输出: 扩展后查询词组 JSON(含每词的变体与来源标记), 供 search.py 使用。
"""
import argparse, json, os, re

RULES = [("-ization", "-isation"), ("-ized", "-ised"), ("-ization ", "-isation "),
         ("-ing", "")]

def auto_variants(w):
    vs = set()
    if re.search(r"[a-z]-[a-z]", w):
        vs.add(w.replace("-", " "))
    if " " in w:
        vs.add(w.replace(" ", "-"))
    for a, b in (("ize", "ise"), ("izer", "iser"), ("yze", "yse"), ("ae", "e"), ("oe", "e")):
        if w.endswith(a) and len(w) > len(a) + 2:
            vs.add(w[: -len(a)] + b)
        elif w.endswith(b) and len(w) > len(b) + 2:
            vs.add(w[: -len(b)] + a)
    if w.isupper() and len(w) >= 2:
        vs.add(w.lower())
    elif w.islower() and len(w) >= 4:
        vs.add(w.upper())
    return {v for v in vs if v and v != w}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms", required=True, help="逗号分隔种子词")
    ap.add_argument("--max-variants", type=int, default=4)
    ap.add_argument("--table", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "..", "resources", "variant_table.tsv"))
    args = ap.parse_args()
    table = {}
    if os.path.exists(args.table):
        for line in open(args.table, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                table[parts[0].lower()] = [v for v in parts[1].split(";") if v]
    out = {}
    for term in [t.strip() for t in args.terms.split(",") if t.strip()]:
        key = term.lower()
        variants = []
        if key in table:
            variants = [(v, "table") for v in table[key][:args.max_variants]]
        else:
            av = sorted(auto_variants(key))[:args.max_variants]
            variants = [(v, "rule") for v in av]
        out[term] = {"canonical": term, "variants": [v for v, _ in variants],
                     "variant_sources": dict(variants), "budget_cap": args.max_variants}
    print(json.dumps({"ok": True, "expanded": out,
                      "divergence_guard": "每词变体<=max_variants; 未命中词表/规则的词不扩展"},
                     ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
