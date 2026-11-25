---
name: formula-symbol-fidelity
description: >-
  从科研 PDF 的词级提取结果中保真还原数学公式与特殊符号：基于几何特征（符号密度、短行居中、
  行尾编号如 (1)/(2.3)）检测数学行，利用 y 偏移把上下标还原为显式 ^/_ 标记，用数据驱动映射表
  （references/symbol-map.tsv）翻译希腊字母与特殊符号，将公式编号与来源位置（页码/bbox）对齐建索引，
  并做符号清单审计（原始提取与归一化输出的符号计数必须对账，未识别字符一律列入 unknown，绝不静默
  丢弃或猜测）。触发条件：任务含公式、希腊字母、上下标、特殊符号且要求符号级保真。超出范围：
  数学语义理解（不做化简/求值/定理推断）、整页阅读顺序还原、表格结构重建、图像型公式的 OCR 识别
  （只标记不猜测）。
---

# formula-symbol-fidelity — 公式与特殊符号保真提取

## 总览

```
词级 TSV (pdftotext -tsv / pymupdf words)
        │
        ▼
scripts/math_detect.py ─────────────► math_lines.jsonl
  几何+符号密度检测数学行               page/bbox/raw_text/eq_number/
  (密度/居中/编号 (n),(n.m))           confidence/reasons
        │
        ▼
scripts/symbol_fidelity.py ─────────► math_linearized.jsonl
  y 偏移>0.25×字号 ⇒ ^/_ 上下标         symbol_inventory.json
  symbol-map.tsv 映射希腊/特殊符号      (raw vs 输出计数对账 + unknown 列表)
        │
        ▼
scripts/eq_index.py ────────────────► equations_index.json
  编号→页码/bbox/文本 索引              result.json (契约感知, 诚实 status)
  缺口/重复只标记不修复
```

核心原则：**宁可标记 unknown，绝不猜测**。任何无法映射的字符保留原样写入输出，
同时连同页码/行号/码位列入 `unknown` 清单；编号异常（缺口、重复）只标记为
inconsistency，不做任何修复性猜测。

## 运行契约

- **输入**：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md`，
  以及案例 PDF。先用 `ls -R /input` 盘点实际文件，不要假设文件名。
- **词级提取**：优先 `pdftotext -tsv in.pdf out.tsv`（若可用）；其次 pymupdf
  `page.get_text("words")`（若已安装）；两者都不可用时退回纯 stdlib 路径
  （脚本本身只依赖 Python 3 标准库，TSV 为其输入）。
- **工作目录**：`/app/work`（中间产物）；**交付物**：`/app/output`。
- **result.json 契约**：必须携带原 `case_id`，必须包含 `output_contract` 声明的
  每一个字段；某字段无法产出时置空并附 `explanation`，禁止编造；`status` 必须诚实
  （`success` / `partial` / `failed`），存在 unknown 符号或编号异常时至少为 `partial`。
- **预算纪律**：64 次请求 / 900 秒。脚本优先——检测、映射、对账全部由确定性脚本完成；
  模型只用于判断性环节（如确认某行是否确为公式、评估 unknown 字符的上下文），不为
  每个符号调用模型。

## 操作步骤

1. `ls -R /input` 盘点输入；读取 `case.json` 记下 `case_id` 与 `output_contract` 字段。
2. 生成词级 TSV：`pdftotext -tsv case.pdf /app/work/words.tsv`，或按简单 7 列格式
   （`page x0 y0 x1 y1 size text`）准备。
3. 检测数学行：
   `python3 scripts/math_detect.py --input /app/work/words.tsv --out /app/work/math_lines.jsonl`
   （退出码 0 正常 / 2 输入错误 / 3 输入为空）。
4. 线性化 + 符号审计：
   `python3 scripts/symbol_fidelity.py --math-lines /app/work/math_lines.jsonl --input /app/work/words.tsv --out-dir /app/work`
5. 建索引 + 契约化结果：
   `python3 scripts/eq_index.py --linearized /app/work/math_linearized.jsonl --inventory /app/work/symbol_inventory.json --case /input/case.json --out-dir /app/output`
6. 人工/模型复核：`symbol_inventory.json` 的 `unknown` 与 `equations_index.json` 的
   `numbering.anomalies` 必须逐条进入 `result.json` 的 `uncertainty`。

## 输出物说明

| 文件 | 内容 |
|---|---|
| `math_lines.jsonl` | 每条数学候选行：page、bbox、raw_text、eq_number、confidence、reasons |
| `math_linearized.jsonl` | 上行 + `linearized`（显式 `^{}`/`_{}` 标记、LaTeX 符号）、`script_notes` |
| `symbol_inventory.json` | 每个已映射符号的 raw_count vs output_count 对账；`unknown` 列表（字符、码位、页/行）；`status` |
| `equations_index.json` | eq_number → 页码/bbox/线性文本/verification；编号缺口与重复列表 |
| `result.json` | case_id、status、output_contract 全字段回声、sources、uncertainty、change_record |

## 方法要点

- **几何优于猜测**：显示公式的"短行 + 居中 + 行尾编号"是版面事实；上下标的
  基线偏移是测量值（阈值 0.25×字号），不是语言模型的推测。详见
  `references/method.md`。
- **数据驱动映射**：希腊字母（α..ω 及大写）与 ∂∇∈∀⇒±×÷≈≠≤≥∑∏∫√∞ 等符号的
  翻译全部来自 `references/symbol-map.tsv`，改表即改行为，代码不含硬编码个案。
- **对账式审计**：每个被映射符号在原始文本中的出现次数必须等于其 LaTeX 形式在
  线性化输出中的出现次数；不等即 `issues`。非 ASCII 且不在表中的字符 ⇒ `unknown`。
- **编号对齐**：`(n)` / `(n.m)` 捕获后从正文剥离单独存 `eq_number`，与页码/bbox
  一起入索引；序列缺口与重复编号只标记。

## 异常与限制

| 情况 | 行为 |
|---|---|
| 自定义编码的符号字体（PUA 码位） | 无法映射 ⇒ 列入 `unknown`（含码位/页/行），保留原字符，**不猜测** |
| 公式被渲染为图片 | 词级 TSV 中无对应词 ⇒ 检测不到；应在 uncertainty 中标记"可能存在图像型公式"，不做 OCR 猜测 |
| 堆叠分数、矩阵、多行对齐公式 | 超出线性 `^/_` 表达能力；按行输出并在 uncertainty 中说明，不强行拼接 |
| 旋转/竖排数学 | 几何假设（y 向下、行水平）失效，可能漏检；置信度与 reasons 会反映 |
| 上下标与基线偏移 < 0.25×字号 | 不判为上下标（保守策略），保持基线文本 |
| 行首即为上下标（无基符） | 以 `^{...}_no_base` 形式保留并在 `script_notes` 标记 |
| 符号映射一对多（如 − 映射为 ASCII `-`） | 对账可能受原文已有 ASCII 连字符干扰；以 unknown/审计为准 |

## 最小示例

`examples/minimal/` 是一个**合成**示例（非真实 PDF 提取），包含上标（x² 式的
`c`+凸起 `2`）、下标（`a_i`）、希腊字母（α β Δ σ ∂）、一个不可映射的 PUA 字符
（U+E000，必须进入 unknown）和一处编号异常（(2) 重复，必须被标记）。运行：

```bash
cd examples/minimal
python3 ../../scripts/math_detect.py --input inputs/words.tsv --out outputs/math_lines.jsonl
python3 ../../scripts/symbol_fidelity.py --math-lines outputs/math_lines.jsonl --input inputs/words.tsv --out-dir outputs
python3 ../../scripts/eq_index.py --linearized outputs/math_linearized.jsonl --inventory outputs/symbol_inventory.json --case inputs/case.json --out-dir outputs
```

`outputs/` 中的全部文件均为上述命令的真实运行结果（详见 `examples/minimal/README.md`）；
因存在 1 个 unknown 符号与 1 处编号重复，`result.json` 的 `status` 为 `partial`。
