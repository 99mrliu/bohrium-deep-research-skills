#!/usr/bin/env python3
"""build_protocol.py -- 把结构化研究问题编译为逐数据库可执行检索协议。

输入 research_question.json：
{
  "question_id": "rq-demo",
  "question_text": "...",
  "concept_blocks": [
    {"block_id": "P", "label": "population",
     "terms": ["type 2 diabetes", "T2DM"]},
    ...
  ],
  "databases": ["pubmed", "scopus", "wos"],
  "date_from": "2015-01-01", "date_to": "2026-12-31",
  "languages": ["en"],
  "search_date": "2026-11-24"
}

输出 search_protocol.json：每个数据库一条 {database, query, field_scope,
date_limit, language_limit, block_trace}。block_trace 记录每个概念块对应
生成的查询子句，使"标准—概念块—检索式"的映射可复核。

组装规则是确定性的：同输入必得同输出。检索式的语法合法性不由本脚本
保证，必须用 lint_query.py 过门禁。
退出码：0=正常；2=输入缺失或不合法。
"""
import argparse
import json
import os
import sys

DIALECTS = {
    "pubmed": {
        "term": lambda t: '"%s"[tiab]' % t,
        "and": " AND ", "or": " OR ",
        "date": lambda d1, d2: '("' + d1.replace("-", "/") + '"[Date - Publication] : "'
                               + d2.replace("-", "/") + '"[Date - Publication])',
        "field_scope": "title/abstract [tiab]；日期 [dp]",
    },
    "scopus": {
        "term": lambda t: "TITLE-ABS-KEY(\"%s\")" % t,
        "and": " AND ", "or": " OR ",
        "date": lambda d1, d2: "PUBYEAR > %d AND PUBYEAR < %d"
                               % (int(d1[:4]) - 1, int(d2[:4]) + 1),
        "field_scope": "TITLE-ABS-KEY；PUBYEAR",
    },
    "wos": {
        "term": lambda t: 'TS=("%s")' % t,
        "and": " AND ", "or": " OR ",
        "date": lambda d1, d2: "DOP=(%s/%s)"
                               % (d1, d2),
        "field_scope": "TS= 主题字段；DOP= 出版日期",
    },
}


def fail(msg):
    print("BUILD-ERROR: " + msg, file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="检索协议编译")
    ap.add_argument("--question", required=True, help="research_question.json 路径")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    if not os.path.isfile(args.question):
        fail("question file missing: %s" % args.question)
    try:
        q = json.load(open(args.question, encoding="utf-8"))
    except Exception as exc:
        fail("question json invalid: %s" % type(exc).__name__)

    blocks = q.get("concept_blocks") or []
    dbs = q.get("databases") or []
    if not blocks or not dbs:
        fail("concept_blocks 与 databases 均不可为空")
    for b in blocks:
        if not b.get("block_id") or not b.get("terms"):
            fail("每个 concept_block 需要 block_id 与非空 terms: %r" % b)

    date_from = q.get("date_from")
    date_to = q.get("date_to")
    queries = []
    for db in dbs:
        d = DIALECTS.get(db)
        if d is None:
            fail("未知数据库方言：%s（支持：%s）" % (db, ", ".join(DIALECTS)))
        parts, trace = [], []
        for b in blocks:
            clause = "(" + d["or"].join(d["term"](t) for t in b["terms"]) + ")"
            parts.append(clause)
            trace.append({"block_id": b["block_id"], "label": b.get("label", ""),
                          "clause": clause})
        if date_from and date_to:
            parts.append(d["date"](date_from, date_to))
        query = d["and"].join(parts)
        queries.append({
            "database": db,
            "query": query,
            "field_scope": d["field_scope"],
            "date_limit": {"from": date_from, "to": date_to},
            "language_limit": q.get("languages") or [],
            "block_trace": trace,
        })

    protocol = {
        "question_id": q.get("question_id", "rq-unknown"),
        "question_text": q.get("question_text", ""),
        "search_date": q.get("search_date", ""),
        "snapshot_policy": "有限快照：检索式按 search_date 限定覆盖范围，不声称实时或全局召回。",
        "queries": queries,
        "assembly_note": "概念块内 OR、块间 AND；日期/语种限定单独登记，语种限定在执行侧落实。",
    }
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "search_protocol.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(protocol, fh, ensure_ascii=False, indent=2)
    print("PROTOCOL %d queries -> %s" % (len(queries), out_path))
    sys.exit(0)


if __name__ == "__main__":
    main()
