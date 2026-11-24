# example_run.md — 合成示例运行说明

**本目录是合成示意案例，非正式测评结果。** 论文（mock_paper.txt）、case
（mock_case.json）、findings 草稿（findings_draft.json）均为虚构，文中人名、
单位、期刊名、DOI、基金号全部虚构。

## 如何复跑

```bash
bash examples/run_example.sh
```

管道：`scripts/severity_gate.py`（R1–R8 严重度闸门）→ `scripts/fp_screen.py`
（FP-01…FP-10 误报鉴别）→ `scripts/adjudicate.py`（A1–A5 对抗复核），全部输出
写入 `examples/output/`。

## 合成论文埋入的已知问题

- 文献 [2] 年份/卷号与（虚构的）外部记录不符 —— 元数据错误
- 文献 [5] 期刊名与医学影像主题不符且无法外部核验 —— 疑似捏造信号（仅本地单信号）
- 缺伦理声明（涉及人体临床数据）—— norm_issue
- "显著优于所有已报道基线方法"但全文无对比实验 —— 证据不足
- 文献 [4] 是会议论文且无 DOI —— 学科惯例，**不应**报
- 正文 "van der Berg 等" vs 文献表 "van der Berg, J." —— 著录变体，**不应**报
- "P < 0.05" 与 "p = 0.032" 写法并存 —— 统计报告习惯，**不应**报
- 中文摘要简略、英文摘要详细但结论一致 —— 惯例，**不应**报

## 草稿设计与实际处置（逐条核对，全部符合预期）

| finding | 设计预期 | 实际处置 |
|---|---|---|
| F-001 图像复用指控（evidence_kind=none 却声称 critical） | 降待复核 | R3 封顶 + R1 封顶 → minor；A3 裁定**待复核** ✓ |
| F-002 会议论文无 DOI | drop | FP-01 **drop（误报排除）** ✓ |
| F-003 作者名拼写变体 | drop | FP-03 **drop（误报排除）** ✓ |
| F-004 元数据错误（逐字 quote + 外部记录） | 保持 major | R8 keep → A5 **维持 major/确认** ✓ |
| F-005 缺伦理声明 | 保 norm_issue/major | R8 keep → A5 **维持 major/确认**，未误判 misconduct ✓ |
| F-006 建议性条目 | info | R5 封顶 info → A4 **维持 info** ✓ |
| F-007 无依据绝对化论断（有逐字 quote） | 保持 major | A5 **维持 major/确认** ✓ |
| F-008 疑似捏造文献（仅本地单信号，断网） | 封顶 major + 待复核 | R3 封顶 → A3 **待复核** ✓ |
| F-009 p 值写法差异 | drop | R1/R2 降级后 FP-07 **drop** ✓ |
| F-010 中英文摘要详略差异 | drop | FP-10 **drop** ✓ |

## 输出文件解读

- `gated_findings.json` / `severity_downgrade_log.json`：第一道闸门后的 findings
  与逐条触发规则（audit_trail 含 rule 名与动作）。
- `screened_findings.json` / `fp_screen_log.json`：每条 finding 的
  keep/downgrade/drop 决定与鉴别规则名；drop 条目不删除，`verdict_status=误报排除`。
- `adjudication.json`：幸存 finding 的对抗复核卡（prosecution/defense/ruling）
  与终审裁定。
- `final_findings.json`：三道闸门后的最终 findings（交付用）。
- `calibration_log.md`：人读校准日志，一张表看全 10 条的处置链路与触发规则名。
