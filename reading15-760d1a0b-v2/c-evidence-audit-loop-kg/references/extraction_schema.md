# 抽取草案 Schema（extraction.draft.json）

模型在阶段 1 写出的唯一文件。顶层结构：

```json
{
  "stage": "stage1-model-draft",
  "items": [ { ... }, ... ]
}
```

`items` 为一个数组，每个元素是一个带 `id`（全文件唯一、建议 `n-/e-/m-/x-/u-` 前缀）
与 `op` 的条目。所有条目最终会被 `audit.py` 逐条机械审计。

## 1. 条目类型（op）

### node — 实体节点

```json
{"id": "n-claim-pce-pri", "op": "node", "entity_type": "claim",
 "label": "PCE of 21.1% (initial, 1-sun)",
 "attributes": {"metric": "PCE", "value": "21.1%", "condition": "initial, 1-sun AM1.5G"},
 "evidence": {"source_id": "primary", "paragraph_id": "pri-p06",
              "quote": "a PCE of 21.1% at 1-sun illumination"}}
```

- `entity_type` ∈ `paper | researcher | material | method | device | sample | metric | claim | condition | dataset`
- `label`：原文中出现的称谓（保持原文大小写/拼写）。
- `attributes`：可选；**claim 必须给出 `metric`/`value`/`condition`**（数值结论的
  审计与冲突保留依赖这三个字段）。
- `evidence`：单个对象或对象数组；`quote` 必须是
  `source_id`/`paragraph_id` 所指段落 `text` 的**精确子串**（区分大小写与空白）。

### edge — 关系边

```json
{"id": "e-measures-pri", "op": "edge", "relation": "measures",
 "subject": "n-claim-pce-pri", "object": "n-metric-pce",
 "qualifiers": {"note": "optional"},
 "evidence": {"source_id": "primary", "paragraph_id": "pri-p06", "quote": "..."}}
```

- 推荐关系集（有向）：`reports`（paper→claim）、`uses`（device/sample→material|method）、
  `prepared-by`（material/sample→method）、`measures`（claim→metric）、
  `conflicts-with`（claim↔claim，数值冲突成对保留）、`involves`（paper→任意，兜底）。
- `subject`/`object` 必须是本文件内已声明的条目 id。
- 只建立原文直接支持的关系：共现、综述转述、推测 **不算** 直接证据。

### merge — 跨篇合并

```json
{"id": "m-mapbi3-alias", "op": "merge",
 "members": ["n-mapbi3-pri", "n-mapbi3-sec"],
 "normalized_key": "mapbi3",
 "reason": "alias pair; sec-p10 explicitly equates the two names",
 "evidence": [ {"source_id": "primary", ...}, {"source_id": "secondary", ...} ]}
```

- 必须给出 `normalized_key`（大小写折叠、去连字符/空格后的规范键）与 `reason`，
  并附双篇证据。
- 审计器拒绝合并 `metric` 相同而 `value` 不同的 claim（`INVALID_NUMERIC_MERGE`）。

### nonmerge — 显式不合并

同名不同对象（如两篇中不同的 "TiO2" 物理样品）必须显式登记：

```json
{"id": "x-tio2-nonmerge", "op": "nonmerge",
 "members": ["n-tio2-pri", "n-tio2-sec"],
 "reason": "same generic term, different physical layers/samples ...",
 "evidence": [ ... ]}
```

### unreported — 未报告项

```json
{"id": "u-hysteresis", "op": "unreported", "topic": "hysteresis index",
 "scope": "primary paper", "reason": "explicitly not reported",
 "evidence": {"source_id": "primary", "paragraph_id": "pri-p06",
              "quote": "hysteresis index was not reported in this study"}}
```

### note — 自由备注（可选）

`{"id": "t-001", "op": "note", "text": "..."}`，不参与图谱。

## 2. 写作纪律（给模型）

1. 只抽取**真实出现在段落文本中**的对象；禁止常识补全。
2. 每个实质条目至少一条 evidence；quote 直接**复制粘贴**原文片段（≥8 字符），
   不要改写、不要补全标点。
3. 根元数据（case.json 的 doi/title/authors）只属于 primary；为 secondary 建
   paper 节点时用它自己的标题与段落。
4. 数值结论一条 claim 对应一个 (metric, value, condition)；不同条件/不同论文的
   数值**分开成两条 claim**，再用 `conflicts-with` 边相连。
5. 行内公式/上下标线性化为纯文本。
6. 宁缺毋滥：拿不准的关系写进 undetermined（可在 note 里说明），不要猜。

## 3. 修复文件 Schema（repairs.json，阶段 3）

```json
{"repairs": [
  {"id": "n-claim-pce-pri",
   "patch": {"evidence": {"source_id": "primary", "paragraph_id": "pri-p06",
                          "quote": "a PCE of 21.1% at 1-sun illumination"}}},
  {"id": "e-some-edge", "drop": true, "drop_reason": "cannot ground in text"}
]}
```

- 只允许修补 `repair_queue.json` 中出现的 id；补丁按顶层字段**整体替换**
  （修引文/地址时替换整个 `evidence`）。
- 修不了的条目用 `drop: true` 撤回并写明原因；撤回会被记录且不进入图谱。
