---
name: evidence-contract-gate
description: >-
  文献解析交付物的证据核验与契约合规门。当解析流水线（任何上游抽取器）已经产出
  全文/表格/引文/result.json，需要回答"核得回吗、丢的东西去哪了、契约字段齐不齐、
  状态诚不诚实"时触发本技能。四个组件：verify_quotes.py 逐字引文门禁（NFKC 归一化
  命中源文本，近似给 difflib 提示，豁免必须带理由）、coverage_ledger.py 字符覆盖
  台账（kept/dropped/unaccounted 三方对账）、contract_check.py 对照 case.json 的
  output_contract 逐项校验 result.json、status_writer.py 强制"未报告/无法判断/
  材料冲突"三类边界分开写入并防止 degraded 结果标 success。不在范围内：上游抽取
  本体（阅读顺序、表格结构各有专门技能）、科学结论的对错判断（只核引文与契约）。
---

# evidence-contract-gate — 证据核验 · 覆盖台账 · 契约合规门

**核心原则：交付前过门，不过不交付。读不出的标注，对不上的剔除，缺字段的修好再交。**

本技能是解析质量的**下游门**：它不替代表格/顺序等上游解析器，而是给任何上游产物
做可复核性核验。四个脚本仅用 Python 3 标准库，任何判定都落 JSON 报告。

## 总览

```
上游解析产物（fulltext/表格/引文清单 + result.json 草稿）
  → verify_quotes.py    引文逐字门禁      gate_report.json     （不过→剔除或 waiver）
  → coverage_ledger.py  字符覆盖台账      coverage_ledger.json （>2% 未解释→partial）
  → status_writer.py    诚实状态写入      修订后的 result.json
  → contract_check.py   契约逐项校验      contract_report.json （FAIL→修复→复检）
```

## 运行契约（平台评测环境）

- 输入：`/input/case.json`、`/input/task.md`、案例材料；工作区 `/app/work`；
  交付区 `/app/output`。
- 平台运行案例时，上游解析（抽文本、理结构）由 Agent 按 task.md 完成；本技能
  负责交付前的核验链。**顺序不可颠倒**：先门禁剔除不合格引文，再写状态，最后
  契约校验必须 PASS 才能视为完成。
- `result.json` 含原 `case_id` 与 `output_contract` 全部字段；`status` 必须
  与证据链一致（门禁未过/覆盖不平衡/有边界说明 → 不允许 success）。
- 预算纪律：核验脚本不耗模型请求；900 秒内先把草稿 + 三份报告落盘，再修复复检。

## 操作步骤

1. **汇集核验输入**：源文本目录（抽取得到的每页 .txt）、原始全文 dump
   （pdftotext 原样输出）、交付物文本清单、拟引用的引文清单 claims.jsonl
   （`{"id","quote","page"?}`）。
2. **引文门禁**：
   `python3 scripts/verify_quotes.py --claims /app/work/claims.jsonl --sources /app/work/sources --out /app/work`
   `status=fail` 时：near_miss → 回原文核对修正 quote 或从交付剔除；
   missing → 剔除或补 waiver（必须 waiver_reason）。
3. **覆盖台账**：
   `python3 scripts/coverage_ledger.py --raw /app/work/raw_dump.txt --kept <交付物文本...> --dropped /app/work/drops.jsonl --out /app/work`
   `unbalanced` → 找出未解释字符来源（常见：页眉页脚忘记记账、图片页、
   抽取重复），补 drops 或在 uncertainty 说明。
4. **写诚实状态**：
   `python3 scripts/status_writer.py --result /app/output/result.json --status <success|partial|failed> [--not-reported ...] [--cannot-judge ...] [--conflict ...] [--handoff ...] --gate ... --coverage ...`
   三类边界（未报告/无法判断/材料冲突）分开写；有边界或门禁失败时
   success 会被自动降为 partial。
5. **契约校验（交付前最后一步）**：
   `python3 scripts/contract_check.py --case /input/case.json --result /app/output/result.json --out /app/work`
   FAIL → 按 fails 逐条修复后复检；PASS 才交付。

## 判定规则摘要

| 门 | 通过条件 | 不过怎么办 |
|-|-|-|
| 引文门禁 | quote 归一化后逐字命中源文本 | 修正为原文措辞；确需保留走 waiver+理由 |
| 覆盖台账 | 未解释字符 ≤2%（可调阈值） | 补记账或 uncertainty 说明，status 降 partial |
| 状态一致 | 无 degraded 信号才可 success | status_writer 自动降级 |
| 契约校验 | required 字段全在、置空有解释、状态合法、有证据定位 | 修复后复检 |

## 异常与限制

- 门禁的归一化是 NFKC + 空白折叠 + 小写化；全半角、CJK 空格、连字（ﬁ→fi）
  不影响命中，但**改字**（如同义改写）必然不命中——这是特性：引文必须逐字。
- 覆盖台账按可见字符（去空白）计数；图片、公式字形不算字符，需用
  `figure_pixels` 类记账说明。
- 契约校验对 output_contract 的字段名做精确匹配；值的内容合理性由人工/Judge 判断，
  本门只保证"齐、非空、有解释、状态合法"。
- 本技能不验证科学结论对错，只验证"结论引的话原文里确实有、契约要求的字段确实在"。

## 最小示例

`examples/minimal/` 为**合成示例**（非正式案例）：合成源文本两页 + 原始 dump、
4 条引文（2 逐字命中、1 拼写近似、1 waiver）、一份故意不合规的
`inputs/result_draft.json`。真实执行记录（已目检，产物在 `outputs/`）：

1. 门禁：`fail`——q3 拼写差异（horizental/vertical）检出为 near_miss，
   q4 waiver 合规记账；
2. 台账：`balanced`——48 个页眉页脚字符有类别记账，0% 未解释；
3. 草稿契约校验：`FAIL`（缺 boundaries 字段、success 与边界矛盾）；
4. status_writer 写入三类边界并降级 partial 后复检：`PASS`。
