# 候选图谱撰写规范（Agent 必读）

`graph.candidate.json` 是 Agent 依据两篇原文撰写的**语义产物**；脚本只做确定性校验、导出与查询，不会替你生成或修补内容。写完后用 `kg_validate.py` 验证，全部通过才能进入导出与查询。

## 顶层结构

```json
{
  "schema_version": "1.0",
  "graph_id": " kebab-case 标识 ",
  "case_id": "与 case.json 一致",
  "sources": [ ... ],
  "nodes": [ ... ],
  "edges": [ ... ],
  "merge_decisions": [ ... ]
}
```

## sources（来源声明）

每篇论文一条，`source_id` 自取（建议 `S1`=primary、`S2`=secondary）：

```json
{"source_id": "S1", "doi": "…", "title": "…", "authors": ["…"],
 "role": "primary", "file": "primary-material.json"}
```

- 根的 DOI/title/authors 只属于第一篇（primary），第二篇的元数据以 `corpus-manifest.json` / `secondary-material.json` 为准，**不得张冠李戴**。
- `file` 用于证据归属核验：声明后，该来源的证据段落必须真的出自该文件，否则校验拒绝。

## nodes（实体）

```json
{"id": "n:tio2", "type": "Material", "name": "二氧化钛",
 "aliases": ["TiO2"],
 "evidence": [{"source_id": "S1", "paragraph_id": "p-a-1", "quote": "二氧化钛电子传输层"}]}
```

- 建议类型：`Researcher / Material / Method / Task / Metric / Sample / Condition / Conclusion`（可用其他类型，导出按类型分列）。
- 实体必须是**论文里真实出现的科研对象**，不要凭常识补全。
- 每个节点 ≥1 条证据；每条证据 = `source_id + paragraph_id + quote`：
  - `paragraph_id` 是组织方 JATS 段落 ID（如材料里的 `paragraph_id` 字段），**不是 PDF 页码**；
  - `quote` 是该段落原文的**精确子串**（≤200 字符，校验器逐字比对，标点都不能改）；
  - 禁止出现 `page`/`页码` 等字段。
- 区分**作者自述**与**他人转述**：综述式转述不要当成原始证据；必要时在 `note` 字段说明。

## edges（关系）

```json
{"id": "e4", "src": "n:sample-a", "dst": "n:pce", "relation": "测得",
 "conditions": "仅样品A、有效面积0.1平方厘米；数值不可移植",
 "evidence": [{"source_id": "S1", "paragraph_id": "p-a-2", "quote": "获得了18.5%的光电转换效率"}]}
```

- 只建立**有证据支持**的关系；共现、推测、综述转述不算直接证据。
- `relation` 自取中文关系名（如 制备/使用/测得/优于/支持/矛盾/促进/条件约束），查询按**精确匹配**过滤，命名要稳定。
- 方向即 `src → dst`；`conditions` 写明适用条件（样品、条件、指标维度），带数值的边必须限定数值归属，**禁止把两篇的条件、样本和数值合成一个结论**。

## merge_decisions（合并 / 不合并决策）

跨篇实体对齐必须显式记录，两种都要：

```json
{"id": "m1", "decision": "merge",
 "left": "S1「二氧化钛电子传输层」(p-a-1)", "right": "S2「二氧化钛薄膜」(p-b-1)",
 "canonical_node": "n:tio2",
 "rationale": "同一化学材料，仅形态描述不同；合并并各自保留来源证据。",
 "evidence": [ ... ]}
```

```json
{"id": "m3", "decision": "no_merge",
 "left": "n:sample-a（S1）", "right": "n:sample-b（S2）",
 "canonical_node": null,
 "rationale": "不同物理样品：面积/方法/数值均不同；绝不合并。",
 "evidence": [ ... ]}
```

判据：
- **merge**：同一对象（化学指称一致、角色一致），仅名称/大小写/全称简称/形态描述不同。
- **no_merge**：相同通用术语但不同物理样品、模型实例、数据集或实验条件；同名不同对象；不同指标或数值结果。不能强迫每个别名都合并。

## 校验

```bash
python3 scripts/kg_validate.py --graph graph.candidate.json \
    --materials primary-material.json secondary-material.json \
    --report validation_report.json
```

退出码 0 才通过；任何问题都会逐条指出（哪个节点/边、哪条证据、quote 与段落原文的差异、来源文件归属错误）。
