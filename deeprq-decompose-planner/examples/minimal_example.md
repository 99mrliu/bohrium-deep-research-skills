# 最小调用示例（示意，非正式案例结果）

输入（示意）：

```json
// /input/case.json
{"case_id": "demo-1", "output_contract": {"status": "...", "answer": "..."},
 "task_md": "task.md"}
```

```markdown
<!-- /input/task.md -->
请综述 2020 年以来固态电池界面工程的进展，比较不同界面改性方法的
循环寿命，并指出尚未解决的科学问题。
```

执行：

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
  --case /input/case.json --input-dir /input --work /app/work --out /app/output
```

示意输出（节选，标注为示例）：

```json
{"ok": true, "case_id": "demo-1", "sub_questions": 5, "waves": 3, "blocked": []}
```

随后 /app/output 含：decomposition_tree.json（SQ-1…SQ-5，含六要素提取与
中英文检索式）、retrieval_plan.json（W1→W2 两层并行→W3 缺口补检，
预算 60/25 已校验）、run_journal.jsonl（含 genesis 与 run_case 两笔，
哈希链已建立）、coverage_matrix.json（5 行全"未检索"）、partial result.json。

Agent 接着按 retrieval_plan.json 逐笔检索并记账：

```bash
python3 /skills/weekly-skill/scripts/journal.py append \
  --journal /app/output/run_journal.jsonl --tool web_search \
  --args '{"query":"solid-state battery interface engineering review","numResults":5}' \
  --results-count 5 --results-digest 9f2c1a08b7d34e55 \
  --sq SQ-1 --note "W1-1 背景定界" --status ok
python3 /skills/weekly-skill/scripts/journal.py verify \
  --journal /app/output/run_journal.jsonl
# {"ok": true, "entries": 3, "chain_head": "a41b…"}   ← 示例值
python3 /skills/weekly-skill/scripts/finalize.py \
  --case /input/case.json --work /app/work --out /app/output
# {"ok": true, "journal_ok": true, "status": "partial", ...}  ← 示例值
```

最终 result.json 的 status 依覆盖情况为 success/partial；任何中断都留有
partial result.json 与已记账的日志，可被 journal.py verify/replay 独立复核。
