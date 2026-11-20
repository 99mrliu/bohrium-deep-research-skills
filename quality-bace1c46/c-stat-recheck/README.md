# stat-recheck-evidence-auditor

统计复核 + 审计级证据锚定 Skill：把文献统计口径的一致性核验变成可重算的
机械校验，把证据定位做到可自动验证（归一化子串 + 字符偏移），产出
"维度—判断—证据—等级"完整评价表与逐行可复现的审计协议。

## 依赖

- Python 3 ≥ 3.8，**仅标准库**（`subprocess` 调 `pdftotext` 允许；pdftotext
  缺失时回退 pypdf，若环境提供）。
- 无网络；全部路径参数化。

## 调用步骤

```bash
python3 scripts/extract_corpus.py  --input-dir /input --work-dir /app/work --output-dir /app/output
python3 scripts/harvest_numbers.py --work-dir /app/work
python3 scripts/recheck.py         --work-dir /app/work
python3 scripts/verify_quotes.py   --work-dir /app/work
python3 scripts/aggregate_grade.py --work-dir /app/work
python3 scripts/build_result.py    --work-dir /app/work --input-dir /input --output-dir /app/output
```

模型（LLM）只介入一处：`work/semantic_queue/*.jsonl` 中 needs_semantic
配对的语境裁决，批处理进行（每批 ≤10 条）。

## 输入

- `/input/case.json`：防御式解析。case_id 尝试 case_id/id/caseId；文献清单
  递归查找 documents/papers/references/files/literature/corpus/materials；
  不命中回退扫描 `/input` 下 *.pdf→*.txt→*.md→*.json；output_contract 递归
  查找 output_contract/contract/output_fields/required_fields 并原样镜像。
- `/input/task.md`：存在则优先作为任务说明。
- 文献材料：PDF / txt / md / Crossref / EuropePMC JSON 快照（仅摘要）。

## 输出

- `/app/output/result.json`：终版交付（任何失败点前已有 in_progress 部分版）。
- `/app/output/recheck_report.md`：复核行表 + 完整性缺口表 + 等级与推导。
- `/app/output/audit_trail.md`：复现协议（sha256、命令序列、逐行页码+偏移）。
- `/app/work/`：pages/ numbers/ recheck/ semantic_queue/ anchors/、
  docs.jsonl、verify_report.json、grades.json。

## 方法

1. 分页抽取（pdftotext -layout，换页符分页）。
2. 正则采集数字声明：n=、a/b (p%)、p 值、95% CI、均值±SD、中位数(IQR)、
   t/z/χ²/F（含 df）、OR/HR/RR；每条带页锚与所在句。
3. 一致性重算（规则全文见 rules/recheck_rules.md）：频数↔百分比、分层
   求和、摘要↔正文数值指纹、p 值近似重算（不完全 β/γ、erf）、效应方向。
   三态 pass/discrepancy/not_recomputable。
4. 报告完整性缺口表（rules/completeness_checklist.md）。
5. 摘录归一化校验（连字符断行还原+空白折叠→子串匹配→偏移报告），失败
   整行降级。
6. 明文阈值分级：adequate / concerns / serious_concerns / ungradable
   （仅摘要语料附加 limited）。

## 限制

- **近似精度**：p 值重算为近似实现，典型绝对误差 <1e-9，但报告值本身带
  舍入；边界情形（重算值落在报告声明边界 ±0.005 内）按 pass 处理并注明。
- **无法重算情形**：缺 df、缺总 n、缺配对 CI、未配对 p 值 →
  not_recomputable，脚本绝不猜测补全。
- **语义配对误差**：摘要↔正文指纹、分层 n 配对、检验量↔p 配对是启发式，
  可能错配；可疑配对一律入 needs_semantic 队列由模型确认，且 discrepancy
  只表示"内部不一致需人工核对"，不代表论文错误。
- 句切分为保守近似；表格跨页、图片内数字（无 OCR 文本层）采集不到。

## 失败处理

- 单篇抽取失败 → 标 failed 继续；终版 status=partial_failure。
- 无任何可重算内容 → ungradable，仍交付缺口表与审计文件。
- 部分 result.json 在 PDF 抽取前已写入，任何中断不会零交付。

## 自查

```bash
python3 -m py_compile scripts/*.py
# 合成 fixture 全链路（见 examples/example_walkthrough.md）应至少识别
# 1 个 pass、1 个 discrepancy、1 个 not_recomputable；
# verify_report.json 中 failed_rows 应为 0；result.json 可被 json.load 解析。
```
