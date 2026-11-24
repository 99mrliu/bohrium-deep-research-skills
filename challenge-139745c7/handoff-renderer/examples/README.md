# 合成最小示例（handoff-renderer）

**本目录是合成示例，用于说明接口与流程，不是正式案例结果。**

`library/` 内含 4 个合成文件：`proposal_v1_2023-03-01.md`、
`proposal_final_2023-06-15.md`（同一报告的两个版本，演示版本族）、
`hplc_B2023-014.csv`、`notes.txt`。`case.json` 两个提问：
一个命中终稿，一个无命中（演示 no_match 写入 INDEX 与 answers.json）。

## 运行

```bash
cd examples
python3 run_example.py
```

在本目录生成 `work/` 与 `output/`（完整交付包：manifest.json、INDEX.md、
index.html、metadata.csv、tree.md、structure.svg、preview_structure.png、
preview_index.png、answers.json、result.json、checklist_report.json）。

## 预期结果（合成示例的期望行为）

- manifest.json `completeness.ok == true`（4 个输入各映射一次）。
- structure.svg 与 INDEX.md 均有 `preview_report.json` 中 `valid == true`
  的 PNG 预览（可用图片查看器打开目检）。
- result.json 含 case_id 与 output_contract 全部字段，status=complete；
  q2 为 no_match 且检索词可见。
- checklist_report.json `ok == true`。
