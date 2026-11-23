# 最小调用示例（合成示例，非正式案例）

输入为手工合成材料（虚构论文片段，仅用于演示核验链接口）：

- `inputs/sources/page1.txt, page2.txt`：模拟上游抽取的每页源文本；
- `inputs/raw_dump.txt`：模拟 `pdftotext` 原始全文（含 48 字符页眉页脚）；
- `inputs/claims.jsonl`：4 条拟引用引文（q1/q2 逐字、q3 有一处拼写差异、
  q4 为带理由的 waiver）；
- `inputs/case.json`：合成契约（answer/evidence/boundaries + 一个非必需字段）；
- `inputs/result_draft.json`：故意不合规的交付草稿（缺 boundaries、
  success 与证据链矛盾）。

真实执行记录（2026-11-23，产物在 `outputs/`，已目检）：

```bash
# 1. 引文门禁 → fail（q3 near_miss 0.97 近似提示、q4 waiver 合规）
python3 ../../scripts/verify_quotes.py --claims inputs/claims.jsonl \
  --sources inputs/sources --out /tmp/eg_work
# 2. 覆盖台账 → balanced（48 页眉页脚字符记账后 0% 未解释）
python3 ../../scripts/coverage_ledger.py --raw inputs/raw_dump.txt \
  --kept inputs/sources/page1.txt inputs/sources/page2.txt \
  --dropped /tmp/eg_work/drops.jsonl --out /tmp/eg_work
# 3. 草稿契约校验 → FAIL（contract_report_draft_FAIL.json）
python3 ../../scripts/contract_check.py --case inputs/case.json \
  --result inputs/result_draft.json --out /tmp/eg_work/draft
# 4. status_writer 写入三类边界、降级 partial、合并门禁摘要
# 5. 复检 → PASS（contract_report_fixed_PASS.json，仅 1 条非必需字段 warn）
```

要点：草稿 FAIL 不是缺陷演示而是门禁的正常工作方式——不合格的 result.json
被拦下，修复（补字段、降级状态、写清边界）后复检 PASS 才允许交付。
