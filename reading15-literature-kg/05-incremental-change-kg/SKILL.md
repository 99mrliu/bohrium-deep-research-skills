---
name: incremental-change-kg
description: >-
  Incremental, auditable literature knowledge-graph builder for the 阅读15
  two-paper input revision. The primary paper is sealed as an immutable
  baseline graph (v1); the secondary paper is applied as an explicit
  changeset of ADD / MERGE / KEEP_DISTINCT / UPDATE_EVIDENCE / CONFLICT
  operations producing the current graph (v2) — no destructive overwrite.
  Node/edge IDs are stable semantic hashes: reruns are byte-identical,
  existing records are never renumbered, new records append deterministic
  IDs. A deterministic verifier enforces that every substantive node/edge
  carries source_id + JATS paragraph_id + verbatim short quote (PDF page
  claims are rejected), and that generic aliases cannot force a merge.
  Includes a stable-ID version differ, a query executor (>=3 real queries
  across baseline and current), and an assembler that mirrors every
  output_contract key into result.json. Use when /input provides
  case.json, task.md, corpus-manifest.json, material.json,
  primary-material.json and secondary-material.json.
  增量图谱更新与可审计性：基线封存、变更集追加、稳定 ID、逐字证据校验、
  双版本查询、冲突保留不覆盖。
---

# 增量变更知识图谱（incremental-change-kg）—— 基线封存 + 变更集 + 全链路可审计

**核心主张。** 两篇论文的图谱不应"一次重建"，而应是"一次封存 + 一次增量变更"：
primary 论文建成 **baseline v1 并封存**（之后任何步骤都不改写它），secondary 论文
以**显式变更集**（changeset）应用，产生 **current v2**。每个变更操作都带 before/after
快照与原文短引，写入人类可读台账；既有节点/边 ID 永不改号，新记录只追加确定性 ID；
冲突与未报告项并列保留，绝不覆盖、绝不把不同论文的条件/样本/数值合成一个结论。

## 何时使用

- `/input/` 提供 `case.json`、`task.md`、`corpus-manifest.json`、`material.json`、
  `primary-material.json`、`secondary-material.json`（可选 `secondary-publisher.xml`
  供人工核对行内公式）。需要在同一图谱中保留两篇材料的节点、关系与来源，并交付
  `/app/output/` 下可复核的图谱、查询、变更记录与 `result.json`。

## 工作流（路径相对于本 SKILL.md；平台运行时 /input、/app/work、/app/output）

**0. 定向（读输入）。** `ls /input`；读 `case.json`（记下 `case_id` 与
`output_contract` 全部键）、`corpus-manifest.json`（各来源 DOI/作者/许可/哈希）、
`task.md`。根 `case.json` 的 DOI/title/authors **只属于第一篇**，不得套到第二篇。

**1. 尽快落一份诚实的部分结果（0 风险）。**

```bash
python3 scripts/kg_assemble.py --input-dir /input --work-dir /app/work \
    --output-dir /app/output
```

产物缺失时 `result.json` 以 `status=partial` + 缺口说明落盘；之后每完成一步重跑一次，
状态自动升级。任何中断都留下有效结果。

**2. 阅读 primary，编写 baseline 候选（Agent 的语义工作在这里）。**
按 `references/change-semantics.md` 的类型词表，把真实出现在 primary 正文中的实体
（材料/方法/任务/指标/研究者/结论/样品/数据集/条件/器件）与有证据支持的关系写成
`/app/work/baseline-candidates.json`。每个实质节点/边必须绑定
`source_id + paragraph_id（组织方 JATS 段落 ID）+ 原文精确短引（≤280 字符）`；
**禁止 page 字段**（本包无 PDF 页码）。然后校验并封存：

```bash
python3 scripts/kg_verify.py --input-dir /input \
    --candidates /app/work/baseline-candidates.json
python3 scripts/kg_apply.py init --input-dir /input \
    --candidates /app/work/baseline-candidates.json --work-dir /app/work
```

校验任何 ERROR 都拒绝落盘；`init` 产出封存的 `graph-v1.json`（+jsonl）。

**3. 阅读 secondary，编写变更集。** 对照 `graph-v1.json` 中的稳定 ID，把新论文带来的
变化写成 `/app/work/changeset.json`，五种操作（详见 references/change-semantics.md）：

- `ADD`：新实体/新边（secondary 的新方法、新样品、新数值边——不同数值天然不同边 ID，
  从机制上防止数值合并）；
- `MERGE`：真别名合并，须给出 justification 与双方证据；**通用术语（"commercial
  carbon black"、"sample"、"reference" 等，见词表）仅凭同名不能合并**，除非确有显式
  证据并设 `allow_generic: true`；幸存者保留原 ID，被吸收者记为别名+证据，不删除；
- `KEEP_DISTINCT`：同名/通用术语但无同一物理对象证据时，保持区分（新节点获得
  确定性 `_2` 后缀 ID，旧 ID 不动）；
- `UPDATE_EVIDENCE`：只向既有节点/边追加证据，不改写原内容；
- `CONFLICT`：结论/关系冲突时新增冲突边并与旧边结成 `conflict_group`，**双方并列
  保留，均不覆盖**。

校验并应用：

```bash
python3 scripts/kg_verify.py --input-dir /input --changeset /app/work/changeset.json \
    --graph /app/work/graph-v1.json
python3 scripts/kg_apply.py apply --input-dir /input --work-dir /app/work \
    --changeset /app/work/changeset.json
```

产出 `graph-v2.json`（+jsonl）、`changes.json`（+jsonl）、`change-ledger.md`
（人类可读台账：逐操作的 before/after、理由、证据短引）。

**4. 版本差异与真实查询（≥3 个，须覆盖两个版本）。**

```bash
python3 scripts/kg_diff.py --baseline /app/work/graph-v1.json \
    --current /app/work/graph-v2.json --out /app/work/diff.json
python3 scripts/kg_query.py --baseline /app/work/graph-v1.json \
    --current /app/work/graph-v2.json --spec /app/work/query-specs.json \
    --out /app/work/queries.json
```

查询算子：`find_nodes` / `find_edges` / `neighbors` / `evidence` / `conflicts` /
`node_history`（单节点跨版本 before/after）/ `diff_summary`。至少包含一个
**baseline vs current 的变化查询**（如 `node_history` 或 `diff_summary`）和一个
对 baseline 单版本的查询。所有结果内联证据短引。也可单次即席查询：

```bash
python3 scripts/kg_query.py --graph /app/work/graph-v2.json --op find_edges \
    --args '{"relation":"delivers_capacity"}'
```

**5. 装配交付。**

```bash
python3 scripts/kg_assemble.py --input-dir /input --work-dir /app/work \
    --output-dir /app/output
```

产出：`graph-baseline.json/jsonl`（封存基线）、`graph-current.json/jsonl`（完整当前图）、
`queries.json`（真实执行的查询+证据）、`changes.json/jsonl`、`change-ledger.md`、
`graph-preview.md`、`graph.dot`、`graph.svg`（文本预览）、`result.json`。
`result.json` 回显 `case_id`，并**动态镜像 `output_contract` 的全部键**：能填的填真实
产物索引，填不了的填 `null` 并记入 `uncertainty`；`status` 为
success/partial 并附原因。

## 不变式（工具强制，详见 references/）

1. **稳定 ID**：ID = 类型缩写 + 语义键哈希；重跑字节级一致；撞键只追加 `_2/_3`，
   既有记录永不改号（references/version-model.md）。
2. **无破坏覆盖**：MERGE/CONFLICT/UPDATE_EVIDENCE 全部只追加；baseline 文件封存
   只读（references/change-semantics.md）。
3. **证据强制**：quote 逐字命中 JATS 段落才允许落盘；page 字段直接拒绝。
4. **数值不合并**：不同来源的条件/样本/数值分边保存；冲突进 `conflict_group`。
5. **幂等**：重复应用同锚点记录自动跳过；`tests/negative_tests.sh` 实测。

## 异常处理

- 材料缺失/段落为空 → 校验器 ERROR，保持 partial 并说明缺口；
- quote 不匹配 / paragraph_id 不存在 / 未知 source_id → 拒绝并指出位置；
- 同名 KEEP_DISTINCT 后按标签解析会报歧义 → 改用显式 `id` 或 `{"ref":"op:N"}`；
- 查询无结果 → 正常返回空列表并 `result_count: 0`，不编造；
- `output_contract` 出现本 Skill 不产出的键 → 填 `null` + uncertainty 说明。

## 预算纪律

步骤 1、2 的校验/封存与步骤 4、5 全部不耗模型请求；模型预算只花在阅读与编写候选/
变更集/查询清单上。先跑步骤 1 落 partial，再逐步完善。

## 文件清单

- `scripts/`：`kg_common.py`（共享库）、`kg_verify.py`（确定性校验器）、
  `kg_apply.py`（封存/变更集应用）、`kg_diff.py`（稳定 ID 版本差异器）、
  `kg_query.py`（查询执行器）、`kg_assemble.py`（装配器）。Python3 标准库，零依赖。
- `references/`：`version-model.md`、`change-semantics.md`、`reproducibility.md`、
  `limits.md`。
- `examples/`：`minimal-example.md`（最小调用）；`synthetic/`（**SYNTHETIC 合成
  示例**：两篇合成论文，最终 9 节点 9 边，演示全部五种操作与 5 个真实查询；
  `run_synthetic.sh` 一键复现，`tests/negative_tests.sh` 负向测试）。
  合成示例仅演示接口，不冒充正式案例结果。
