# 最小调用示例（示意输出，非正式案例结果）

输入（示意）：`/input/case.json`（research_question + constraints.time_range + output_contract）、
`/input/search09_export.json`（15 条记录，含标注的合成重复与冲突意见）、`/input/reference_papers.json`（9 篇）。

```bash
python3 .../run_all.py --case /input/case.json --input-dir /input --work /app/work --out /app/output
# [index.py] rc=0 {"ok": true, "docs": 15, "vocab": 380, "failures": 1}
# [search.py] rc=0 {"ok": true, "label": "Q1-main", "returned": 8, ...}
# [rankcheck.py] rc=0 {"ok": true, "searches": 1, "empty_verdicts": 0}

python3 .../expand.py --terms "passivation,efficiency"
# {"expanded": {"passivation": {"variants": ["passivated", "passivating", "钝化"], ...}}}

python3 .../search.py --work /app/work \
  --query "+perovskite passivation -photocatalysis" --query-zh "钙钛矿 钝化" \
  --year-from 2022 --year-to 2025 --exclude-type "review,perspective" \
  --label "Q2-controlled" --out /app/output
# {"ok": true, "label": "Q2-controlled", "returned": 6, ...}

python3 .../finalize.py --case /input/case.json --input-dir /input --work /app/work --out /app/output
# {"ok": true, "status": "complete", "candidates": 9, "contract_fields": 7}
```

产物：`result.json`（candidates 按分排序、searches 摘要、rank_audit、status、uncertainty）、
`search_Q1-main.json`（每条候选含 score / matched_terms / facet_check / origin）、`rank_audit.json`
（各查询清单文献命中率@top5，0 命中时 verdict=snapshot_empty）。
