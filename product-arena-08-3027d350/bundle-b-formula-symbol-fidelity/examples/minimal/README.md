# minimal 示例（SYNTHETIC / 合成）

**免责声明**：本示例为人工合成的词级 TSV，**不是**从真实 PDF 提取的数据，
仅用于端到端演示 formula-symbol-fidelity 流水线。

## 输入构造（inputs/）

- `words.tsv`：2 页、84 个词（7 列简单格式：`page x0 y0 x1 y1 size text`），含：
  - 4 条居中显示公式，行尾编号 (1)、(2)、(2)、(3)；
  - 一个**上标**：`E = m c` + 抬升 8pt、字号缩小的 `2`（y1 相对基线 −8.0）；
  - 一个**下标**：`a` + 下沉的 `i`（y1 相对基线 +3.0）；
  - 希腊字母 α、β、Δ、σ、∂；
  - 一个**不可映射字符**：U+E000（Private Use Area），必须进入 `unknown`；
  - 一处**编号异常**：(2) 重复出现两次，必须被标记为 inconsistency；
  - 4 行长正文（左对齐、无符号密度）作为阴性对照，不应被判为数学行。
- `case.json`：合成案例，`case_id = synthetic-minimal-001`，
  `output_contract` 字段为 `equations` / `symbol_audit` / `uncertainty`。
- `task.md`：合成任务书。

## 运行命令（在 examples/minimal 目录下）

```bash
python3 ../../scripts/math_detect.py --input inputs/words.tsv --out outputs/math_lines.jsonl
python3 ../../scripts/symbol_fidelity.py --math-lines outputs/math_lines.jsonl --input inputs/words.tsv --out-dir outputs
python3 ../../scripts/eq_index.py --linearized outputs/math_linearized.jsonl --inventory outputs/symbol_inventory.json --case inputs/case.json --out-dir outputs
```

或从 skill 根目录一键复现：`sh scripts/run_example.sh`。

## outputs/ 是真实运行结果

`outputs/` 下全部文件（math_lines.jsonl、math_linearized.jsonl、
symbol_inventory.json、equations_index.json、result.json、run.log）均为上述
命令的**真实运行产物**，并经人工目检确认：

| 检查点 | 结果 |
|---|---|
| 上标还原 | `E = m c^{2}`（script_notes: dev=−8.0, superscript）✔ |
| 下标还原 | `a_{i} = b`（script_notes: dev=+3.0, subscript）✔ |
| 希腊字母映射 | α→`\alpha`、β→`\beta`、Δ→`\Delta`、σ→`\sigma`（×2）、∂→`\partial`，raw/输出计数 6=6 对账通过 ✔ |
| 不可映射字符 | U+E000 保留原文并列入 `unknown`（page 2, line p2-l008），未猜测 ✔ |
| 编号异常 | (2) 重复 2 次 → 两条记录 `verification=duplicate_number`，anomalies 记录 ✔ |
| 正文阴性对照 | 4 行正文 0 条误判（lines_total=8, candidates=4）✔ |
| result.json | `status=partial`（1 unknown + 1 编号异常），契约三字段齐全，case_id 一致 ✔ |
