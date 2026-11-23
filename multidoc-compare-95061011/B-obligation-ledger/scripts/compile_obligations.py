#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compile_obligations.py — 把 comparison-workorder.json 编译成义务台账 obligations.jsonl。

义务（obligation）三类：
  - field_cell     ：工单字段 × 文档，每个单元格一条义务
  - comparability  ：可比性维度 × 文档对，每对每维一条义务
  - question       ：工单显式问题，每问一条义务

对未知 schema 健壮：documents / dimensions / fields / questions 均尝试多个常见键名，
元素既可以是字符串也可以是带 id/document_id/name 等键的对象。
找不到文档清单时可由 --corpus 目录（*.jsonl 文件名即 document_id）推断。

用法：
  python3 compile_obligations.py --workorder comparison-workorder.json \
      [--case case.json] [--corpus corpus_dir] --out obligations.jsonl
"""
import argparse
import itertools
import json
import os
import re
import sys

DEFAULT_DIMENSIONS = ["task", "metric", "units", "material", "pollutant", "budget"]

DOC_KEYS = ("documents", "corpus", "document_list", "papers", "docs")
DIM_KEYS = ("dimensions", "comparability_dimensions", "comparison_dimensions")
FIELD_KEYS = ("fields", "required_fields", "output_fields", "columns")
QUESTION_KEYS = ("questions", "explicit_questions", "queries")
ID_KEYS = ("document_id", "doc_id", "id", "name", "key")


def load_json(path):
    if not path:
        return None
    if not os.path.isfile(path):
        print("[compile] 警告：文件不存在，忽略：%s" % path, file=sys.stderr)
        return None
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print("[compile] 错误：%s 不是合法 JSON：%s" % (path, e), file=sys.stderr)
            sys.exit(2)


def slug(s):
    """把任意字符串转成 obligation_id 可用的片段。"""
    s = re.sub(r"\s+", "_", str(s).strip())
    s = re.sub(r"[^0-9A-Za-z_\-.\u4e00-\u9fff]", "-", s)
    return s or "unnamed"


def pick_id(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for k in ID_KEYS:
            if item.get(k):
                return str(item[k])
    return None


def pick_list(*sources, keys=()):
    for src in sources:
        if not isinstance(src, dict):
            continue
        for k in keys:
            v = src.get(k)
            if isinstance(v, list) and v:
                return v
    return None


def docs_from_corpus(corpus_dir):
    out = []
    for fn in sorted(os.listdir(corpus_dir)):
        if fn.endswith(".jsonl"):
            out.append(fn[: -len(".jsonl")])
    return out


def main():
    ap = argparse.ArgumentParser(description="编译 comparison-workorder.json 为 obligations.jsonl")
    ap.add_argument("--workorder", required=True, help="comparison-workorder.json 路径")
    ap.add_argument("--case", default=None, help="case.json 路径（可选，用于补充文档清单/case_id）")
    ap.add_argument("--corpus", default=None, help="语料目录（可选，找不到文档清单时从 *.jsonl 文件名推断）")
    ap.add_argument("--out", required=True, help="输出 obligations.jsonl 路径")
    args = ap.parse_args()

    wo = load_json(args.workorder)
    if not isinstance(wo, dict):
        print("[compile] 错误：workorder 顶层必须是 JSON 对象", file=sys.stderr)
        sys.exit(2)
    case = load_json(args.case) if args.case else None

    case_id = wo.get("case_id") or (case or {}).get("case_id") or "UNKNOWN-CASE"

    # ---- 文档清单 ----
    raw_docs = pick_list(wo, case, keys=DOC_KEYS)
    documents = []
    if raw_docs:
        documents = [d for d in (pick_id(x) for x in raw_docs) if d]
    if not documents and args.corpus and os.path.isdir(args.corpus):
        documents = docs_from_corpus(args.corpus)
        print("[compile] 工单未给出文档清单，从 --corpus 推断：%s" % documents, file=sys.stderr)
    if not documents:
        print("[compile] 错误：无法确定文档清单（工单/case/--corpus 均无）", file=sys.stderr)
        sys.exit(2)

    # ---- 维度 / 字段 / 问题 ----
    raw_dims = pick_list(wo, keys=DIM_KEYS)
    dimensions = [d for d in (pick_id(x) for x in raw_dims) if d] if raw_dims else list(DEFAULT_DIMENSIONS)
    if not raw_dims:
        print("[compile] 工单未给 dimensions，使用默认六维：%s" % dimensions, file=sys.stderr)

    raw_fields = pick_list(wo, keys=FIELD_KEYS)
    fields = [f for f in (pick_id(x) for x in raw_fields) if f] if raw_fields else []
    if not fields:
        print("[compile] 警告：工单无 fields，跳过 field_cell 义务", file=sys.stderr)

    raw_questions = pick_list(wo, keys=QUESTION_KEYS) or []
    questions = []
    for i, q in enumerate(raw_questions, 1):
        if isinstance(q, str):
            questions.append({"id": str(i), "text": q})
        elif isinstance(q, dict):
            qid = q.get("id") or q.get("qid") or str(i)
            qtext = q.get("question") or q.get("text") or q.get("q") or json.dumps(q, ensure_ascii=False)
            questions.append({"id": str(qid), "text": str(qtext)})

    # ---- 展开义务 ----
    obligations = []

    def base(oid, kind):
        return {
            "obligation_id": oid,
            "case_id": case_id,
            "kind": kind,
            "document_id": None,
            "doc_pair": None,
            "dimension": None,
            "field": None,
            "question": None,
            "closure_criterion": "",
            "status": "open",
            "closure": None,
        }

    for field in fields:
        for doc in documents:
            o = base("FC-%s-%s" % (slug(field), slug(doc)), "field_cell")
            o["document_id"] = doc
            o["field"] = field
            o["closure_criterion"] = (
                "answered_with_evidence：给出 value/unit 且附 source_document_id+paragraph_id+quote，"
                "quote 须逐字落在该段落内；或 not_reported_confirmed：声明检索范围（search_scope 列出已检索段落）"
                "且 note 说明；或 conflict_preserved：附双方证据；或 out_of_scope：note 说明理由。"
            )
            obligations.append(o)

    for dim in dimensions:
        for a, b in itertools.combinations(documents, 2):
            o = base("CMP-%s-%s-vs-%s" % (slug(dim), slug(a), slug(b)), "comparability")
            o["doc_pair"] = [a, b]
            o["dimension"] = dim
            o["closure_criterion"] = (
                "判定两文档在维度 %s 上是否可比：answered_with_evidence 且 value ∈ "
                "{comparable, not_comparable, partially_comparable}，附证据段落 quote（建议同时给 "
                "secondary_* 双方证据）；维度根本无意义时可 out_of_scope 并说明。" % dim
            )
            obligations.append(o)

    for q in questions:
        o = base("Q-%s" % slug(q["id"]), "question")
        o["question"] = q["text"]
        o["closure_criterion"] = (
            "回答该问题：answered_with_evidence（value 为答案，附 source_document_id+paragraph_id+quote）；"
            "或 not_reported_confirmed（附检索范围）；或 conflict_preserved（附双方证据，不得合并）。"
        )
        obligations.append(o)

    with open(args.out, "w", encoding="utf-8") as f:
        for o in obligations:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    n_fc = sum(1 for o in obligations if o["kind"] == "field_cell")
    n_cmp = sum(1 for o in obligations if o["kind"] == "comparability")
    n_q = sum(1 for o in obligations if o["kind"] == "question")
    print("[compile] case_id=%s 文档=%d 字段=%d 维度=%d 问题=%d" % (case_id, len(documents), len(fields), len(dimensions), len(questions)))
    print("[compile] 生成义务 %d 条：field_cell=%d comparability=%d question=%d -> %s" % (len(obligations), n_fc, n_cmp, n_q, args.out))


if __name__ == "__main__":
    main()
