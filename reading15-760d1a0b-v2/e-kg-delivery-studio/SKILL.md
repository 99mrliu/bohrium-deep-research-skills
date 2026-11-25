---
name: e-kg-delivery-studio
description: 文献知识图谱的下游交付与渲染工程。用纯 Python 标准库把"已验证"的知识图谱变成一整套可人工核查的交付物：确定性分层布局的全图 graph.svg（无 graphviz）、每个查询一张高亮结果子图的 query_<id>.svg、自包含 report.html（内联 SVG + 查询表格 + 逐字引文证据索引）、report.md、nodes.csv/edges.csv、graph.jsonld、graph.graphml、evidence_index.json。抽取侧只需模型写一份紧凑 JSONL，引文由脚本机械校验（精确子串 + 地址存在）。适用于"阅读15｜文献知识图谱构建"等要求图谱可溯源、可渲染、可验证交付的场景。
---

# e-kg-delivery-studio — 知识图谱交付工作室（下游交付与渲染工程）

## 1. 用途与适用条件

本 Skill 的重心是**交付物工程**：把知识图谱变成评审者可以直接打开、逐条核查的一套文件
（SVG/HTML/MD/CSV/JSON-LD/GraphML/证据索引）。抽取与验证被刻意压缩为最小流程——模型只写
**一份**紧凑的 `extractions.jsonl`，其余全部交给确定性脚本。

适用条件：
- 输入符合挑战运行时契约（见 §3）的两篇（或一篇）文献全文 + case.json；
- 需要"查得到回得去"：每个节点/边都要能回到 `source_id + paragraph_id + 逐字引文`；
- 需要可渲染、可审查、可复用的交付物，而不是只有一个 JSON。

不适用：需要交互式图数据库、需要 graphviz 等第三方布局库的场景（本包刻意不用任何第三方库）。

## 2. 模型 vs 脚本的分工

| 方 | 做什么 |
|---|---|
| 模型（agent） | 只写 **一个文件** `/app/work/extractions.jsonl`：每行一个 JSON 操作（`node`/`edge`/`merge`/`nonmerge`/`unreported`/`note`）。格式见 `references/extraction-schema.md`。 |
| 脚本（确定性、纯标准库） | 输入发现、引文机械校验（**精确子串** + 地址存在）、图构建与合并/非合并、数值冲突保留、自动执行 case.json 的 query_specs、渲染全部交付物、镜像 output_contract 组装 result.json。 |

设计要点：模型写的东西少而紧凑（省请求数），机械工作全部脚本化（可复现、可审计）。

## 3. 运行时契约

- 输入在 `/input/`：`case.json`（含 `case_id`、`output_contract`、可选 `query_specs`、只属于
  primary 的根书目元数据）、`task.md`、`material.json`（容忍 list / `{"materials":[...]}` /
  mapping 三种形态）、`primary-material.json`、`secondary-material.json`（可能缺失）、
  `corpus-manifest.json`（用于交叉核对归属）、可选 `secondary-publisher.xml`（**只登记存在，
  绝不解析**）。脚本通过文件名**发现**输入，不硬编码任何内容。
- 工作目录 `/app/work`：`corpus.json` → `verified.json` → `graph.json` → `queries.json`
  依次落盘，可断点续跑（各阶段是独立子命令）。
- 交付目录 `/app/output`：见 §6 清单；`result.json` 动态镜像 `output_contract` 声明的每一个键；
  产不出的键置 `null` 并在 `contract_notes` 记录原因，**绝不静默省略**。

## 4. 证据规则（不可协商）

1. 每个实质性 node/edge 必须携带 ≥1 条证据：`source_id` + `paragraph_id`（组织者的 JATS 段落 ID；
   本包没有 PDF 页码，**绝不编造页码**）+ 一段**逐字引文**，引文必须是该段落文字的精确子串。
2. `verify` 阶段机械校验每一条引文：子串不成立或地址不存在 → 该行被拒绝并记录原因码
   （`QUOTE_NOT_SUBSTRING` / `ADDRESS_NOT_FOUND` / `MALFORMED_JSON` / `DANGLING_ENDPOINT` /
   `DUPLICATE_ID` / `MISSING_FIELD` / `UNKNOWN_OP` / `EMPTY_EVIDENCE`）。渲染阶段
   `evidence_index.json` 会**再校验一次**全部引文。
3. ≥3 个真实执行的查询（优先 case.json 的 `query_specs`），每个查询返回：结果子图（节点+边）、
  支撑证据、明确列出的未确定/未知项（unreported 列表自动附加到每个查询）。
4. 合并纪律：跨篇合并需要归一化键 + 明确理由（`merge` 操作，进 merge ledger）；
   同名不同物必须显式 `nonmerge`（进 non-merge registry）；不同条件/样品/数值**绝不**合并成
   一条结论——数值冲突作为独立 claim 节点保留（`resolution="preserved"`）；同一通用方法/材料
   术语跨篇出现 ≠ 同一物理样品/模型/数据集。
5. 未报告项进 `unreported` 列表；源内部冲突保留而不是静默消解；行内公式/下标线性化为文本。

## 5. 命令序列（可直接照抄）

```bash
# 0) 看一眼输入里有什么
ls /input

# 1) 发现输入、规范化语料 -> /app/work/corpus.json
python3 /skills/weekly-skill/scripts/kg_pipeline.py discover --input /input --work /app/work

# 2) 【模型步骤】读 /app/work/corpus.json 的段落，写 /app/work/extractions.jsonl
#    （格式：references/extraction-schema.md；每条 node/edge 必须带逐字引文）

# 3) 机械校验引文 -> /app/work/verified.json（拒绝行进 quarantine，并打印统计）
python3 /skills/weekly-skill/scripts/kg_pipeline.py verify --work /app/work \
    --extractions /app/work/extractions.jsonl

# 4) 构建图（应用 merge/nonmerge，保留数值冲突）-> /app/work/graph.json
python3 /skills/weekly-skill/scripts/kg_pipeline.py build --work /app/work

# 5) 执行 case.json 的 query_specs -> /app/work/queries.json
python3 /skills/weekly-skill/scripts/kg_pipeline.py query --work /app/work

# 6) 渲染全部交付物 -> /app/output/（也可单独调 render.py）
python3 /skills/weekly-skill/scripts/kg_pipeline.py render --work /app/work --output /app/output

# 7) 镜像 output_contract 组装 result.json
python3 /skills/weekly-skill/scripts/kg_pipeline.py assemble --work /app/work --output /app/output

# 或者一把梭（等价于 1+3+4+5+6+7）：
python3 /skills/weekly-skill/scripts/kg_pipeline.py all --input /input --work /app/work \
    --extractions /app/work/extractions.jsonl --output /app/output
```

## 6. 交付物清单与审查方式（评审者指南）

| 文件 | 审查方式 |
|---|---|
| `result.json` | 镜像 output_contract；含 status/sources/uncertainty/change_records/artifacts。 |
| `graph.svg` | **签名产物**：全图，浏览器直接打开。按实体类型分列、列内按标签排序、边为贝塞尔曲线、箭头+关系标签；悬停看完整标签与限定词。 |
| `query_<id>.svg` | **签名产物**：每个执行的查询一张，与全图**同一坐标系**，结果子图红色高亮、其余淡化为 12% 透明度——可逐坐标对照。 |
| `report.html` | **签名产物**：自包含单文件（内联 SVG、无外部依赖）。§1 全图；§2 各查询（图+参数+结果表+冲突检查+未确定项）；§3 证据索引（每条含逐字引文与"子串已校验"标记）；§4 合并账本/非合并登记/冲突保留/未报告；§5 校验统计。 |
| `report.md` | 上述内容的 markdown 摘要。 |
| `nodes.csv` / `edges.csv` | 表格工具直接打开；含证据地址列。 |
| `graph.jsonld` | JSON-LD 导出，供下游语义工具消费。 |
| `graph.graphml` | GraphML 导出，可导入 Gephi/Cytoscape 等。 |
| `evidence_index.json` | 全部证据条目（EV001…），每条 `quote_verified` 为渲染时重新机械校验的结果。 |
| `verification_report.json` | verify 阶段的统计与被拒绝行（含原因码）。 |

布局算法与确定性保证详见 `references/artifact-guide.md`。

## 7. 异常处理（诚实降级，不硬撑）

- 缺 `case.json` → 警告，`case_id="unknown-case"`，无 contract 时仍产出完整 result.json。
- 缺 secondary 全文 → 容忍，单源语料继续跑（警告记录）。
- `material.json` 形态异常 / 某段不是对象 → 跳过并警告。
- `extractions.jsonl` 缺失 → 空图继续（`status` 降为 `unable`，result.json 如实说明）。
- 坏行/坏引文/悬空端点 → 该行拒绝进 `verification_report.json`，不阻塞其余行。
- 查询无可解析节点 → `status=no_match/ambiguous`，消息写入该查询；查询结果为空 → `empty`
  （诚实的空结果，附 undetermined 说明）。
- 无法产出的 contract 键 → `null` + `contract_notes` 原因，整体 status 降 `partial`。
- 清单交叉核对（manifest 的 doi/title/sha256）不一致 → 记录警告，不中断。

## 8. 预算感知退化方案（64 请求 / 900 秒）

按此顺序放弃（越靠后越不能动）：
1. 先砍：`report.md`（信息已在 report.html）。
2. 再砍：每查询 SVG 只画结果子图最高优先级的 1–2 个查询（但 ≥3 个查询仍须执行并写入
   result.json）。
3. 抽取侧：优先覆盖 claim/metric/condition/sample 与 query_specs 直接需要的实体；方法类
   实体可缩减。**绝不**为省时间而跳过引文（无引文的行会被 verify 拒绝，等于白写）。
4. 保底三件套绝不可少：`result.json`（镜像 contract）+ `report.html` + `graph.svg`。
5. 时间充裕时才加 `--run-meta`（墙钟时间只进 `run_meta` 块，不破坏确定性比对）。

## 9. 合成示例

`examples/` 内含完整 SYNTHETIC 示例（明确标注，非真实论文）：6 个输入文件 + 手工编写的
`work/extractions.jsonl`（含跨篇别名合并、"TiO2" 同名不同物显式非合并、21.1% vs 18.7%
不同条件数值冲突保留、滞后指数未报告项、3 个 query_specs）。运行：

```bash
python3 scripts/run_minimal_example.py
```

输出落在 `examples/synthetic/output/`（已随包提交，供不跑代码直接审查；它们是演示产物，
不是正式案例答案）。细节见 `examples/README.md`。

## 10. 参考文档

- `references/extraction-schema.md` — extractions.jsonl 的完整行格式、关系词汇表、合并纪律。
- `references/artifact-guide.md` — 每个交付物的结构、确定性分层布局算法、审查清单。
