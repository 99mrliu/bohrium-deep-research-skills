#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引文精确匹配（鲁棒包装器）。

用法（CLI）：
  python3 quote_check.py --input <input_dir> --source-id S --paragraph-id P --quote "原文短引"
输出 JSON：{"match": true/false, ...}。供 Agent 与校验器核对“逐字短引”。
"""
import argparse
import json
import sys

from relation_common import load_corpus, quote_matches, normalize_text


def check_quote(corpus, source_id, paragraph_id, quote):
    src = corpus.get(source_id)
    if src is None:
        return {"match": False, "reason": "unknown_source_id", "source_id": source_id}
    text = src.get(paragraph_id)
    if text is None:
        return {"match": False, "reason": "unknown_paragraph_id",
                "source_id": source_id, "paragraph_id": paragraph_id}
    ok = quote_matches(text, quote)
    out = {"match": ok, "source_id": source_id, "paragraph_id": paragraph_id,
           "normalized_quote": normalize_text(quote)}
    if not ok:
        out["reason"] = "quote_not_verbatim_substring"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="逐字短引精确匹配")
    ap.add_argument("--input", required=True, help="含 material.json 的输入目录")
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--paragraph-id", required=True)
    ap.add_argument("--quote", required=True)
    args = ap.parse_args(argv)
    corpus, _ = load_corpus(args.input)
    res = check_quote(corpus, args.source_id, args.paragraph_id, args.quote)
    json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if res["match"] else 1


if __name__ == "__main__":
    sys.exit(main())
