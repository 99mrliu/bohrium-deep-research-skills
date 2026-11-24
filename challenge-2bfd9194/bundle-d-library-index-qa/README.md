# library-index-qa

科研资料库"整理 → 检索 → 问答 → 重建"闭环 Skill（bundle D）。重心：**落库的终点是可查询**——整理完的資料库必须能被检索、能带证据回答问题、能仅凭清单重建索引。

## 用途

把 /input 下混杂的科研文件（论文、数据、扫描件、补充材料、草稿、行政备注、别名副本、旧版本）按内容哈希去重后落库，建立 sqlite FTS5 全文目录（无 FTS5 自动降级 LIKE，不崩溃），回答 case.json/task.md 中的 questions/searches/queries——**每条答案必须引用真实文件路径 + 原文 snippet，答不出标 unanswered**，最后演练"只凭清单与落库文件重建索引"并由独立校验器逐项核对。

## 运行

```bash
# 全自动（检索阶段只出命中，答案留占位）
python3 scripts/run_case.py all --input /input --work /app/work --out /app/output

# 模型读 work/query_raw.json 撰写 work/qa_answers.json 后合并并复验
python3 scripts/run_case.py qa --input /input --work /app/work --out /app/output --answers /app/work/qa_answers.json
python3 scripts/run_case.py verify --input /input --work /app/work --out /app/output
python3 scripts/run_case.py finalize --input /input --work /app/work --out /app/output
```

分阶段：`init / scan / plan / apply / index / qa / rebuild / verify / finalize`。合成示例复跑可加 `--auto-answer`（正式案例禁用）。

## 输出（/app/output/）

result.json、library/、LIBRARY_MANIFEST.jsonl、index/catalog.db、index/index_stats.json、QA_LOG.json（JSONL：question/answer/evidence/confidence/status）、SEARCH_GUIDE.md、REBUILD_DIFF.json、duplicates.json、version_chains.json、operations_journal.jsonl、skipped_and_conflicts.json、audit_report.json。

## 文件说明

| 路径 | 作用 |
|---|---|
| SKILL.md | harness agent 唯一会认真读的文件：契约、规则、模型职责 |
| scripts/run_case.py | 分阶段编排器（stdlib only） |
| scripts/indexer.py | 建 catalog.db：files 表 + FTS5/LIKE 全文索引 + 原文表，出 index_stats.json 与 SEARCH_GUIDE.md |
| scripts/query.py | 问题提取 + 中文 bigram 检索 top-5 + snippet，写 QA_LOG.json；支持 --answers 合并模型答案 |
| scripts/rebuild_index.py | 归档恢复演练：凭清单+library 重建索引，出 REBUILD_DIFF.json |
| scripts/verify_index.py | 独立校验器：只读 /input 与 /app/output，出 audit_report.json |
| references/query_syntax.md | 检索语法与降级规则 |
| references/metadata_dictionary.md | manifest / catalog.db / QA_LOG 字段字典 |
| examples/ | **合成示例**（非正式案例结果）：输入 12 个小文件 + 真实跑出的输出 |

## 限制

- 仅 Python 3 标准库；不联网；不写 /input；不解析 PDF/扫描件正文（二进制如实标 not_indexed_binary）。
- catalog.db 是运行期二进制产物（契约允许），不随 skill 提交。
- FTS5 不可用时检索降级为 LIKE（功能可用，index_stats.json 记 degraded:true，result.json 如实降级）。
