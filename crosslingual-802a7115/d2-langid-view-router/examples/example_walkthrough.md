# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用 `examples/data/views.jsonl` 的**合成玩具数据**，仅说明接口与产物形态，
> **不是**平台正式案例的结果。合成结构刻意复刻跨语言已知文献检索的典型视图：
> 葡语原文全文、出版方英译全文（带翻译标记）、仅英文摘要记录、完全重复副本、
> 以及另一篇独立英文工作。

## 输入（合成）

`examples/data/views.jsonl`：5 条记录、2 个 work——

- `w1-pt-full`：W1 葡语原文全文（DOI 10.0000/synth.w1，长正文）；
- `w1-en-trans`：W1 英译全文（正文首句 "Translated from the Portuguese original."）；
- `w1-en-abs`：W1 仅摘要记录（无 body 字段）；
- `w1-en-dup`：`w1-en-trans` 的逐字副本；
- `w2-en-full`：W2 英文原文全文（DOI 10.0000/synth.w2）。

## 调用

```bash
python3 scripts/langid_views.py --roots examples/data --out examples/out
```

控制台输出（本次实际运行）：`{"status": "ok", "records": 5, "works": 2}`

## 产物（本次实际运行已目检）

`examples/out/views.json` 与 `examples/out/routing_report.md`。W1 的四个视图分类：

| record | detected | view | evidence |
|-|-|-|-|
| w1-pt-full | pt (0.941) | original | fullest body of its language |
| w1-en-trans | en (0.99) | translation | explicit marker: translated from |
| w1-en-abs | en (0.933) | abstract_only | no full body (0 chars) but abstract present |
| w1-en-dup | en (0.99) | duplicate | near-identical text to w1-en-trans (Jaccard≥0.9) |

路由表：W1 的 query_languages = {en, pt}；`w1-en-dup` countable=no（去重）；
W2 仅 en。DOI 聚类把 4 条 W1 记录（含无 DOI 重复副本经标题相似度）正确归并。

## 复核方式

对照 `views.json` 中每条记录的 `lang_evidence.scores` 与 `view_evidence`，
回指 `views.jsonl` 原始字段，确认分类依据确实存在。
