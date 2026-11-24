# 故障取证报告（紧凑版）

- 文件: `/tmp/bfa/repair/recovered.csv`
- 字节: 236 | sha256: `d02ec95009604964…`
- 解码: utf-8 (score 1.000) | 行尾: {'CRLF': 0, 'LF': 10, 'CR': 0} | 分隔符: , (5 列, 一致性 1.000)

## 故障清单（3 项）

1. **fullwidth_chars** [medium, score=0.90] {"cells": 1}
2. **sentinel_tokens** [info, score=0.99] {"-999": 1, "ND": 1}
3. **scientific_notation_text** [low, score=0.90] {"cells": 1}

## 建议修复（草案，均未批准）

- R01 `{"op": "fullwidth_to_ascii"}` score=0.90

下一步：对照数据字典与工单审批 suggested_repair_map.json → repair_apply.py → roundtrip_check.py
