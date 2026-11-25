# Task (SYNTHETIC minimal example)

从给定的词级提取结果（`inputs/words.tsv`，代替真实案例中的案例 PDF）中：

1. 检测所有数学候选行（显示公式及其编号），输出 `math_lines.jsonl`；
2. 将上下标还原为 `^` / `_` 标记，把希腊字母与特殊符号按
   `references/symbol-map.tsv` 映射为 LaTeX 线性形式，输出
   `math_linearized.jsonl` 与符号清单审计 `symbol_inventory.json`；
3. 建立公式索引 `equations_index.json`，编号缺口/重复只做标记不做猜测性修复；
4. 生成符合 `inputs/case.json` 中 `output_contract` 的 `result.json`。

约束：任何无法识别的字符必须进入 `unknown` 列表，禁止猜测、禁止静默丢弃；
`result.json` 必须携带原 `case_id` 与全部 `output_contract` 字段，并给出诚实的
`status`。
