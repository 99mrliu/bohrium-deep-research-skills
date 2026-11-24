#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""indexer.py — 落库后为资料库建立可检索目录 catalog.db（stdlib only）。

输入：LIBRARY_MANIFEST.jsonl（每行一个来源文件的落库记录）+ library/ 目录。
输出：index/catalog.db（files 表 + fts 全文索引 + docs 原文表）、index_stats.json、SEARCH_GUIDE.md。

- 文本类文件（扩展名白名单 + 可解码性判定，UTF-8 -> GB18030 依次尝试）全文入 fts。
- 二进制/不可解码文件只入 files 表，text_status=not_indexed_binary。
- sqlite 无 FTS5 时自动降级为普通表 + LIKE 检索，stats 记 degraded:true，绝不崩溃。
- 幂等：每次运行 DROP 重建全部表。
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata

TEXT_EXTS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".log", ".xml",
    ".tex", ".py", ".dat", ".xy", ".cfg", ".ini", ".ris", ".bib",
}
MAX_INDEX_BYTES = 2 * 1024 * 1024  # 单文件全文入库上限，超出截断并标记


def is_cjk(ch):
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def cjk_bigram_expand(text):
    """把 CJK 连续串展开为空格分隔的 bigram，便于 FTS5 unicode61 分词命中中文。"""
    out, run = [], []

    def flush():
        if not run:
            return
        if len(run) == 1:
            out.append(" " + run[0] + " ")
        else:
            out.append(" " + " ".join(run[i] + run[i + 1]
                                      for i in range(len(run) - 1)) + " ")
        run.clear()

    for ch in text:
        if is_cjk(ch):
            run.append(ch)
        else:
            flush()
            out.append(ch)
    flush()
    return "".join(out)


def decode_text(raw):
    """依次尝试 UTF-8 / GB18030；返回 (text, encoding) 或 (None, None)。"""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None, None


def looks_text(raw):
    """按可解码性 + 可打印比例判定是否文本。"""
    text, enc = decode_text(raw[:65536])
    if text is None:
        return False
    sample = text[:4096]
    if not sample:
        return True
    bad = sum(1 for c in sample
              if not (c.isprintable() or c in "\r\n\t") and not is_cjk(c))
    return bad / len(sample) < 0.05


def guess_title(text, fallback):
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:60]
    return fallback


def read_manifest(manifest_path):
    rows = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_catalog(manifest_path, library_dir, db_path):
    """重建 catalog.db。返回 stats dict。幂等：DROP 后重建。"""
    rows = read_manifest(manifest_path)
    stats = {
        "manifest_rows": len(rows),
        "files_table_rows": 0,
        "unique_library_files": 0,
        "indexed_text_files": 0,
        "not_indexed_binary": 0,
        "skipped_rows": 0,
        "truncated_files": 0,
        "by_category": {},
        "by_text_status": {},
        "degraded": False,
        "degrade_reason": None,
        "db_path": db_path,
    }
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE files ("
        " source_path TEXT, rel_path TEXT, sha256 TEXT, size INTEGER,"
        " category TEXT, mtime TEXT, title_guess TEXT, text_status TEXT,"
        " action TEXT, duplicate_of TEXT)"
    )
    fts5_ok = True
    try:
        cur.execute("CREATE VIRTUAL TABLE fts USING fts5(path, content)")
    except sqlite3.OperationalError as exc:
        fts5_ok = False
        cur.execute("CREATE TABLE fts (path TEXT PRIMARY KEY, content TEXT)")
        stats["degraded"] = True
        stats["degrade_reason"] = "FTS5 unavailable, fallback to LIKE: %s" % exc
    cur.execute("CREATE TABLE docs (path TEXT PRIMARY KEY, content TEXT)")

    seen_paths = set()
    for row in rows:
        rel_path = row.get("rel_path")
        category = row.get("category") or "_unassigned"
        action = row.get("action") or ""
        text_status = "skipped"
        title_guess = row.get("title_guess") or ""
        if rel_path:
            abs_path = os.path.join(library_dir, rel_path)
            if row.get("duplicate_of"):
                # 别名行：内容同规范副本，不重复索引
                text_status = "alias_of_indexed"
            elif not os.path.isfile(abs_path):
                text_status = "missing_on_disk"
            else:
                with open(abs_path, "rb") as f:
                    raw = f.read()
                ext = os.path.splitext(rel_path)[1].lower()
                if (ext in TEXT_EXTS or looks_text(raw)) and looks_text(raw):
                    text, enc = decode_text(raw)
                    truncated = False
                    if len(raw) > MAX_INDEX_BYTES:
                        text = text[:MAX_INDEX_BYTES]
                        truncated = True
                        stats["truncated_files"] += 1
                    if not title_guess:
                        title_guess = guess_title(
                            text, os.path.splitext(os.path.basename(rel_path))[0])
                    text_status = "indexed_truncated" if truncated else "indexed"
                    if rel_path not in seen_paths:
                        cur.execute(
                            "INSERT INTO docs VALUES (?, ?)", (rel_path, text))
                        cur.execute(
                            "INSERT INTO fts VALUES (?, ?)",
                            (rel_path, cjk_bigram_expand(text)))
                else:
                    text_status = "not_indexed_binary"
            seen_paths.add(rel_path)
        else:
            stats["skipped_rows"] += 1
        cur.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?)",
            (row.get("source_path"), rel_path, row.get("sha256"),
             row.get("size"), category, row.get("mtime"),
             title_guess, text_status, action, row.get("duplicate_of")))
        stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
        stats["by_text_status"][text_status] = \
            stats["by_text_status"].get(text_status, 0) + 1

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM files")
    stats["files_table_rows"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT rel_path) FROM files WHERE rel_path IS NOT NULL")
    stats["unique_library_files"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM fts")
    stats["indexed_text_files"] = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(DISTINCT rel_path) FROM files"
        " WHERE text_status='not_indexed_binary'")
    stats["not_indexed_binary"] = cur.fetchone()[0]
    denom = stats["unique_library_files"] or 0
    stats["index_coverage"] = (
        round(stats["indexed_text_files"] / denom, 4) if denom else None)
    stats["index_coverage_note"] = (
        "indexed_text_files / unique_library_files；二进制文件不计入分子，属预期")
    conn.close()
    return stats


SEARCH_GUIDE_TEMPLATE = """# SEARCH_GUIDE — 如何检索这份资料库（合成示例产物亦适用）

本资料库的检索入口是 `index/catalog.db`（SQLite，仅标准库即可打开）。
表结构：

- `files`：每个来源文件一行（含别名与跳过项）。列：source_path, rel_path, sha256, size, category, mtime, title_guess, text_status, action, duplicate_of。
- `fts`：全文索引（rel_path -> 内容）。FTS5 模式下为虚表；降级模式下为普通表。
- `docs`：已索引文本文件的原文（用于核对 snippet）。

当前索引模式：**{mode}**{degrade_note}
索引覆盖率：{coverage}（{indexed}/{unique} 个库内唯一文件全文可检索）

## 方式一：用 query.py（推荐）

```bash
# 交互式单问
python3 scripts/query.py --db index/catalog.db --ask "量子点实验的温度条件" 
# 批量问答（questions.json 为字符串数组或 {{"question": ...}} 数组）
python3 scripts/query.py --db index/catalog.db --questions work/questions.json --out QA_LOG.json
```

## 方式二：sqlite3 CLI 自查

```bash
# 看目录清单
sqlite3 index/catalog.db "SELECT rel_path, category, text_status FROM files ORDER BY rel_path;"
# FTS5 模式：中文须按 bigram 查询（"温度条件" -> "温度 度条 条件"，AND 语义）
sqlite3 index/catalog.db "SELECT path FROM fts WHERE fts MATCH '\"温度\" AND \"度条\" AND \"条件\"';"
# 英文/数字直接用词
sqlite3 index/catalog.db "SELECT path FROM fts WHERE fts MATCH '\"xrd\"';"
# 降级模式（无 FTS5）：用 LIKE
sqlite3 index/catalog.db "SELECT path FROM fts WHERE content LIKE '%温度%' AND content LIKE '%条件%';"
# 核对某条 snippet 是否为原文子串
sqlite3 index/catalog.db "SELECT content FROM docs WHERE path='data/量子点发光二极管实验记录.txt';"
```

## 检索规则备忘

- 中文查询先切词块（按标点与"的/了/和/与/及/在"切分，去掉"什么/哪个/多少"等疑问词），
  每个词块转成 bigram 后块内 AND；先全块 AND，零命中自动降级为块间 OR 并按相关度排序。
- 返回 top-5，snippet 取命中词前后各 60 字符的**原文**片段（来自 docs 表，可直接核对）。
- 检索不到就如实标 `unanswered`，不要凭文件名猜测回答。
"""


def write_search_guide(path, stats):
    mode = "LIKE 降级模式" if stats["degraded"] else "FTS5"
    degrade_note = ("\n降级原因：%s" % stats["degrade_reason"]) if stats["degraded"] else ""
    cov = stats.get("index_coverage")
    content = SEARCH_GUIDE_TEMPLATE.format(
        mode=mode, degrade_note=degrade_note,
        coverage=("%.1f%%" % (cov * 100)) if cov is not None else "n/a",
        indexed=stats["indexed_text_files"], unique=stats["unique_library_files"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main(argv=None):
    ap = argparse.ArgumentParser(description="为落库资料库建立可检索 catalog.db")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--out-dir", required=True, help="index 输出目录")
    ap.add_argument("--stats", help="index_stats.json 路径（默认 <out-dir>/index_stats.json）")
    ap.add_argument("--guide", help="SEARCH_GUIDE.md 路径（默认 <out-dir>/../SEARCH_GUIDE.md）")
    args = ap.parse_args(argv)

    db_path = os.path.join(args.out_dir, "catalog.db")
    stats = build_catalog(args.manifest, args.library, db_path)
    stats_path = args.stats or os.path.join(args.out_dir, "index_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    guide_path = args.guide or os.path.join(
        os.path.dirname(os.path.abspath(args.out_dir)), "SEARCH_GUIDE.md")
    write_search_guide(guide_path, stats)
    print(json.dumps({"db": db_path, "stats": stats_path,
                      "degraded": stats["degraded"],
                      "indexed": stats["indexed_text_files"],
                      "files_rows": stats["files_table_rows"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
