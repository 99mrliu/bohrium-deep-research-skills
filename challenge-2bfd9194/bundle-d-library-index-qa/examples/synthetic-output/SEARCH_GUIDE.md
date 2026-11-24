# SEARCH_GUIDE — 如何检索这份资料库（合成示例产物亦适用）

本资料库的检索入口是 `index/catalog.db`（SQLite，仅标准库即可打开）。
表结构：

- `files`：每个来源文件一行（含别名与跳过项）。列：source_path, rel_path, sha256, size, category, mtime, title_guess, text_status, action, duplicate_of。
- `fts`：全文索引（rel_path -> 内容）。FTS5 模式下为虚表；降级模式下为普通表。
- `docs`：已索引文本文件的原文（用于核对 snippet）。

当前索引模式：**FTS5**
索引覆盖率：100.0%（10/10 个库内唯一文件全文可检索）

## 方式一：用 query.py（推荐）

```bash
# 交互式单问
python3 scripts/query.py --db index/catalog.db --ask "量子点实验的温度条件" 
# 批量问答（questions.json 为字符串数组或 {"question": ...} 数组）
python3 scripts/query.py --db index/catalog.db --questions work/questions.json --out QA_LOG.json
```

## 方式二：sqlite3 CLI 自查

```bash
# 看目录清单
sqlite3 index/catalog.db "SELECT rel_path, category, text_status FROM files ORDER BY rel_path;"
# FTS5 模式：中文须按 bigram 查询（"温度条件" -> "温度 度条 条件"，AND 语义）
sqlite3 index/catalog.db "SELECT path FROM fts WHERE fts MATCH '"温度" AND "度条" AND "条件"';"
# 英文/数字直接用词
sqlite3 index/catalog.db "SELECT path FROM fts WHERE fts MATCH '"xrd"';"
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
