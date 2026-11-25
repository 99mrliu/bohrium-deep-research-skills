# 输出格式约定（output schemas）

## candidates.jsonl（confusion_scan.py）

每行一个 JSON 对象：

```json
{"id": "c0007", "page": 1, "line": 3, "col": 53, "span": "phot0n",
 "suggestion": "photon", "rule": "dig0_o", "kind": "char_in_word",
 "confidence": "high", "context": "in_word", "reason": "..."}
```

- `id`：稳定序号（扫描顺序，页→行→列）。
- `page` 从 1 起（按 form feed 分页）；`line` 为全局行号（空行也计数）；
  `col` 为行内字符偏移（0 起），满足 `line[col:col+len(span)] == span`。
- `confidence` ∈ {high, medium, low}；`kind` ∈ {char_in_word, seq_in_word,
  ligature_insert, space_merge, greek_latin, unreadable,
  standalone_confusable}；`rule` 对应 ocr-confusions.tsv 的 `id`。

## change_log.jsonl（postcorrect.py）

每行一个**已应用**编辑：

```json
{"id": "c0007", "page": 1, "line": 3, "col": 53, "before": "phot0n",
 "after": "photon", "rule": "dig0_o", "kind": "char_in_word",
 "confidence": "high"}
```

unreadable 类编辑的 `after` 恒为 `"[unreadable]"`，原串在 `before` 中。

## review_list.json（postcorrect.py）

JSON 数组，每个未应用候选：

```json
{"id": "c0002", "page": 1, "line": 1, "col": 32, "span": "rnetal",
 "suggestion": "metal", "rule": "seq_rn_m", "confidence": "medium",
 "decision": "defer", "reason": "medium confidence requires --aggressive ..."}
```

`decision` ∈ {defer（策略性暂缓，原文未动）, reject（门控拒绝，如
plausibility gate、span mismatch、overlap）}。

## qc_report.json（ocr_qc.py）

```json
{"status": "ok",
 "before": {"tokens": 150, "suspicious": 16, "rate": 0.1067},
 "after":  {"tokens": 149, "suspicious": 3,  "rate": 0.0201},
 "delta":  {"suspicious": 13, "rate_reduction": 0.0865},
 "applied_changes": 13, "applied_by_rule": {"dig1_l": 6, ...},
 "remaining_candidates": [{"id": "...", "span": "...", ...}],
 "per_line_heat": {"before": [{"page": 1, "line": 1, "tokens": 11,
                               "suspicious": 2}, ...],
                   "after": [...]}}
```

## result.json（ocr_qc.py）

```json
{"case_id": "<原样回显>", "status": "ok|partial|failed",
 "outputs": {"<contract_field>": {"path": "...", "status": "produced"}
                          或 {"path": "", "status": "empty",
                              "explanation": "..."}},
 "sources": {"tools": {"tesseract": "...", "platform_ocr_tool": "..."},
             "references": {"lexicon": "..."},
             "input_raw_ocr": "..."},
 "metrics": {"suspicious_rate_before": ..., "suspicious_rate_after": ...},
 "change_record": {"applied": 13, "marked_unreadable": 1,
                   "deferred_or_rejected": 3, "by_rule": {...},
                   "change_log": "change_log.jsonl"},
 "uncertainty": [{"span": "...", "suggestion": "...", "confidence": "...",
                  "reason": "..."}, ...],
 "warnings": [...]}
```

诚实性约定：`case_id` 缺失时报 `unknown-case` 并写 warning；合同字段无
产出时必须 `status: "empty"` + explanation，不得伪造路径；`uncertainty`
必须完整列出全部暂缓/拒绝项。
