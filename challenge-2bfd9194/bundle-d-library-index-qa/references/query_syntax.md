# 检索语法与降级规则（query.py / indexer.py）

## 索引侧

- 文本判定：扩展名白名单（txt/md/csv/tsv/json/jsonl/log/xml/tex/py/dat/xy/cfg/ini/ris/bib）或可解码性判定（UTF-8 → GB18030 依次尝试，不可打印字符比例 <5%）。
- 全文入库前做 **CJK bigram 展开**：连续中文串转成空格分隔的二字组（"温度条件" → `温度 度条 条件`），拉丁词原样。sqlite unicode61 分词器不切中文，这是纯标准库下让 FTS5 命中中文的最简可靠办法。
- 表：`fts(path, content)`（FTS5 虚表；降级时普通表）、`docs(path, content)`（原文，供 snippet 与逐字核对）、`files(...)`（目录清单）。
- 单文件超过 2MB 截断索引，text_status=indexed_truncated。

## 查询侧（query.py）

1. **切词块**：问题按标点与"的/了/和/与/及/在"切成词块；拉丁词小写；去掉"什么/哪个/哪些/多少/怎样/如何/请问/吗/呢"等疑问词；去掉词块尾巴的"是什么/为什么/是多少/有哪些"。
2. **FTS5 MATCH**：每个中文词块转 bigram 后**块内 OR**（召回优先，bm25 把命中 bigram 多的文档自然排前）；词块之间先试 **AND**（match_mode=fts5_and），零命中自动降级为 **OR**（match_mode=fts5_or）。取 top-5。
3. **LIKE 降级**（catalog.db 为降级库时自动启用）：like_and（全部词块命中）→ like_or（部分命中），match_mode 如实记录。
4. **snippet**：命中词在**原文**（docs 表）中的位置，前后各取 60 字符；越界侧加省略号 …。snippet 一定是原文子串（去掉 …、换行视为空格后），verify_index.py 逐条全查。
5. **无命中 → status=unanswered，answer 留空，绝不编答案。**

## QA_LOG.json（JSONL，每行一条）

```json
{"question": "...", "answer": "...", "evidence": [{"path": "data/xx.txt", "snippet": "…"}],
 "confidence": "high|medium|low", "status": "answered|partially_answered|unanswered",
 "match_mode": "fts5_and", "note": "可选"}
```

- `answered`：答案可从 evidence snippet 直接推出，confidence 可 high。
- `partially_answered`：命中相关但不充分，confidence ≤ medium。
- `unanswered`：无命中或命中无关，evidence 可留空或留参考命中，confidence=low。
- 正式运行：模型读 work/query_raw.json → 写 work/qa_answers.json → `run_case.py qa --answers ...` 合并。`--auto-answer`（top-1 snippet 作草稿 + confidence=low + note="auto draft, 合成示例"）**仅供合成示例复跑**。

## sqlite3 CLI 速查

```sql
-- FTS5：中文查 bigram（块内 OR、词间 AND 手写）
SELECT path FROM fts WHERE fts MATCH '"温度" OR "度条" OR "条件"';
-- 降级库：
SELECT path FROM fts WHERE content LIKE '%温度%';
-- 核对 snippet 是否原文子串：
SELECT content FROM docs WHERE path='data/XRD原始数据说明.txt';
```
