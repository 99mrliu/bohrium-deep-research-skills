# rob-signal-dual-adjudicator

文献偏倚风险量表化评价 Skill：偏倚领域集 + 信号问题树 + 双通道独立初评 +
明文规则裁决 + 人工复核入口 + 引用门控。对每篇文献产出
"领域—判断—证据（逐字摘录+页锚）—裁决来源—整体等级（含推导）"的可复核评价表。

## 依赖

- Python ≥ 3.8，**仅标准库**；
- 外部命令 `pdftotext`（poppler）用于 PDF 抽取；不可用时回退 pypdf（若环境
  恰好可导入），再失败则该文献标 `failed`，流水线继续；
- 全程离线，无网络访问。

## 调用步骤

```bash
W=/app/work; O=/app/output
python3 scripts/extract_corpus.py --case /input/case.json --task /input/task.md \
    --input-dir /input --workdir $W --output-dir $O
python3 scripts/select_domains.py --workdir $W
python3 scripts/collect_signals.py --workdir $W
# —— 模型双通道初评，写 channel_p/<doc_id>.jsonl 与 channel_n/<doc_id>.jsonl
#    （格式见 templates/channel_row.md）——
python3 scripts/adjudicate.py --workdir $W
python3 scripts/verify_quotes.py --workdir $W
python3 scripts/apply_overrides.py --workdir $W   # 无人工改判也可跑
python3 scripts/build_result.py --workdir $W --output-dir $O
```

## 输入

- `/input/case.json`：防御式解析。case_id 尝试 `case_id`/`id`/`caseId`；
  文献清单递归查找 `documents`/`papers`/`references`/`files`/`literature`/
  `corpus`/`materials`；output_contract 递归查找 `output_contract`/`contract`/
  `output_fields`/`required_fields` 并全部镜像进 result.json。
- `/input/task.md`：具体要求优先，摘要写入 result.json。
- 清单缺失时按 `*.pdf → *.txt → *.md → *.json`（含 title/abstract 的快照）
  扫描 `/input`。
- 可选 `/app/work/review_overrides.jsonl`：人工改判（格式见
  `templates/override_format.md`）。

## 输出

- `/app/output/result.json`：case_id、镜像的 output_contract、status、
  documents[]（领域评价 + 整体等级 + 推导）、adjudication_summary、
  quote_verification、overrides_applied、uncertainties、change_log。
  **10 秒内先写部分版（status=in_progress），任何失败点前已有交付。**
- `/app/output/rob_report.md`：人读版评价表。
- `/app/output/scale_revision_suggestions.md`：量表改进建议骨架。
- 工作目录中间产物：pages/ anchors/ signals/ channel_p|n/ adjudicated/
  verified/ final/、adjudication_ledger.jsonl、verify_report.json、
  overrides_applied.json。

## 方法概要

1. **领域集**：按启发式文献类型（RCT/观察性/诊断/系统综述/其他）选择
   `domains/` 定义的领域集，每领域 2–4 个信号问题（肯定性证据/否定性
   证据/弃权条件明文规定）。
2. **双通道初评**：脚本按信号问题关键词窗口召回候选句（预打 P/N 标签），
   通道 P 正向取证、通道 N 反向查漏，模型只判断候选句，输出领域级
   判断 + 逐字摘录 + 页锚 `p<页>.¶<段>`。
3. **裁决**：R1 一致直采；R2 有摘录者优先；R3 双方无证据 → insufficient；
   R4 双方有证据冲突 → 取较高风险并标 `adjudicated_conservative`；
   R5 单通道降级处理。全部分歧进 `adjudication_ledger.jsonl`。
4. **人工复核**：review_overrides.jsonl 合并改判并记录变更；分歧/改判
   高频领域沉淀为 `scale_revision_suggestions.md`。
5. **分级**：按 `rules/judgment_levels.md` 映射表 M0–M6 显式推导整体等级，
   禁止孤立等级。
6. **引用门控**：归一化（去空白换行、去连字符断行、NFKC 全半角折叠）
   子串校验；标错页则全文重定位并报告，找不到则降级 insufficient。

## 限制

- 候选句召回依赖关键词表，全新表述可能漏召回 → 该领域倾向 `insufficient`
  （诚实弃权，可在量表改进建议中补关键词）。
- 图表/图像内容不可解析；涉及纯图证据的领域按证据不足处理。
- 启发式类型判定可能误分（标 `uncertain`），可用一次模型请求批量确认。
- 摘要级文献整体等级封顶 `insufficient_evidence`。

## 失败处理

零文献 → status=completed_with_warnings；case.json 解析失败 → 目录扫描；
PDF 失败 → 标 failed 跳过；摘录校验失败 → 降级 + 报告；改判格式错误 →
拒绝并记入 overrides_rejected。所有异常写入 result.json 的
uncertainties / change_log。

## 自测

```bash
python3 -m py_compile scripts/*.py
# 合成 fixture 全链路（/tmp/rob_fixture 下含 case.json、txt 文献、
# EuropePMC 风格 JSON、双通道 jsonl、review_overrides.jsonl）：
bash /tmp/rob_fixture/run_pipeline.sh
```

fixture 搭建脚本见评测提交说明；自测覆盖 extract → select → collect →
adjudicate → verify → overrides → build 全链路。
