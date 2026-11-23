#!/usr/bin/env python3
"""build_profiles.py — 校验 agent 填写的条件档案（condition profiles）并输出规范化 profiles.json。

条件档案格式（profiles.jsonl，每行一条）：
  {"doc_id": "DOC-01", "dimension": "pollutant", "value": "RhB",
   "paragraph_id": "P2", "quote": "目标污染物为罗丹明 B（RhB）"}

机检落地：
  1. doc_id 必须对应语料目录中的一个 .md/.txt 文件（文件名主干 = doc_id）；
  2. 段落按空行切分，自动编号 P1, P2, ...；paragraph_id 必须存在；
  3. quote 必须逐字（空白归一后）出现在该 doc 的该段落中——这是"条件档案落在原文上"的硬校验；
  4. 六核心维度 task/metric/units/material/pollutant/budget 未填写的，只告警不报错，
     裁定时按"未报告"（undecidable）处理；value 填 "NOT_REPORTED"/空 等价于未报告。

用法：
  python3 build_profiles.py --corpus /path/to/corpus --profiles profiles.jsonl --out profiles.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

CORE_DIMENSIONS = ["task", "metric", "units", "material", "pollutant", "budget"]
NOT_REPORTED_TOKENS = {"", "not_reported", "n/a", "na", "none", "null", "未报告", "不详"}
PARA_RE = re.compile(r"^P(\d+)$")
REQUIRED_KEYS = ("doc_id", "dimension", "value", "paragraph_id", "quote")


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load_corpus(corpus_dir: str) -> dict:
    """语料目录 → {doc_id: {paragraph_id: paragraph_text}}。段落按空行切分。"""
    docs = {}
    for p in sorted(Path(corpus_dir).iterdir()):
        if not p.is_file() or p.suffix.lower() not in {".md", ".txt"}:
            continue
        text = p.read_text(encoding="utf-8")
        paras = [seg for seg in re.split(r"\n\s*\n", text) if seg.strip()]
        docs[p.stem] = {f"P{i + 1}": paras[i] for i in range(len(paras))}
    return docs


def main() -> int:
    ap = argparse.ArgumentParser(description="校验条件档案并输出规范化 profiles.json")
    ap.add_argument("--corpus", required=True, help="语料目录（每篇论文一个 .md/.txt 文件，文件名主干 = doc_id）")
    ap.add_argument("--profiles", required=True, help="agent 填写的 profiles.jsonl")
    ap.add_argument("--out", required=True, help="输出规范化 profiles.json")
    args = ap.parse_args()

    corpus = load_corpus(args.corpus)
    if not corpus:
        print(f"[ERROR] 语料目录为空或不存在: {args.corpus}", file=sys.stderr)
        return 1

    raw = []
    errors, warnings = [], []
    with open(args.profiles, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw.append((ln, json.loads(line)))
            except json.JSONDecodeError as e:
                errors.append(f"第{ln}行 JSON 解析失败: {e}")

    docs_out: dict = {}
    for ln, rec in raw:
        missing = [k for k in REQUIRED_KEYS if k not in rec]
        if missing:
            errors.append(f"第{ln}行缺少字段: {missing}")
            continue
        doc_id = str(rec["doc_id"]).strip()
        dim = str(rec["dimension"]).strip()
        value = rec["value"]
        pid = str(rec["paragraph_id"]).strip()
        quote = str(rec["quote"])

        if doc_id not in corpus:
            errors.append(f"第{ln}行: doc_id '{doc_id}' 不在语料中（语料含: {sorted(corpus)}）")
            continue
        if not PARA_RE.match(pid) or pid not in corpus[doc_id]:
            errors.append(f"第{ln}行: {doc_id} 不存在段落 {pid}（共 {len(corpus[doc_id])} 段）")
            continue

        reported = not (value is None or str(value).strip().lower() in NOT_REPORTED_TOKENS)
        if reported:
            if norm_ws(quote) not in norm_ws(corpus[doc_id][pid]):
                errors.append(
                    f"第{ln}行: quote 未逐字落地于 {doc_id} {pid}。\n"
                    f"  quote: {quote!r}\n  段落原文: {norm_ws(corpus[doc_id][pid])!r}"
                )
                continue
        else:
            value = "NOT_REPORTED"

        slot = docs_out.setdefault(doc_id, {})
        if dim in slot:
            errors.append(f"第{ln}行: {doc_id} 的维度 '{dim}' 重复定义（首次见第{slot[dim]['line']}行）")
            continue
        slot[dim] = {
            "value": value,
            "paragraph_id": pid,
            "quote": quote,
            "reported": reported,
            "line": ln,
        }
        if dim not in CORE_DIMENSIONS:
            warnings.append(f"{doc_id}: 扩展维度 '{dim}'（不在六核心维度内，按扩展键规则裁定）")

    for doc_id in sorted(docs_out):
        for dim in CORE_DIMENSIONS:
            if dim not in docs_out[doc_id]:
                warnings.append(f"{doc_id}: 核心维度 '{dim}' 未填写 → 裁定时按未报告（undecidable）处理")
    for doc_id in sorted(corpus):
        if doc_id not in docs_out:
            warnings.append(f"语料文档 {doc_id} 没有任何 profile（其所有维度均为 undecidable）")

    if errors:
        print("条件档案校验失败：", file=sys.stderr)
        for e in errors:
            print(f"  [ERROR] {e}", file=sys.stderr)
        return 1

    out = {
        "schema": "condition-profiles/1",
        "corpus_dir": str(Path(args.corpus).resolve()),
        "core_dimensions": CORE_DIMENSIONS,
        "docs": docs_out,
        "warnings": warnings,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(v) for v in docs_out.values())
    print(f"OK: {n} 条 profile，覆盖 {len(docs_out)} 篇文档 → {args.out}")
    for w in warnings:
        print(f"  [WARN] {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
