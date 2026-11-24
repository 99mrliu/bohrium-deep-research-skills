# 合成示例（synthetic / 合成数据，仅供演示与自检）

`synthetic_case/` 是一个**全合成**的微型案例：15 条虚构的低光图像增强
（low-light image enhancement）文献记录（L001–L015, 2015–2024），每条记录带
`"synthetic": true` 标记。其中：

- **L009**（2021）与 **L010**（2022）对同一量（Retinex 式增强 → YOLOv5 在
  ExDark 上的 mAP@0.5）给出相反结论（+4.2 点 vs -0.3 点不显著），用于演示
  冲突证据双侧配对。
- `retrieval_log_good.jsonl`：两条满足闭合纪律（hits == kept + len(excluded)）
  的查询行；q1 为 `source=provided-corpus` 伪查询行；q2 含一条外部引用
  （arXiv:2599.00001），演示 external_refs 标记（非致命）。
- `retrieval_log_bad.jsonl`：一行 hits(10) != kept(6) + excluded(1)，
  触发 `closure_violation`。
- `gaps_good.json`：两条带完整排除证据的空白声明（missing-population-or-setting
  与 conflict-unresolved），近失记录与声明主题真实重叠。
- `gaps_bad.json`：四条坏声明，分别触发 `bare_gap_claim`（裸声明）、
  `irrelevant_near_miss`（近失记录与声明主题零重叠）、`unknown_gap_type`、
  `unknown_query`。
- `conflicts_good.json`：双侧齐全（record_ids + 数值 + 位置）的冲突条目。
- `conflicts_bad.json`：一条单侧条目（`missing_side`）+ 一条两侧数值相同
  的伪冲突（`not_a_conflict`）。

## 运行

```
bash examples/run_example.sh
```

脚本会真实运行四条流水线并把产物复制到 `example_output/`：

- `good/`：全部 exit 0 —— canon.jsonl、retrieval_report.json、
  gap_verdicts.json（均 admissible）、conflict_report.json（admissible）。
- `bad/`：三条校验各 exit 1 —— retrieval_report_bad.json（closure_violation）、
  gap_verdicts_bad.json（四种违规）、conflict_report_bad.json（missing_side +
  not_a_conflict），外加各命令的 stdout 日志。

末尾的 PROOF 行逐条断言上述违规码确实触发、good 路径确实通过。
