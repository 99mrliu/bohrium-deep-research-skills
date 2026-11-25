# extractions.jsonl — the ONE model-written artifact (schema reference)

> 本文件定义模型唯一需要写出的文件：`/app/work/extractions.jsonl`。
> 追加写、逐行一个 JSON 对象；解析器宽容（坏行跳过并告警，不中断流水线）。

## 总则

- **一行一个 JSON 对象**，必须含 `"op"` 字段；已知 op：
  `node` / `edge` / `merge` / `nonmerge` / `unreported` / `note`。
- 除 `note` 外，每条 op 都必须携带三元组证据：
  `source_id`（语料来源 id，如 `P1`/`S1`）、`paragraph_id`（JATS 段落 id）、
  `quote`（**必须是该段落 text 的逐字符精确子串**，脚本机械校验，造假必被拒）。
- 本任务语料**没有 PDF 页码**：禁止编造页码，地址只能是 `(source_id, paragraph_id)`。
- 内联公式/下标线性化为纯文本（如 `MAPbI3` 写作 `MAPbI3`）。
- 文件可**追加写**：修补充一行新 op 即可（重名 id 以先出现者为准并在报告中告警）；
  也可以整文件重写。

## op: node

```json
{"op":"node","id":"n_cl_x","type":"claim","name":"短名称",
 "source_id":"P1","paragraph_id":"p1","quote":"原文精确子串",
 "qualifiers":{"metric":"PCE","value":"21.1%","condition":"1-sun 初始测量"}}
```

- `id`：稳定字符串 id（建议 `n_<type>_<关键词>[_<来源>]`）。
- `type`：`paper/material/method/task/metric/condition/sample/dataset/claim/researcher/other`；
  未知类型不会拒绝，但会在 verify 报告里标记。
- `qualifiers`：可选，**数值型 claim 必须带** `metric` + `condition`
  （不同条件/数值绝不并入同一结论）。

## op: edge

```json
{"op":"edge","id":"e1","type":"uses|achieves|reports|measures|contradicts|aliases|...",
 "from":"n_a","to":"n_b","source_id":"P1","paragraph_id":"p3","quote":"...","note":"可选"}
```

- `from`/`to` 必须是已声明的 node id（或脚本自动生成的 `paper_<source_id>`）。
- 关系方向必须与原文一致；`note` 可记录条件差异。
- 冲突用 `contradicts`（或 `conflicts-with`）显式连边 —— 脚本保留
  （`resolution=preserved`），绝不自动消解。

## op: merge（跨篇合并，需克制）

```json
{"op":"merge","id":"mg1","keep":"n_规范id","drop":"n_别名id",
 "normalized_key":"material|mapbi3|methylammonium lead iodide",
 "reason":"为什么是同一条实体（一句话，含依据段落）",
 "source_id":"S1","paragraph_id":"s1","quote":"..."}
```

- 必须给 `normalized_key`（规范化键：小写、符号折叠）与显式 `reason`；
  缺任一字段即被拒。
- 合并后 `drop` 节点被 `keep` 吸收，引用它的边自动重定向，账本写入
  `merge_ledger`。
- **不要合并**：不同条件/样本/数值；同名但不同物理对象（典型陷阱：两篇都
  出现 "TiO2" 但指不同层/样品）；同一通用术语 ≠ 同一数据集/模型。

## op: nonmerge（同名不同物，显式登记）

```json
{"op":"nonmerge","id":"nm1","name":"TiO2","subjects":["n_a","n_b"],
 "reason":"同名但不同物理对象：……","source_id":"S1","paragraph_id":"s3","quote":"..."}
```

- `subjects` 至少 2 个；写入 `nonmerge_registry`，防止后续被误合并。

## op: unreported（未报告项）

```json
{"op":"unreported","id":"u1","item":"hysteresis index",
 "reason":"原文明确说未量化，无法抽取数值",
 "source_id":"P1","paragraph_id":"p6","quote":"..."}
```

## op: note（给审稿人的备注，可选）

```json
{"op":"note","id":"note1","text":"任意说明（归属、缩写定义、冲突解释等）"}
```

## 坏行处理（apply 阶段）

- JSON 解析失败、非对象、`op` 未知 → 跳过并在 `run_report.json
  .line_acceptance.skipped_detail` 中逐行记录（含行号、原因、原文截断）。
- 校验失败（引文非子串、地址不存在、merge 缺键等）→ 进入 quarantine，
  见 `verify_report.json`。
