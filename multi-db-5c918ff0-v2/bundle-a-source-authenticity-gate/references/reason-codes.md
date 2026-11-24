# Reason Codes（机器可读原因码）

本文件定义 `scripts/source_gate.py` 在 `authenticity_ledger.json`、`gated_records.json`
与 `result.json` 中可能发出的全部原因码。严重级别语义：

- **error**：导致所在工件被 `quarantined`（其记录一律不得进入下游）。
- **warning**：工件降级为 `trusted_with_warnings`（记录仍可进入 `gated_records.json`，但警告随结果声明）。
- **info**：仅记录，不改变判定。

| code | severity | 含义 | 典型处置 |
|---|---|---|---|
| `MATERIAL_MISSING` | error | case.json 引用了某材料文件，但磁盘上不存在 | 隔离该"幽灵工件"，在 uncertainty 中声明缺口 |
| `READ_ERROR` | error | 文件无法读取（权限/IO 错误） | 隔离工件 |
| `ENCODING_NON_UTF8` | error | 文件不是合法 UTF-8（有损解码后出现 U+FFFD） | 隔离工件；编码真实性无法保证 |
| `PARSE_ERROR` | error | 内容既不是可解析 JSON/JSONL，也不像 HTML 片段 | 隔离工件，类型记 `unknown` |
| `UNKNOWN_FORMAT` | error | JSON 可解析但不符合任何已知源信封/记录形态 | 隔离工件；**仍记录在台账中，绝不沉默丢弃** |
| `ENVELOPE_MISSING_KEYS` | error | 已分类类型的必需信封键缺失（如 crossref 缺 `message.items`、europepmc 缺 `resultList.result`、import_state 缺 `records`） | 隔离工件 |
| `ENCODING_BOM` | info | 存在 UTF-8 BOM（解析前已剥离） | 记录即可 |
| `REPLACEMENT_CHAR_PRESENT` | warning | 文本中出现 U+FFFD 替换字符 | 提示上游编码有损 |
| `TRAILING_CONTENT` | warning | JSON 主值之后存在尾随内容 | 提示拼接/截断污染 |
| `ENVELOPE_STATUS_NOT_OK` | warning | crossref `status` 不为 `"ok"` | 响应语义可疑，降级可信 |
| `COUNT_MISMATCH` | warning | 计数不符：`message.total-results` > 实际 items 数，或 `hitCount` ≠ `resultList` 长度 | 提示响应截断/不完整；降级可信 |
| `ITEM_FIELD_MISSING` | warning | 条目级必填字段缺失/为空（crossref: DOI/title/issued；europepmc: id/source/title；publisher: doi 或 title 至少其一） | 该条目被排除于门控记录之外（记 `excluded_items`），工件降级可信 |
| `FIELD_TYPE_MISMATCH` | warning | 字段类型与期望不符（如 DOI 非字符串、边不是 {from,to}） | 视位置降级可信 |
| `HTML_RESIDUE` | warning | 摘要等字段残留 HTML 标签 | 剥离标签仅供检查，**原始值保留** |
| `HTML_FORMAT_LIMITED` | info | publisher 载荷为 HTML 片段 | 仅能门控 DOI 级标识符，结构不可机器核验 |
| `DUPLICATE_IDENTIFIER` | warning | 单一载荷内部出现重复标识符（同一 DOI/id 出现两次） | 降级可信，提示上游去重缺失 |
| `EMPTY_PAYLOAD` | warning | 载荷为空（items/records/结果列表长度为 0） | 降级可信；若非空约束为硬性则升级为 error |
| `DANGLING_EDGE` | warning | 引用图边端点无法解析到任何材料中的标识符 | 报告，不致命（non-fatal） |
| `IMPORT_NOT_VERIFIABLE` | warning | 导入状态声称来自 db X，但案例中不存在 X 的源响应工件 | 记 `not_verifiable`，声明缺口（declared gap） |
| `IMPORT_INCONSISTENT` | warning | 导入状态声称的标识符在对应源响应中不存在 | 该导入条目被隔离（记 `quarantined`），在 uncertainty 中声明 |
| `ARTIFACT_QUARANTINED` | error | 记录因所在工件被隔离而被排除（仅出现于 `excluded_items`） | 阻断进入下游 |
| `TASK_FILE_MISSING` | warning | task.md 缺失/不可读 | 门控仅凭 case.json 继续，状态降为 partial |

## 判定规则（确定性的）

对每件工件收集其全部检查码集合 `C`：

```
若 C 中存在 severity=error 的码  → verdict = quarantined
否则若 C 中存在 severity=warning 的码 → verdict = trusted_with_warnings
否则                              → verdict = trusted
```

`reference_graph` 与 `import_state` 自身不产出文献记录，但其 error 级问题同样触发隔离，
其 warning 级问题（`DANGLING_EDGE`、`IMPORT_*`）如实进入报告与 uncertainty。
