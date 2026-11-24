# 合成最小示例（replay-custody）

**本目录是合成示例，用于说明接口与流程，不是正式案例结果。**

`library/` 内含 2 个合成文件：`exp_record_B2023-014.md`（含缓冲液配方原文）
与 `notes.txt`。`case.json` 两个提问：一个能取到原文句子（核验门应放行），
一个库中无相关内容（应为 not_found）。

`run_example.py` 在正式流程中**故意注入一张改写引文的证据卡**（把原文
"50 mM Tris-HCl pH 8.0" 改写为 "0.05 M Tris 缓冲液"），用于演示核验门
会拦截非逐字引文。

## 运行

```bash
cd examples
python3 run_example.py
```

在本目录生成 `work/`（journal.jsonl、sources_manifest.json、
evidence_cards.json、verified_answers.json、contract_report.json）与
`output/`（result.json、REPLAY.md 等）。

## 预期结果（合成示例的期望行为）

- `verified_answers.json`：q1 的证据卡 verified；注入的伪卡 rejected，
  原因含 `quote_not_verbatim`；q2 为 not_found。
- `result.json`：answers 中无被拦截论断；uncertainty 记录拦截事件；
  含 case_id 与 output_contract 全部字段；契约检查 ok=true。
- `REPLAY.md` 生成且保管链 seal 校验通过（chain_ok=true）。
