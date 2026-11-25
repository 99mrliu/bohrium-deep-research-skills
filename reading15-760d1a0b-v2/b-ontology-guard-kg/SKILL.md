---
name: b-ontology-guard-kg
description: 用封闭、可机器校验的本体（实体/关系/限定词/极性全部封闭词表）约束文献知识图谱抽取；类型化校验脚本把违规条目按错误码隔离进 quarantine.json，只允许一轮有界修复；merge 规则按实体类型定义，查询按类型化图模式回答。适用于"阅读15｜文献知识图谱构建"中需要强语义治理、可验证语义约束的场景。
---

# b-ontology-guard-kg —— 封闭本体与类型约束的文献知识图谱构建

## 1. 用途与适用条件

本技能面向"阅读15｜文献知识图谱构建"挑战：给定 `/input` 下两篇论文的段落级全文，
构建**每个节点/边都可回溯到原文精确子串**、且**全部通过封闭本体校验**的知识图谱。

重心（与其他技能包的区别）是**语义治理**：

- `references/ontology.json` 是唯一权威：9 种实体类型、9 种关系类型（各带
  domain/range/极性/必需限定词）、6 个限定词键、21 个类型化错误码，全部封闭。
- 模型写的每条抽取都要过 `scripts/validate_ontology.py`；违规条目带错误码进
  `quarantine.json`，`validation_report.json` 给出逐规则违规计数。
- 修复预算**只有一轮**（见 §6）。杜绝"改到过为止"的无界循环。
- 数值结论强制携带 metric+condition（`NUMERIC_REQUIRES_METRIC_CONDITION`），
  从源头防止"不同条件下的数值被并成一个结论"。

适用条件：输入符合 §2 的运行时契约；Python 3.9+，仅标准库，无网络。
不适用：需要开放词表/自由关系抽取的场景（那会直接违背本体的封闭性设计）。

## 2. 运行时契约（必须遵守）

- 输入在 `/input/`：`case.json`（含 `case_id`、`output_contract`、可选 `query_specs`；
  根部 doi/title/authors **只属于 primary 论文**）、`task.md`、`material.json`（容忍
  list / `{"materials":[...]}` / mapping 三种形态）、`primary-material.json`、
  `secondary-material.json`、`corpus-manifest.json`（用 sha256/role/doi 交叉核对归属）、
  可选 `secondary-publisher.xml`（只登记存在，**绝不解析**）。
- 脚本**发现**实际文件，容忍缺 secondary、段落数不同、额外文件；不得硬编码本文件示例内容。
- 中间产物在 `/app/work`；最终交付在 `/app/output`：
  - `result.json`：必含 `case_id` + `output_contract` 声明的**全部**键（动态镜像；
    产不出的键置 `null` 并在 `contract_notes` 记录原因，绝不静默省略）。含诚实
    `status`（success/partial/unable/refused + 原因）、sources、uncertainty、unreported。
  - 签名工件：`validation_report.json`（逐规则违规计数）与 `quarantine.json`（带错误码的隔离区），
    另附 `graph.json`、`query_results.json`、`merge_ledger.json`、`nonmerge_registry.json`。
- 证据规则（不可协商）：
  - 每个实质节点/边带 `source_id` + `paragraph_id`（组织方的 JATS 段落 ID；本数据包
    **没有 PDF 页码，禁止编造页码**）+ 该段原文**精确子串**的短 quote。校验脚本机械
    核查 quote 子串与地址存在性（`ADDRESS_NOT_FOUND` / `QUOTE_NOT_SUBSTRING`）。
  - ≥3 个真实执行的查询（优先 case.json 的 `query_specs`），每个返回结果子图、支持证据、
    显式列出的未决/未知关系。
  - 合并纪律：跨篇合并需归一键 + 显式理由（`merge` op）；同名不同物记显式 `nonmerge`；
    不同条件/样品/数值绝不并为一个结论；跨篇同名通用方法/材料词 ≠ 同一物理样品/模型。
  - 未报告项进 `unreported`；文献内部冲突保留（resolution="preserved"，用 `note` 记录）。
  - 内联公式/下标线性化为纯文本。
- 确定性输出：JSON 一律 `sort_keys`、列表排序；除 `run_meta` 外不写挂钟时间戳（本技能默认不写）。

## 3. 模型 vs 脚本的分工

| 步骤 | 谁做 | 产物 |
|---|---|---|
| 通读两篇论文，写抽取草稿 | **模型**（唯一手写工件） | `/app/work/extractions.jsonl`（JSONL，格式见 `references/extraction_schema.md`） |
| 发现输入、归一语料、manifest 核对 | 脚本 `discover.py` | `corpus.json`、`discovery.json` |
| 封闭本体校验（类型/domain/range/限定词/极性/quote 子串/地址） | 脚本 `validate_ontology.py` | `validation_report.json`、`quarantine.json` |
| 看隔离清单，写**一份**修复文件 | **模型**（仅一轮） | `/app/work/repair.jsonl`（只含被隔离条目的修正版，沿用原 id） |
| 建图（merge 应用、nonmerge 登记） | 脚本 `build_graph.py` | `graph.json`、`merge_ledger.json`、`nonmerge_registry.json` |
| 执行 query_specs（类型化图模式 + 限定词过滤） | 脚本 `query.py` | `query_results.json` |
| 镜像 output_contract 组装 | 脚本 `assemble.py` | `/app/output/result.json` 等 |

模型只写两个小型 JSONL 文件（草稿 + 一轮修复），其余全部机械化——这是为
64 请求 / 900 秒预算设计的。

## 4. 确切命令序列（照抄即可）

```bash
# 0) 输入发现（假设技能装在 /skills/weekly-skill）
cd /skills/weekly-skill
mkdir -p /app/work /app/output
python3 scripts/discover.py --input /input --work /app/work

# 1) 模型通读 corpus.json 中的段落，写 /app/work/extractions.jsonl（见 §5 与 references/extraction_schema.md）

# 2) 第 1 轮校验（草稿）
python3 scripts/validate_ontology.py --work /app/work --extraction /app/work/extractions.jsonl

# 3) 若 quarantine.json 非空：模型读 /app/work/quarantine.json，写 /app/work/repair.jsonl
#    （只含被隔离条目的修正版，沿用原 id），然后第 2 轮校验（修复，唯一一轮）
python3 scripts/validate_ontology.py --work /app/work --extraction /app/work/repair.jsonl --repair

# 4) 建图 → 查询 → 组装
python3 scripts/build_graph.py --work /app/work
python3 scripts/query.py --work /app/work
python3 scripts/assemble.py --work /app/work --output /app/output
```

每条命令都有 `--help`；全部 `python3` 直接可跑，无第三方依赖。

## 5. 封闭本体速览（权威定义见 references/ontology.json / ontology.md）

- 实体：`researcher material method task metric condition sample dataset claim`。
- 关系（domain → range；必需限定词）：
  `uses`(sample/method→material/method/dataset/sample)、`compares`(claim→claim；metric)、
  `outperforms`(claim→claim；metric+condition)、`supports`(claim→claim)、
  `contradicts`(claim→claim)、`measures`(sample/method→metric；condition)、
  `reports`(claim→metric；value+unit+condition)、`reviews-cites`(claim→claim；context)、
  `aliases`(同类型→同类型)。
- 全局规则：带数值 `value` 的边必须同时有 metric（或 metric 客体）与 condition；
  `aliases` 两端类型必须一致；封闭词表外一切拒绝。
- 逐类型合并规则：`sample` **跨篇绝不自动合并**（同名两篇 = nonmerge 候选）；
  `claim` **绝不合并**；`condition` 参数不同不合并；material/metric 的别名对须显式
  `merge` + 理由 + 证据。
- 写草稿前先读 `references/extraction_schema.md`：6 种 op（node/edge/merge/nonmerge/
  unreported/note）的精确字段。

## 6. 有界修复策略（仅一轮，不可协商）

1. 第 1 轮校验后，`/app/work/quarantine.json` 列出每条违规的**类型化错误码**
   （如 `UNKNOWN_RELATION`、`DOMAIN_MISMATCH`、`MISSING_QUALIFIER`、
   `NUMERIC_REQUIRES_METRIC_CONDITION`、`QUOTE_NOT_SUBSTRING`…）。
2. 模型逐条决定：**修**（写进 `repair.jsonl`，沿用原 id）或**弃**（不写即视为放弃，
   例如 quote 无法核实、或该关系本就站不住）。
3. 第 2 轮校验（`--repair`）：通过的条目移出隔离并入图；仍违规或未修复的条目
   永久隔离（`final=true`），不再进入图谱，但在 `result.json` 的 quarantine 摘要中
   如实披露。
4. **没有第三轮**：再用 `--repair` 会被拒绝（退出码 3，`REPAIR_BUDGET_EXHAUSTED`）。
   时间紧时直接跳过 §4 第 3 步，接受隔离损失，也不要超预算。

## 7. 查询回答（类型化图模式）

`query.py` 支持三种模式（对应 case.json `query_specs`）：
`neighborhood`（实体邻域，可限定关系类型）、`edges_of_relation`（某关系全部边，
支持 `qualifier_filter` 等值过滤）、`contradiction_check`（两 claim 间的
contradicts/compares 检查，并列出 condition 差异——条件不同会显式提示"不得合并"）。
每个结果含 `status`（ok/no_match/unknown_entity）、子图、证据 quote、`undetermined`
列表。**空结果是诚实答案**（status=no_match），不是失败。

## 8. 异常处理

| 情况 | 行为 |
|---|---|
| secondary 缺失 | discover 警告并进入单篇模式，流程继续 |
| case.json / 材料文件不可解析 | discover 记 warning 继续；无段落时退出码 1 |
| manifest sha256/role/doi 不符 | 记入 `discovery.json` 的 manifest_check，不中断 |
| 抽取文件缺失 | validate 退出码 2 并提示 |
| 修复超预算 | validate 退出码 3（REPAIR_BUDGET_EXHAUSTED） |
| 查询实体未找到 / 无边命中 | status=unknown_entity / no_match，undetermined 如实列出 |
| contract 键产不出 | result.json 该键置 null + `contract_notes` 记原因，status=partial |
| 图文件缺失 | assemble 仍写出 status=unable 的 result.json（诚实部分结果） |

建议：discover 之后**先写一份早期 partial result.json**（可直接跑一次
`assemble.py`：图未建时会自动标 `unable` 并说明缺失），最后再跑一遍组装刷新。

## 9. 预算感知降级方案（64 请求 / 900 秒）

1. **优先保**：discover → 草稿抽取（1 个大请求写完整个 JSONL）→ 第 1 轮校验 →
   修复（1 个请求）→ build/query/assemble。这是完整路径，约 4–6 个模型请求。
2. 时间/请求紧张时，按序砍：① 放弃修复轮（接受 quarantine，result 照样组装）；
   ② 草稿里只保高价值实体（claim/metric/condition/sample + 跨篇别名对），少写
   researcher/task；③ 查询数 ≥3 是硬要求，但 `query_specs` 若超过 3 个，脚本会全部
   执行——无需模型干预，不耗请求。
3. 不要砍：quote 精确子串、merge/nonmerge 纪律、contract 键镜像——这些是评分核心。
4. 任何降级都要写进 `result.json` 的 `uncertainty` / `evidence_notes`，诚实披露。

## 10. 自检清单（交付前）

- [ ] `validation_report.json` 有逐规则违规计数；`quarantine.json` 条目带错误码与 final 标记
- [ ] 每条 node/edge 的 quote 经脚本验证为原文精确子串（未被隔离）
- [ ] ≥3 个查询真实执行且有证据与 undetermined 列表
- [ ] ≥1 个有理由的跨篇 merge、≥1 个显式 nonmerge；数值冲突仍是两个独立 claim
- [ ] `result.json` 镜像了 output_contract 全部键，status 诚实

## 11. 示例

`examples/` 内含一个**合成**（SYNTHETIC，非真实论文）端到端示例：
`bash examples/run_example.sh` 或 `python3 scripts/run_minimal_example.py`，
从 `examples/synthetic/input` 一路跑到 `examples/synthetic/output`，演示草稿违规 →
隔离 → 一轮修复 → 建图 → 3 个查询 → 组装的完整路径（详见 `examples/README.md`）。
