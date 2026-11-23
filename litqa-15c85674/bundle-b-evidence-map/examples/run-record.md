# 最小调用示例运行记录（合成示例，非正式案例结果）

> 输入 `synthetic-case.json` 为虚构论文（SYN-2026-Lattice-12，Ti-6Al-4V 点阵结构，
> 7 个段落、2 个复合中文问题）。以下命令均在本地真实执行。

## 命令序列

```bash
mkdir -p work/input work/app/work work/app/output
cp examples/synthetic-case.json work/input/case.json

# 1) 索引 + 数值总表
python3 scripts/evidence_map.py index --case work/input/case.json --work work/app/work
# stdout: index ok: 7 paragraphs, 22 numeric mentions

# 2) 子问分解 + 候选排序（关键词由模型从中文子问译出）
python3 scripts/evidence_map.py subqs --index work/app/work/index.json --work work/app/work \
  --terms "Q1S1:yield strength,modulus;Q1S2:compression,room temperature,crosshead;\
Q1S3:dense reference;Q2S1:hot isostatic pressing;Q2S2:fatigue life;Q2S3:nodal stress"
# 节选：
#   子问1（terms: yield strength, modulus）→ P5(6.34) P3(4.40) P6(2.41) P7(2.26)
#   子问2（terms: compression, room temperature, crosshead）→ P2(13.55)
#   Q2S1（hot isostatic pressing）→ P7(9.84)；Q2S2（fatigue life）→ P6(7.00)

# 3) 冲突扫描（每条含数值的论断前各跑一次）
python3 scripts/evidence_map.py conflicts --index work/app/work/index.json --key "yield strength"
# stdout 节选：13 条邻近提及；MULTIVALUE MPa:['100','245','268','960'] …逐段保留对象与条件；exit=0
python3 scripts/evidence_map.py conflicts --index work/app/work/index.json --key "fatigue life"
# stdout: NONE: 无提及…；exit=4 → 据此在 P6 通读确认后写"疲劳寿命未被测量"

# 4) 依据 evidence_map.md 与 numbers.md 成文作答（模型步骤），写 result.json / answers.json
# 5) 引文逐字自检（内嵌脚本，真实执行）：quote self-check: 0 bad quote(s)
```

## 最终产物

`result.synthetic.json`：本次合成示例的真实输出。要点：

- Q1 的"点阵约为致密样的 25.5%"为两值相除，按纪律标 `kind=inferred`；
- Q2 的疲劳寿命依据 `conflicts` 的 NONE 结果 + P6 原文确认，写为
  "有依据地说明未报告"（`kind=reported`，证据为 P6 的明确否定句）；
- `coverage` 列出实际读取的全部 7 段。
