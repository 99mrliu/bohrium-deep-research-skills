# 引文契约（citation contract）

本契约定义"带来源引用的问答"中引文的合法形态与核验标准。
**核验脚本（qa_verify.py）是唯一裁判**：它说不过，就是不过。

## 引文格式

论断文本中，引用写在论断之后、句读之前：

```
…500 小时后效率保持率为 91.2%。[F02|9f4c11ab|L4-L4]"500 小时后效率保持率 91.2%。"
```

- `F02`：索引 `kb_index.json` 中的 file_id（对应一条真实文件记录）。
- `9f4c11ab`：该文件 SHA-256 前 8 位，即**版本坐标**；文件内容一旦变化，
  该引文自动失效（version_mismatch）。
- `L4-L4`：行号区间（行号化抽取文本的行号）；偏差 >3 行只警告不判失败，
  但必须修正后再交付。
- 引文必须是从该文件**逐字截取**的连续片段（脚本按"去除全部空白后子串
  比对"核验，兼容跨行与 CJK）；禁止转述、拼接、改字、补标点。

## citations.jsonl（核验输入，每行一条）

```json
{"citation_id": "c1", "claim_id": "q1-c1", "file_id": "F02", "sha8": "9f4c11ab",
 "line_start": 4, "line_end": 4, "quote": "500 小时后效率保持率 91.2%。"}
```

## answers.json（模型撰写，finalize 的输入）

```json
{"answers": [
  {"question_id": "q1",
   "answer": "500 小时后效率保持率为 91.2%。",
   "claims": [{"claim_id": "q1-c1",
               "claim": "500 小时后效率保持率为 91.2%",
               "evidence": [{"citation_id": "c1", "file_id": "F02",
                             "sha8": "9f4c11ab", "line_start": 4, "line_end": 4,
                             "quote": "500 小时后效率保持率 91.2%。"}],
               "paraphrase": false}]}
]}
```

## 转述与推测

无法用逐字引文支撑的句子：要么删除，要么 `paraphrase: true` 并给
confidence（high/medium/low），且在 answer 中用"据库内材料概述"类措辞
明示；禁止把转述伪装成引文（引文核验不过时 finalize 会强制降级）。

## 核验失败的处置（硬性）

- `quote_not_found` 且有 best_match（相似度≥0.85）：按 best_match 的真实
  坐标与原文改写引文，重新核验。
- `quote_not_found` 无 best_match：论断降级 unsupported 或删除。
- `version_mismatch`：重新读取该文件当前内容，按新哈希重取引文。
- `file_unreadable` / `file_id_not_in_index`：该证据作废，换源或标
  "库中无依据"。
- 最终 result.json 不允许残留任何 pass=false 的引文（finalize 强制清空）。
