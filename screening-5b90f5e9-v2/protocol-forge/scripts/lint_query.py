#!/usr/bin/env python3
"""lint_query.py -- 检索式语法门禁（确定性静态检查）。

对 search_protocol.json 中每条检索式（或单独传入的查询串）执行规则检查：
  L1 括号配平；L2 引号配平；
  L3 布尔运算符不得位于串首/串尾；L4 运算符不得相邻（AND AND / OR NOT NOT 等，
     但 AND NOT 合法）；L5 字段标签必须在方言白名单内；
  L6 通配符 * 只允许出现在词尾；L7 空括号 () 禁止；
  L8 同一检索式内字段标签混用提示（warn，不 fail）；
  L9 运算符不得紧贴括号（"OR )"、"( AND"）。

方言白名单见 references/dialect_fields.md 并在本文件 DIALECT_FIELDS 中实现。

产物 lint_report.json：{queries:[{database,status,issues:[{rule,severity,span,message}]}],overall}
退出码：0=全部 PASS（允许 WARN）；3=存在 ERROR；2=输入缺失。
"""
import argparse
import json
import os
import re
import sys

DIALECT_FIELDS = {
    "pubmed": {"tiab", "ti", "tw", "mh", "mesh", "dp", "date - publication",
               "la", "pt", "au", "ta", "all"},
    "scopus": {"title-abs-key", "title", "abs", "key", "all", "au", "doi",
               "pubyear", "language", "srctype"},
    "wos": {"ts", "ti", "ab", "ak", "au", "do", "dp", "dop", "la", "dt"},
}

OPS = ("AND", "OR", "NOT", "NEAR")


def tokenize(query):
    """粗略词法：括号、引号串、运算符、字段标签、普通词。"""
    tokens = []
    i, n = 0, len(query)
    while i < n:
        ch = query[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            tokens.append(("paren", ch, i))
            i += 1
            continue
        if ch == '"':
            j = query.find('"', i + 1)
            if j == -1:
                tokens.append(("unterminated-quote", query[i:], i))
                break
            tokens.append(("phrase", query[i:j + 1], i))
            i = j + 1
            continue
        m = re.match(r"[A-Za-z][A-Za-z0-9\-]*(\*?)", query[i:])
        if m:
            word = m.group(0)
            tokens.append(("word", word, i))
            i += m.end()
            continue
        m = re.match(r"\[[^\]]*\]|[A-Z-]+\([^)]*\)|[=:]", query[i:])
        if m:
            tokens.append(("field", m.group(0), i))
            i += m.end()
            continue
        tokens.append(("char", ch, i))
        i += 1
    return tokens


def lint_one(database, query):
    issues = []

    def add(rule, severity, span, message):
        issues.append({"rule": rule, "severity": severity,
                       "span": span, "message": message})

    # L1 括号配平
    depth, min_pos = 0, None
    for idx, ch in enumerate(query):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0 and min_pos is None:
                min_pos = idx
    if depth != 0 or min_pos is not None:
        add("L1", "ERROR", min_pos if min_pos is not None else len(query) - 1,
            "括号不配平（最终深度 %d）" % depth)

    # L2 引号配平
    if query.count('"') % 2 != 0:
        add("L2", "ERROR", query.rfind('"'), "双引号数为奇数，存在未闭合引号")

    tokens = tokenize(query)
    # 操作数序列：短语、普通词、括号、字段标签都参与结构判断
    seq = [t for t in tokens if t[0] in ("phrase", "word", "paren", "field")]

    def is_op(tok):
        return tok[0] == "word" and tok[1].upper() in OPS

    # L3 运算符位置
    if seq and is_op(seq[0]):
        add("L3", "ERROR", seq[0][2], "运算符 %s 位于检索式开头" % seq[0][1])
    if seq and is_op(seq[-1]):
        add("L3", "ERROR", seq[-1][2], "运算符 %s 位于检索式结尾" % seq[-1][1])

    # L4 运算符相邻（AND NOT 合法）
    for a, b in zip(seq, seq[1:]):
        if is_op(a) and is_op(b):
            ua, ub = a[1].upper(), b[1].upper()
            if not (ua in ("AND", "OR") and ub == "NOT"):
                add("L4", "ERROR", b[2], "运算符相邻：%s %s" % (ua, ub))

    # L5 字段标签白名单
    fields = DIALECT_FIELDS.get(database)
    seen_fields = set()
    if fields is not None:
        for m in re.finditer(r"\[([^\]]+)\]", query):
            tag = m.group(1).strip().lower()
            seen_fields.add(tag)
            if tag not in fields:
                add("L5", "ERROR", m.start(),
                    "字段标签 [%s] 不在 %s 白名单" % (m.group(1), database))
        for m in re.finditer(r"([A-Za-z][A-Za-z0-9\-]{1,})\s*=\s*\(", query):
            tag = m.group(1).lower()
            seen_fields.add(tag)
            if tag not in fields:
                add("L5", "ERROR", m.start(),
                    "字段前缀 %s= 不在 %s 白名单" % (m.group(1), database))
        for m in re.finditer(r"\b([A-Z][A-Z0-9\-]{2,})\(", query):
            tag = m.group(1).lower()
            seen_fields.add(tag)
            if tag not in fields:
                add("L5", "ERROR", m.start(),
                    "函数字段 %s( 不在 %s 白名单" % (m.group(1), database))
    # L8 混用提示
    if len(seen_fields) > 3:
        add("L8", "WARN", 0, "单条检索式使用 %d 种字段标签，注意可移植性" % len(seen_fields))

    # L9 运算符紧贴括号（"OR )"、"( AND"）
    for a, b in zip(seq, seq[1:]):
        if is_op(a) and b[0] == "paren" and b[1] == ")":
            add("L9", "ERROR", b[2], "运算符 %s 后紧跟右括号" % a[1])
        if a[0] == "paren" and a[1] == "(" and is_op(b) and b[1].upper() in ("AND", "OR"):
            add("L9", "ERROR", b[2], "左括号后紧跟运算符 %s" % b[1])

    # L6 通配符位置
    for m in re.finditer(r"\*", query):
        prev = query[m.start() - 1] if m.start() > 0 else " "
        nxt = query[m.start() + 1] if m.start() + 1 < len(query) else " "
        if not (prev.isalnum()) or (nxt.isalnum()):
            add("L6", "ERROR", m.start(), "通配符 * 只能出现在词尾")

    # L7 空括号
    for m in re.finditer(r"\(\s*\)", query):
        add("L7", "ERROR", m.start(), "存在空括号 ()")

    status = "PASS"
    if any(i["severity"] == "ERROR" for i in issues):
        status = "FAIL"
    elif any(i["severity"] == "WARN" for i in issues):
        status = "WARN"
    return {"database": database, "status": status, "issues": issues,
            "query_preview": query[:120]}


def main():
    ap = argparse.ArgumentParser(description="检索式语法门禁")
    ap.add_argument("--protocol", help="search_protocol.json 路径")
    ap.add_argument("--database", help="单条查询的方言")
    ap.add_argument("--query", help="单条查询串（与 --database 同用）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    targets = []
    if args.protocol:
        if not os.path.isfile(args.protocol):
            print("LINT-INPUT-MISSING: %s" % args.protocol, file=sys.stderr)
            sys.exit(2)
        proto = json.load(open(args.protocol, encoding="utf-8"))
        for q in proto.get("queries", []):
            targets.append((q["database"], q["query"]))
        for extra in proto.get("extra_queries", []):
            targets.append((extra["database"], extra["query"]))
    elif args.database and args.query:
        targets.append((args.database, args.query))
    else:
        print("LINT-INPUT-MISSING: 需 --protocol 或 --database+--query", file=sys.stderr)
        sys.exit(2)

    results = [lint_one(db, q) for db, q in targets]
    overall = "PASS"
    if any(r["status"] == "FAIL" for r in results):
        overall = "FAIL"
    elif any(r["status"] == "WARN" for r in results):
        overall = "WARN"
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "lint_report.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"overall": overall, "queries": results}, fh,
                  ensure_ascii=False, indent=2)
    print("LINT %s (%d queries) -> %s" % (overall, len(results), out_path))
    sys.exit(0 if overall != "FAIL" else 3)


if __name__ == "__main__":
    main()
