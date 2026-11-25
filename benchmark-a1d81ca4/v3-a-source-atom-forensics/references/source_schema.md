# 实际数据结构与验证边界

本文件定义脚本实际接受的格式。所有示例标识均为描述性格位，不是正式 case 或预制答案。

## 1. source-map/v1

`source_map.py` 的输出为对象：

| 字段 | 类型 | 含义 |
|---|---|---|
| `schema_version` | string | 固定 `source-map/v1` |
| `sources` | list[object] | 每个实际文件一条；显示路径、运行时 `file_path`、格式、原始字节数、完整 SHA256、节点数 |
| `nodes` | list[object] | 可引用的非空文本节点；不生成任何源文本之外的科学内容 |
| `warnings` | list | 非致命索引说明；缺文件、空文件、坏格式不是 warning，而是退出 2 |

每个 node 至少含：

```json
{
  "node_id": "node_<stable-hex>",
  "source_id": "src_<stable-hex>",
  "source_file": "relative-or-base-name.ext",
  "file_path": "runtime path used for byte re-check",
  "source_sha256": "<64 lowercase hex of source bytes>",
  "path": "$.documents[0].paragraphs[0]",
  "locator": {"kind": "paragraph", "index": 1},
  "kind": "paragraph",
  "page": 3,
  "text": "exact decoded source text for this node",
  "text_sha256": "<sha256 of UTF-8 node text>",
  "normalized_text": "NFKC and whitespace-collapsed matching view"
}
```

- `page` 可缺失或为 `null`；仅从 JSON 对象实际 `page` 字段继承，不能由页眉、标题或节点顺序猜测。JSONL/MD/TXT 默认无 page。
- `path` 是递归 JSONPath 风格定位；JSONL 含真实行号，MD/TXT 含真实行范围。`locator.kind` 为 `paragraph` 或 `row`，`index` 是同一字符串/文本内布局节点序号，不是全表人工行号。`section` 存在时记录真实 Markdown 标题链。
- 对 JSON dict/list 递归索引所有字符串；数值/布尔值不会转写成字符串，空字符串不形成证据节点。单个字符串中的空行划分段落、管道表格行单独切分；原始节点文本不做同义改写。
- `node_id` 由显示源路径、源字节 SHA256、JSON path、定位器及精确节点文本共同哈希。相同文件和字节在相同相对显示路径下重建稳定；重命名文件、改变路径/段落顺序或字节会明确形成新身份。
- `normalized_text` 仅供匹配，`text` 与源字节哈希用于取证。匹配算法为 `NFKC` 后将连续 Unicode 空白折叠成一个 ASCII 空格，再检查子串。

## 2. Bank 项

草稿顶层必须有 `Bank`，固定恰好 4 个对象；没有参数把正式 gate 改成任意题数。每项：

```json
{
  "id": "unique-item-id",
  "task": "what the taker must do",
  "scope/input_material": {
    "source_files": ["materials.json"],
    "included": ["declared paths or other real source scope"],
    "exclusions": []
  },
  "reference_answer": {
    "elements": [
      {"id": "element-a", "text": "minimum independently checkable answer element"}
    ]
  },
  "rubric": {"0": "criterion", "1": "criterion", "2": "criterion"},
  "difficulty": "text or non-boolean scalar",
  "data_license": "actual source/license statement",
  "evidence": {"atoms": []}
}
```

`scope/input_material` 也可为非空字符串或数组；不得为 null、空字符串、空 list/dict。`reference_answer` 另外接受一个字符串（隐式元素 id `answer`）、字符串/id-text 对象列表；复杂对象必须使用上述 `elements`。推荐使用显式对象，避免用一整段混合结论逃避覆盖检查。`rubric` 必须含非空字符串键 `"0"`、`"1"`、`"2"`，不是已得分数。

## 3. Atom 与原子证据映射

`evidence.atoms` 必须非空，每个 atom：

```json
{
  "id": "globally-unique-atom-id",
  "text": "one atomic answer assertion",
  "type": "claim | numeric | absence | identifier | other-agent-declared-type",
  "answer_element_ids": ["element-a"],
  "reason": "agent: why this atom represents the indicated answer element and its scope",
  "evidence": {
    "node_id": "one node already in source map",
    "quote": "contiguous exact text except NFKC/whitespace",
    "reason": "agent: why this exact quote supports subject, relation, unit, polarity and qualifiers"
  }
}
```

每个 atom 只有一个 evidence 对象；多源/多节点时使用多个 atom 映射同一答案元素。 gate 检查：

1. 四项目、必填字段、rubric、全局唯一 atom id、有效答案元素 id。
2. 每个答案元素至少被一个 atom 的 `answer_element_ids` 覆盖；映射未知元素或未知节点标为 `orphan`。
3. 每个 item 至少一个 atom；零原子、未覆盖、quote 空白、未知 node 均失败。
4. 规范化 quote 是**其声明 node** 的规范化 `text` 的连续子串；不能跨段落/行/节点拼接。
5. atom 文本只要出现数字记号，默认每个记号都必须在 quote 中以同一规范化形式出现；`type=numeric` 却无数字也失败。`--allow-unsupported-numeric` 只把此一条降为显式 warning，不补单位换算，也不改变其他失败。
6. 两个 reason 均须非空。脚本检查存在性，不理解自然语言原因是否为真。

`evidence-verdict/v1` 含 `ok/errors/items/summary/sources_rechecked`，以及当前 `draft_sha256`、`source_map_sha256`。`summary` 明确列 `failed_items/zero_atom_items/orphan_atom_ids`。退出码：0=结构与词法门禁通过，1=草稿/证据验证失败，2=map、源文件或输入无法可靠读取。`policy.semantic_status` 永远是需 agent 裁决、未独立验证。

## 4. result 合同与导出

`finalize.py` 读取原 case 原样，支持以下四种 `output_contract` 外形（`fields` 为直接映射也接受）：

```json
["Bank", "sources", "uncertainty", "change_records"]
```

```json
{"fields": ["Bank", "sources"]}
```

```json
{"fields": [{"name": "Bank", "type": "array", "minItems": 4, "maxItems": 4}]}
```

```json
{"Bank": "array", "sources": {"type": "array"}, "uncertainty": {"type": "array"}}
```

字段名并集必须全部出现在草稿顶层，`case_id` 取原 case；额外提交字段也原样保留。已知 string/array/object/boolean/integer/number/any 类型、enum、minItems/maxItems 会检查；未知类型不会被偷偷忽略，而是阻止 complete。空 `sources` 占位可由 map 的真实公开摘要替换，非空提交 `sources` 不覆盖。所有草稿内容（包括 uncertainty/change_records）保留，finalizer 只追加必要状态和变更记录。

默认要求：`Bank` 恰好四项、当前 map 和 draft 与 verdict 哈希一致、gate 全四项通过、无字段/类型错误。否则 exit 1 且不写新的 success。显式 `--allow-partial --limits <具体限制>` 才把已知失败导出为 `status=partial/success=false`；case、draft、case_id 或合同形状本身不可读时仍 exit 2，不能靠 partial 修复坏输入。

**限制：** 节点索引不辨别标题、上下文或表格跨列语义；精确子串不证明引用蕴含原子；数字字面一致不证明单位/方向正确；agent 自己声明元素和映射也不是第三方覆盖审计。需要独立人工语义复核时必须在 uncertainty 明示，不能声称 gate 已代替复核。
