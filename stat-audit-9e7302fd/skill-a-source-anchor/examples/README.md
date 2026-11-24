# 合成示例说明(非真实案件结果)

本目录全部内容为**合成示例**:论文文本、审查发现、运行产物均由技能作者手工
构造,仅用于演示本技能的「提取 → 保真度门 → 锚定核验门」流水线,
**不是、也不得被当作任何真实案件的审查结果**。

## 文件清单

| 文件 | 说明 |
|---|---|
| `synthetic_paper.txt` | 合成示例论文(方法+结果节选,约 90 行,含一个换页符模拟 2 页;全文虚构) |
| `sample_findings.jsonl` | 3 条候选发现:F-001、F-002 为真实逐字摘录(F-001 故意用半角括号,演示规范化匹配);F-003 故意把原文「估算」误写为「估计」,**必须被锚定门拒绝** |
| `run_example.sh` | 端到端演示脚本,产物写入 `examples/output/` |
| `expected_output/` | 实际运行流水线得到的参考输出(见下) |

## 运行方法

```bash
bash run_example.sh
```

预期结果:

1. `pdf_to_anchored_text.py` 退出码 0,报告 2 页、91 行、1753 字符;
2. `source_integrity.py` 退出码 0,`integrity_report.json` 中 `verdict="ok"`;
3. `anchor_verify.py` **退出码 1**(门是真实的):F-001、F-002 通过核验并附带
   `{page, line, end_page, end_line, char_start, char_end, context}`,
   F-003 被拒绝并写入 `rejects.jsonl`(原因:规范化后仍无精确匹配)。

## expected_output/ 内容

- `anchors_excerpt.jsonl` — anchors.jsonl 前 15 行(完整文件由运行生成);
- `integrity_report.json` — 保真度报告(verdict=ok);
- `verified_findings.jsonl` — 通过核验的 2 条发现,含锚点与上下文;
- `rejects.jsonl` — 被拒绝的 1 条发现,含拒绝原因。

偏移量已用脚本回切原文核验:`raw[char_start:char_end]` 规范化后与规范化后的
quote 完全相等;F-001 命中 P2 L4,F-002 命中 P2 L19。

## 对齐要求

修改任何脚本行为(标记格式、规范化规则、阈值)后,必须重新运行
`run_example.sh` 并用新产物更新 `expected_output/`,保持示例与实现一致。
