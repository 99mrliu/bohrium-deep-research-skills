# 最小调用示例运行记录（合成示例，非正式案例结果）

> 输入 `synthetic-case.json` 为虚构论文（SYN-2026-ML-33，GraphMixer 图神经网络，
> 7 个段落、2 个复合中文问题）。以下命令均真实执行。

## 命令序列

```bash
mkdir -p work/app/work work/app/output

# 1) 生成写作单（含论断语法提示）
python3 scripts/claim_lint.py scaffold --case examples/synthetic-case.json --work work/app/work
# stdout: scaffold ok: 2 question sheet(s) → Q1.md, Q2.md

# 2) 通读全部 7 段，按 claim-grammar.md 在写作单上写论断（模型步骤，略）

# 3) 汇编 result.json 与 answers.json（模型步骤）

# 4) 表达质量检查
python3 scripts/claim_lint.py lint --case examples/synthetic-case.json --result work/app/output/result.json
# stdout: lint done: 0 error(s), 0 warn(s)；exit=0
```

## 故障注入验证（真实执行）

向 result.json 注入三类典型错误后重跑 lint：

```text
ERROR: E2 Q2/Q2-C9: 论断数值 2.2 未出现在该论断引文中
WARN:  W1 Q2/Q2-C9: 措辞像推断但标了 reported，确认 kind
lint done: 1 error(s), 1 warn(s)；exit=1
```

即："自己算出的差值以 reported 措辞写出"会被 E2 + W1 同时点名，
这正是本 Skill 针对的表达类失分。

## 最终产物

`result.synthetic.json`：本次合成示例的真实输出（lint 0 error / 0 warn）。要点：

- Q2-C2 为作者解释（"suggesting …"），按语法在 text 中带"作者认为"字样、
  kind 仍为 reported；
- Q2-C4 是"有依据地说明未报告"：引文为原文明确否定句
  "scalability to graphs larger than PubMed was not evaluated"。
