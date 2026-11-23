# 合成示例 SYNTHETIC EXAMPLE（非正式案例结果）

本目录的全部材料均为本 Skill 作者编造，用于演示 `src-fidelity-item-forge`，不包含、也不能推导任何隐藏案例答案。`work_plan.json` 中 q2 的 locator 故意错写为 `doc1.para1`；其 quote 实际位于 `doc1.para2`。

## 运行

```bash
bash examples/run_example.sh /tmp/a1d81ca4-a-demo-out
```

也可省略参数，产物写入 `examples/out/`。

## 预期产物

- `source_index.json`：`source_excerpt.txt` 的 sha256、字节数、`doc1.para1` 与 `doc1.para2`、归一化文本和偏移映射；
- `verdicts_before_fix.json`：q1 为 `pass`，q2 为 `fail`，机器原因为锚点漂移；
- `result_before_fix.json`：`status` 为“部分完成”，`item_bank` 只包含 q1；
- `failure_analysis_before_fix.md`：记录 q2 原始输出、失败原因与修法；
- `verdicts.json` 与最终 `result.json`：两条证据均 `pass`，状态为“成功”；
- `scoring_record.json`：修正后 q1、q2 的证据锚定分均为 2。

## 最终 `result.json` 关键字段

- `case_id`: `synthetic-demo-001`
- `answer_summary`: 已填充合成题卡摘要
- `item_bank`: 修正后的 2 张 `fit` 题卡
- `evidence_map`: 每题的 locator、quote 与机器 verdict
- `status_note`: 修正计划说明

正式 T2 工单要求 4 道题；本示例用 `--expected-count 2` 仅演示门禁机制。