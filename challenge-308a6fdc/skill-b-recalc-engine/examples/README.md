# 最小调用示例（合成示例，非正式案例结果）

本示例演示 recalc-verify-engine 的完整接口与流程。**全部输入数据为虚构合成数据，
输出为示意产物，不冒充正式案例结果。**

## 输入（examples/input/）

- `case.json`：合成 case（case_id=`EXAMPLE-NOT-A-TEST-CASE`，含 output_contract 五键）。
- `task.md`：合成任务说明。
- `experiment_data.csv`：**虚构**的两组重复测量（control/treatment 各 5 次，文件头有合成声明）。
- `deliverable.md`：**故意含四类数字**的合成草稿，用于演示三态判定：
  - `4.3` —— 材料原文数字 → RAW-SUPPORTED；
  - `12.2%` —— 正确派生数字（重算值 12.1951%，誊写舍入）→ DERIVED-SUPPORTED；
  - `4.79` —— 错误派生数字（真均值 4.6）→ UNSUPPORTED（提示最接近重算值 mean=4.6）；
  - `p = 0.032` —— 材料未给出的 p 值 → UNSUPPORTED-PVALUE。

## 运行命令（真实执行，秒级完成）

```bash
SKILL_DIR=<本 bundle 根目录>
# 1) 摄入 + 重算（产物：recalc_table.md / derived_values.json / dataset_profile.json）
python3 "$SKILL_DIR/scripts/recalc.py" \
    --input-dir "$SKILL_DIR/examples/input" \
    --output-dir /tmp/recalc-work
# 2) 三态核验 + 装配 result.json（产物：verify_report.md / result.json / deliverable.md 副本）
python3 "$SKILL_DIR/scripts/verify_draft.py" \
    --draft "$SKILL_DIR/examples/input/deliverable.md" \
    --input-dir "$SKILL_DIR/examples/input" \
    --derived /tmp/recalc-work/derived_values.json \
    --case "$SKILL_DIR/examples/input/case.json" \
    --output-dir "$SKILL_DIR/examples/output"
```

正式运行时把 `--input-dir` 换成 `/input`、工作目录换成 `/app/work`、
输出目录换成 `/app/output`（`--case /input/case.json`）。

## 输出（examples/output/，由上述命令真实生成）

- `recalc_table.md`：重算表（n/mean/median/SD/SEM/min/max + 组间 diff/ratio/pct_change，附公式与输入）。
- `derived_values.json` / `dataset_profile.json`：机器可读重算账与数据剖面。
- `verify_report.md`：三态核验报告（本示例四类数字各命中一类）。
- `result.json`：契约化结果（output_contract 五键 + case_id 原样 + status/sources/uncertainty/change_log）。
- `deliverable.md`：交付稿副本（合成示例稿，其中 UNSUPPORTED 项按规则待处置）。

## 手工验算（供复核）

control=[4.1,4.3,3.9,4.2,4.0] → mean=4.1；treatment=[4.6,4.8,4.5,4.7,4.4] → mean=4.6；
百分比变化 = (4.6−4.1)/4.1×100% = 12.1951%；SD = 0.158114（n−1）。与重算表一致。
