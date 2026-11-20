# 标注表填写说明（S1 / S2 通用）

## 独立性纪律

- S1 按 `sheet_s1.jsonl`（题录正序）填写；S2 按 `sheet_s2.jsonl`（题录逆序）填写。
- **S2 不得参照 S1 的任何结论、理由或证据**；两份表由两次独立请求分别完成，
  每次只能依据 `records_dedup.jsonl` 中的标题/摘要重新推导。
- dual_fixture 模式下两套标注来自案例自带 fixture（输入材料，非金标准），
  本表纪律由 fixture 的外部独立性替代，模型不得改动其判定。

## 行格式（JSONL，每行一条）

```json
{"record_id": "R0001", "decision": "include", "reason_code": "INC-DES", "evidence_quote": "240 adults with type 2 diabetes were randomized to CGM or SMBG", "note": ""}
```

| 字段 | 要求 |
|---|---|
| record_id | 照抄空白表，不得增删记录 |
| decision | `include` / `exclude` / `uncertain` |
| reason_code | 见 rules/reason_codes.md，非空 |
| evidence_quote | **从该记录标题或摘要中逐字摘录**的片段（脚本归一 NFKC+小写+压缩空白后做子串校验）；不要改写、不要翻译、不要拼接多处文字 |
| note | decision=uncertain 且免引用时必填（说明缺什么信息）；其余情况可空 |

## 常见失败与修复

- 「未锚定」：quote 含改写/翻译/拼接 → 回到 records_dedup.jsonl 复制原文连续片段。
- 「note 必填」：uncertain 免引用时必须写明缺失信息（如「摘要为空，无法核实结局指标」）。
- 填好后另存为 `/app/work/annotations_s1.jsonl` 与 `/app/work/annotations_s2.jsonl`，
  各跑 `validate_annotations.py --sheet <表>`，exit 0 再进入 agreement。
