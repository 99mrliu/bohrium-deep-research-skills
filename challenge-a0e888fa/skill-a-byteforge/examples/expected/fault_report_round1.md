# 故障取证报告（紧凑版）

- 文件: `/Users/liuhengshen/Desktop/bhr_product/a0e888fa-5dir/bundles/skill-a-byteforge/examples/demo_table.csv`
- 字节: 334 | sha256: `6298f60065557db8…`
- 解码: utf-8 (score 0.909) | 行尾: {'CRLF': 5, 'LF': 5, 'CR': 0} | 分隔符: ; (5 列, 一致性 1.000)

## 故障清单（5 项）

1. **mojibake_double_encoding** [high, score=0.99] {"via": "latin1_utf8", "mojibake_chars_before": 42, "mojibake_chars_after": 0, "before_sample": ["æ ·åç¼å·;ææ ;åå¼;åä½;n", "W-01;æº¶è§£æ°§;8.2;mg/L;3", "W-02;æº¶è§£æ°§;ï¼.ï¼;mg/L;3"], "after_sample": ["样品编…
2. **mixed_eol** [low, score=0.95] {"CRLF": 5, "LF": 5, "CR": 0}
3. **invisible_chars** [medium, score=0.90] {"NBSP@1处": 3}
4. **sentinel_tokens** [info, score=0.99] {"-999": 1, "ND": 1}
5. **scientific_notation_text** [low, score=0.90] {"cells": 1}

## 建议修复（草案，均未批准）

- R01 `{"op": "mojibake_fix", "via": "latin1_utf8"}` score=0.99
- R02 `{"op": "normalize_eol", "to": "\\n"}` score=0.95
- R03 `{"op": "set_delimiter", "delimiter": ";"}` score=0.90
- R04 `{"op": "strip_invisible", "chars": [" "]}` score=0.90

下一步：对照数据字典与工单审批 suggested_repair_map.json → repair_apply.py → roundtrip_check.py
