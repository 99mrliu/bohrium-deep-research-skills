#!/usr/bin/env python3
"""Compile natural-language questions into structured query JSON.

Extracts hard filters (year, batch, project, version, file type, path) and
concept terms (with lexicon expansion). Anything that looks like a constraint
but cannot be structured goes to unparsed_constraints -- never dropped silently.

Usage: forge_parse.py CASE_JSON LEXICON_JSON OUT_JSON
"""
import json
import re
import sys

YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
BATCH = re.compile(r"\b([A-Z]{1,3}\d{4}-\d{2,})\b")
VNUM = re.compile(r"\bv(\d+)\b", re.IGNORECASE)
PROJECT = re.compile(r"项目\s*([A-Za-z0-9一-鿿]{1,12})|([A-Z]{3,})\s*项目")
CJK = re.compile(r"[一-鿿]+")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
STOP = set("的了和是在有与及或其对这那中上个一为以于哪些哪个什么哪份在哪"
           "写在对应多少什么内容时候当时")
VERSION_WORDS = [("终稿", "final"), ("正式版", "final"), ("定稿", "final"),
                 ("初稿", "draft"), ("草稿", "draft"),
                 ("修订", "revised"), ("修改版", "revised")]
TYPE_WORDS = [("pdf", ["pdf"]), ("表格", ["csv", "xlsx", "tsv"]),
              ("文档", ["md", "txt", "docx"]), ("记录", ["md", "txt"]),
              ("数据", ["csv", "xlsx", "tsv", "json"])]


def bigrams(text):
    run = "".join(c for c in text if c not in STOP)
    return [run[i:i + 2] for i in range(len(run) - 1)]


def parse_question(qid, qtext, lexicon):
    filters = {}
    unparsed = []
    m = YEAR.search(qtext)
    if m:
        y = int(m.group(1))
        filters["year"] = y
        filters["date_after"] = "%d-01-01" % y
        filters["date_before"] = "%d-12-31" % y
    m = BATCH.search(qtext)
    if m:
        filters["batch"] = m.group(1)
    m = PROJECT.search(qtext)
    if m:
        filters["project"] = next(g for g in m.groups() if g)
    for word, tag in VERSION_WORDS:
        if word in qtext:
            filters["version"] = tag
            break
    m = VNUM.search(qtext)
    if m and "version" not in filters:
        filters["version"] = "v" + m.group(1)
    for word, exts in TYPE_WORDS:
        if word in qtext.lower():
            filters["file_type"] = exts
            break

    concepts = []
    expansion = {}
    for t in LATIN.findall(qtext):
        tl = t.lower()
        if not YEAR.fullmatch(tl) and not BATCH.fullmatch(t):
            concepts.append(tl)
    for run in CJK.findall(qtext):
        concepts.extend(bigrams(run))
    # lexicon expansion on multi-char CJK substrings of the question
    for canon, syns in lexicon.items():
        if canon in qtext:
            expansion[canon] = list(syns)
            concepts.extend(s.lower() for s in syns)
    concepts = sorted(set(concepts))
    # constraint-looking fragments we could not structure
    for frag in re.findall(r"(?:权限|加密|扫描件|副本|备份|大小|修改时间)[^，。？,?.]*", qtext):
        unparsed.append(frag)
    return {"question_id": qid, "question": qtext, "concepts": concepts,
            "expansion_log": expansion, "hard_filters": filters,
            "unparsed_constraints": unparsed, "filter_trace": {}}


def find_questions(case):
    for key in ("searches", "questions", "queries", "tasks"):
        v = case.get(key)
        if isinstance(v, list) and v:
            return [q if isinstance(q, dict) else {"id": "q%d" % i, "text": str(q)}
                    for i, q in enumerate(v)]
        if isinstance(v, str):
            return [{"id": "q0", "text": v}]
    return []


def main():
    case_p, lex_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    case = json.load(open(case_p, encoding="utf-8"))
    try:
        lexicon = json.load(open(lex_p, encoding="utf-8"))
        lexicon = {k: v for k, v in lexicon.items() if not k.startswith("_")}
    except Exception:
        lexicon = {}
    queries = [parse_question(q.get("id"), q.get("text", ""), lexicon)
               for q in find_questions(case)]
    if not lexicon:
        for q in queries:
            q.setdefault("notes", []).append("lexicon_missing")
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump({"case_id": case.get("case_id") or case.get("id"),
                   "queries": queries}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"n_queries": len(queries),
                      "n_with_filters": sum(1 for q in queries if q["hard_filters"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
