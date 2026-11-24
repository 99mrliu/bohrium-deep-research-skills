#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""query.py — 对 catalog.db 做带证据问答（stdlib only）。

流程：
1. 提取问题：--questions 指定 JSON；缺失时用 --case/--task 防御式递归提取
   （键名 questions|searches|queries|qa，值为字符串或对象数组）。
2. 每问：FTS5 MATCH（中文词块转 bigram，块内 AND；先全块 AND，零命中降级块间 OR），
   取 top-5，snippet 为命中词前后各 60 字符的原文片段（来自 docs 表）。
   无 FTS5（degraded 库）时自动改用 LIKE。
3. 写出：
   - --raw：原始命中（供模型阅读后撰写答案）。
   - --out QA_LOG.json（JSONL，每行 {"question","answer","evidence":[{"path","snippet"}],
     "confidence","status", ...}）。
   - --auto-answer：仅合成示例用，把 top-1 snippet 作为草稿答案，
     confidence=low、status=partially_answered、note="auto draft, 合成示例"。
   - --answers：模型撰写的答案 JSON（[{"question","answer","confidence","status"}]），
     按 question 精确匹配合并进 QA_LOG（证据沿用真实命中）。正式运行走这条路。
"""
import argparse
import json
import os
import re
import sqlite3
import sys

QUESTION_KEYS = ("questions", "searches", "queries", "qa")
STOPWORDS = {"什么", "哪个", "哪些", "多少", "怎样", "怎么样", "如何", "请", "请问",
             "一下", "吗", "呢", "是否", "是不是", "有没有", "的", "了", "在", "是",
             "和", "与", "及", "或", "谁", "哪", "为何", "为什么"}
CJK_SPLIT = re.compile(r"[的了和与及在，。、；：？！?!,.;:·\s]+")
SNIPPET_RADIUS = 60


def is_cjk(ch):
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def extract_questions_from_obj(obj, found):
    """防御式递归提取问题：找 questions|searches|queries|qa 键，值为字符串或对象数组。"""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(key, str) and key.lower() in QUESTION_KEYS:
                _collect_value(val, found)
            else:
                extract_questions_from_obj(val, found)
    elif isinstance(obj, list):
        for item in obj:
            extract_questions_from_obj(item, found)


def _collect_value(val, found):
    if isinstance(val, str):
        if val.strip():
            found.append(val.strip())
    elif isinstance(val, dict):
        for k in ("question", "q", "query", "text", "search", "keyword"):
            if isinstance(val.get(k), str) and val[k].strip():
                found.append(val[k].strip())
                return
    elif isinstance(val, list):
        for item in val:
            _collect_value(item, found)


def load_questions(questions_path, case_path, task_path):
    """优先 questions_path；否则从 case.json / task.md 提取。返回 (questions, origin)。"""
    if questions_path and os.path.isfile(questions_path):
        with open(questions_path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        found = []
        _collect_value(data, found)
        if not found:
            extract_questions_from_obj(data, found)
        return list(dict.fromkeys(found)), "questions_file"
    found = []
    for path in (case_path, task_path):
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            try:
                extract_questions_from_obj(json.loads(text), found)
            except json.JSONDecodeError:
                # task.md 等非 JSON：按行找“问题/检索”行
                for line in text.splitlines():
                    m = re.match(r"\s*(?:问题|检索|query|question)[:：]\s*(.+)", line,
                                 re.IGNORECASE)
                    if m:
                        found.append(m.group(1).strip())
    return list(dict.fromkeys(found)), "extracted_from_case_or_task"


def split_chunks(question):
    """把问题切成检索词块：CJK 词块 + 拉丁词。去疑问词。"""
    chunks = []
    buf, buf_cjk = [], None  # buf_cjk: 当前缓冲是否 CJK
    for ch in question:
        cjk = is_cjk(ch)
        if not cjk and not ch.isalnum():
            if buf:
                s = "".join(buf)
                chunks.extend(_flush_cjk(s) if buf_cjk else [s])
                buf, buf_cjk = [], None
            continue
        if buf and cjk != buf_cjk:
            s = "".join(buf)
            chunks.extend(_flush_cjk(s) if buf_cjk else [s])
            buf = []
        buf.append(ch if cjk else ch.lower())
        buf_cjk = cjk
    if buf:
        s = "".join(buf)
        chunks.extend(_flush_cjk(s) if buf_cjk else [s])
    seen, out = set(), []
    for c in chunks:
        if c and c not in STOPWORDS and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _flush_cjk(run):
    parts = [p for p in CJK_SPLIT.split(run) if p]
    out = []
    for p in parts:
        for sw in ("是什么", "为什么", "是多少", "有哪些"):
            if p.endswith(sw) and len(p) > len(sw):
                p = p[: -len(sw)]
        if p and p not in STOPWORDS:
            out.append(p)
    return out


def bigrams(chunk):
    if all(is_cjk(c) for c in chunk) and len(chunk) > 1:
        return [chunk[i] + chunk[i + 1] for i in range(len(chunk) - 1)]
    return [chunk]


def fts_quote(term):
    return '"' + term.replace('"', ' ') + '"'


def build_match(chunks, joiner):
    """词块内 bigram 取 OR（召回优先，bm25 自然把命中多的排前）；词块间由 joiner 决定。"""
    exprs = []
    for c in chunks:
        terms = [fts_quote(t) for t in bigrams(c)]
        exprs.append("(" + " OR ".join(terms) + ")" if len(terms) > 1 else terms[0])
    return (" %s " % joiner).join(exprs)


def make_snippet(content, chunks):
    lower = content.lower()
    pos = -1
    for c in sorted(chunks, key=len, reverse=True):
        pos = lower.find(c.lower())
        if pos >= 0:
            break
        for bg in bigrams(c):
            pos = lower.find(bg.lower())
            if pos >= 0:
                break
        if pos >= 0:
            break
    if pos < 0:
        pos = 0
    start = max(0, pos - SNIPPET_RADIUS)
    end = min(len(content), pos + SNIPPET_RADIUS)
    snippet = content[start:end].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(content) else "")


def search(conn, chunks, top, degraded):
    """返回 (hits, match_mode)。hits: [{"path","snippet"}]"""
    cur = conn.cursor()
    if not chunks:
        return [], "no_terms"
    if degraded:
        cur.execute("SELECT path, content FROM docs")
        rows = cur.fetchall()
        strict, loose = [], []
        for path, content in rows:
            low = content.lower()
            hit = [c for c in chunks if c.lower() in low
                   or any(bg.lower() in low for bg in bigrams(c))]
            if len(hit) == len(chunks):
                strict.append((path, content, len(hit)))
            elif hit:
                loose.append((path, content, len(hit)))
        chosen, mode = (strict, "like_and") if strict else (loose, "like_or")
        chosen.sort(key=lambda r: (-r[2], r[0]))
        return ([{"path": p, "snippet": make_snippet(c, chunks)}
                 for p, c, _ in chosen[:top]], mode) if chosen else ([], mode)
    for joiner, mode in (("AND", "fts5_and"), ("OR", "fts5_or")):
        try:
            cur.execute(
                "SELECT fts.path, docs.content FROM fts"
                " JOIN docs ON docs.path = fts.path"
                " WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?",
                (build_match(chunks, joiner), top))
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            return search(conn, chunks, top, degraded=True)
        if rows:
            return [{"path": p, "snippet": make_snippet(c, chunks)}
                    for p, c in rows], mode
    return [], "no_hit"


def main(argv=None):
    ap = argparse.ArgumentParser(description="对 catalog.db 做带证据问答")
    ap.add_argument("--db", required=True)
    ap.add_argument("--questions", help="work/questions.json")
    ap.add_argument("--case", help="/input/case.json（questions 缺失时提取）")
    ap.add_argument("--task", help="/input/task.md（同上）")
    ap.add_argument("--ask", help="交互式单问")
    ap.add_argument("--out", help="QA_LOG.json（JSONL）输出路径")
    ap.add_argument("--raw", help="原始命中 JSON 输出路径（供模型读）")
    ap.add_argument("--answers", help="模型撰写答案 JSON，按 question 合并")
    ap.add_argument("--auto-answer", action="store_true",
                    help="仅合成示例：top-1 snippet 作草稿答案，confidence=low")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM sqlite_master WHERE name='fts' AND sql LIKE '%fts5%'")
        degraded = cur.fetchone() is None
    except sqlite3.OperationalError:
        degraded = True

    if args.ask:
        questions, origin = [args.ask], "cli"
    else:
        questions, origin = load_questions(args.questions, args.case, args.task)

    answers_map = {}
    if args.answers and os.path.isfile(args.answers):
        with open(args.answers, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if isinstance(item, dict) and item.get("question"):
                    answers_map[item["question"].strip()] = item

    raw_out, log_entries = [], []
    for q in questions:
        chunks = split_chunks(q)
        hits, mode = search(conn, chunks, args.top, degraded)
        raw_out.append({"question": q, "chunks": chunks,
                        "match_mode": mode, "hits": hits})
        entry = {"question": q, "answer": "", "evidence": hits,
                 "confidence": "low", "status": "unanswered",
                 "match_mode": mode}
        model_ans = answers_map.get(q.strip())
        if model_ans:
            entry["answer"] = model_ans.get("answer", "")
            entry["confidence"] = model_ans.get("confidence", "medium")
            entry["status"] = model_ans.get(
                "status", "answered" if hits else "unanswered")
            entry["note"] = "model answer merged from --answers"
            if isinstance(model_ans.get("evidence_paths"), list):
                keep = set(model_ans["evidence_paths"])
                entry["evidence"] = [h for h in hits if h["path"] in keep] or hits
        elif args.auto_answer and hits:
            entry["answer"] = hits[0]["snippet"]
            entry["confidence"] = "low"
            entry["status"] = "partially_answered"
            entry["note"] = "auto draft, 合成示例"
        elif not hits:
            entry["status"] = "unanswered"
            entry["answer"] = ""
        log_entries.append(entry)
    conn.close()

    result = {"questions_origin": origin, "count": len(questions),
              "degraded_db": degraded, "entries": raw_out}
    if args.raw:
        os.makedirs(os.path.dirname(os.path.abspath(args.raw)), exist_ok=True)
        with open(args.raw, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for e in log_entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(json.dumps({"questions": len(questions), "origin": origin,
                      "answered_or_partial": sum(
                          1 for e in log_entries if e["status"] != "unanswered"),
                      "unanswered": sum(
                          1 for e in log_entries if e["status"] == "unanswered")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
