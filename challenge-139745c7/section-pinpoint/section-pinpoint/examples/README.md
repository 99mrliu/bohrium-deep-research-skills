# 合成最小示例（section-pinpoint）

**本目录是合成示例，用于说明接口与流程，不是正式案例结果。**

`library/` 内含 3 个合成文件：

- `开题报告_v1_2023-03-01.md`：含 `1. 研究背景`、`2. 实验方案`（含 2.1 缓冲液）等编号章节。
- `开题报告_终稿_2023-06-15.md`：同主题终稿，缓冲液配方在 `2.1` 节且有修订数值。
- `HPLC数据_2023-07.csv`：表格文件，无章节结构，验证非标题文件也能切段锚点。

`case.json` 两个提问：一个命中终稿 `2.1` 节，一个（"量子点合成"）全库无命中，
用于演示 `no_match` 的诚实报告。

## 运行

```bash
cd examples
python3 run_example.py
```

在本目录生成 `work/anchors.jsonl`、`work/hits.json`、`output/result.json`。

## 预期结果（合成示例的期望行为）

- 提问 1 状态 `located`，首命中 locator 含 `开题报告_终稿_2023-06-15.md › §2.1`，
  `anchor_sentence` 为"缓冲液配方（修订）：25 mM HEPES pH 7.4"开头，
  带 char_start/char_end。
- 提问 2 状态 `no_match`，note 中列出检索词项与锚点总数，不返回整篇文件。
- `result.json` 含 case_id 与 output_contract 全部字段。
