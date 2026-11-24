---
name: structure-forge
description: 科研素材思维导图的层级结构体检与确定性再平衡技能；当需要把文献、实验记录、项目计划等材料整理成层级清晰、粒度合规的思维导图，或对已有导图进行结构诊断与机械修复时使用。
---

# Structure Forge：思维导图层级结构工程

## 1. 定位与运行时契约

本技能面向科研素材思维导图的“层级结构工程”：将非结构化或半结构化材料整理为层
级清晰、分类轴一致、粒度合规的树状中间表示，并提供可重复、确定性的体检（lint）
与再平衡（rebalance）工具。本技能不生成内容观点，不润色文字，仅保障结构质量。

运行时契约（必须遵守）：

1. 运行起始时读取 `/input/case.json` 与 `/input/task.md`；原始素材文件位于
   `/input/` 下，只读使用。
2. 一切中间产物（思维导图 JSON、体检报告、再平衡结果、变更记录）写入
   `/app/work`。
3. 最终交付物写入 `/app/output`。其中 `/app/output/result.json` 必须包含：
   原始 `case_id`（逐字保留，不得改写）、该案例 `output_contract` 指定的**全部**
   字段、诚实的状态字段（`success` / `partial` / `unable_to_determine` /
   `refused`）、来源与证据（sources/evidence）、不确定性列表（uncertainties）、
   变更记录（changes）。
4. 应在运行早期先保存一份合法（字段齐全）的 `partial` 状态 `result.json`，随后
   就地改进；时间或请求预算耗尽时，交付物仍处于可评分状态。
5. 同案例重跑必须确定性：本技能全部脚本对同一输入产生逐字节相同的输出。

## 2. 思维导图中间表示（本技能标准化的 JSON schema）

```json
{
  "meta": {
    "purpose": "paper | experiment | project | meeting | knowledge",
    "budget": 120,
    "audience": "目标读者描述"
  },
  "root": "<根节点 id>",
  "nodes": [
    {"id": "n1", "parent": null, "label": "……", "kind": "concept"},
    {"id": "n2", "parent": "n1", "label": "……", "kind": "question"}
  ]
}
```

- `meta.purpose`：导图用途，决定核心 kind 检查集合（见
  `references/taxonomy.md`）。
- `meta.budget`：节点总数预算（整数）。
- `meta.audience`：目标读者（自由文本）。`meta` 允许携带额外说明性键（如
  `note`），工具不解释。
- `root`：根节点 id；恰好一个节点的 `parent` 为 `null`，且必须与 `root` 一致。
- `kind` 词汇表（12 种）：`question, method, evidence, result, conclusion,
  limitation, task, risk, decision, milestone, concept, other`。定义与使用规则见
  `references/taxonomy.md`。

粒度与标签规则（深度 2–5、兄弟节点不超过 7、标签不超过 40 显示字符、近似重复判
据、自动修复边界）见 `references/granularity-rules.md`。

## 3. 何时使用

### 3.1 适用场景

- 依据论文、实验记录、项目计划、会议纪要、文献笔记等科研素材构建思维导图，需要
  先确立层级骨架再填充内容时。
- 已有思维导图（草稿或他处导入）存在重复分支、过载分支、过深嵌套、单子链、标签
  冗长等结构问题，需要客观诊断与确定性修复时。
- 需要可审计的结构变更记录（每次修复一条 JSONL 记录）时。
- 同一案例需重跑且要求结果逐字节一致（确定性流水线）时。

### 3.2 不适用场景

- 需要语义层面的改写、摘要、润色或观点生成（本技能只做结构，不动语义）。
- 素材不是层级结构而是网状结构（概念图、引用网络），树形假设不成立时。
- 需要自动判定孤儿节点归属、自动解开多根或环：此类结构错误涉及语义决策，本技能
  仅报告，不代为裁决。
- 无输入素材的凭空创作。

## 4. 固定运行方式

以下命令假定技能安装于 `/skills/weekly-skill`，在运行环境中逐条执行（仅依赖
Python 3.10+ 标准库，无网络）：

```bash
mkdir -p /app/work /app/output

# 步骤一：对草稿思维导图做结构体检（存在 ERROR 时退出码为 1，属预期）
python3 /skills/weekly-skill/scripts/tree_lint.py \
  --map /app/work/mindmap.json \
  --report /app/work/lint_report.json
echo "lint exit=$?"

# 步骤二：确定性自动再平衡（退出码恒为 0；无法读取输入时为 2）
python3 /skills/weekly-skill/scripts/tree_rebalance.py \
  --map /app/work/mindmap.json \
  --out /app/work/rebalanced.json \
  --changes /app/work/changes.jsonl

# 步骤三：对再平衡结果复检
python3 /skills/weekly-skill/scripts/tree_lint.py \
  --map /app/work/rebalanced.json \
  --report /app/work/lint_report_after.json
echo "lint-after exit=$?"
```

可选参数：`tree_lint.py --budget N` 覆盖 `meta.budget`。

## 5. 工作流程

1. **读取任务**：解析 `/input/case.json`（case_id、output_contract）与
   `/input/task.md`，确定 `purpose`、`budget`、`audience`。
2. **尽早落盘**：先向 `/app/output/result.json` 写入字段齐全、状态为 `partial`
   的合法结果，后续就地更新。
3. **构建草稿**：从素材抽取节点，按第 2 节 schema 写出
   `/app/work/mindmap.json`；每个兄弟组只使用一个分类轴（见
   `references/taxonomy.md`）。
4. **体检**：运行步骤一。ERROR 级问题（多根、环、孤儿、parent 引用缺失、id 重
   复、空标签）由运行者依据素材人工裁决修复；工具不自动处理。
5. **再平衡**：运行步骤二，获得 `rebalanced.json` 与 `changes.jsonl`。
6. **复检与人工收尾**：运行步骤三。残留 WARN（如 `missing_core_kind`）提示需要
   补充内容（例如为论文类导图增补 `conclusion` 节点）；残留 ERROR（孤儿等）必
   须人工处置后重新体检。
7. **交付**：将最终导图、两份体检报告、变更记录与 `result.json` 一并写入
   `/app/output`；不确定性写入 uncertainties，变更写入 changes。

## 6. 输出物说明

| 文件 | 说明 |
| --- | --- |
| `lint_report.json` | 体检报告。`{"summary":{"errors","warnings","nodes","max_depth","max_children"},"findings":[{"severity","check","node_ids","detail"}]}`；findings 按 `(check, node_ids)` 字典序排序，完全确定。 |
| `rebalanced.json` | 再平衡后的导图，schema 与输入一致；节点按 id 排序、键序规范化，保证幂等。 |
| `changes.jsonl` | 每行一次修复操作（`merge_duplicate` / `collapse_chain` / `split_overloaded` / `truncate_label`），被移除节点的原始 label/kind 记录在行内；无修复时为空文件。 |
| `result.json` | 案例交付物：原始 case_id、output_contract 全部字段、诚实状态、sources/evidence、uncertainties、changes。 |

## 7. 异常处理表

| 异常 | 体检检查名（级别） | 自动修复 | 处置建议 |
| --- | --- | --- | --- |
| 多根 | `multiple_roots`（ERROR） | 否 | 人工指定唯一根；多余根改挂或删除 |
| 环 | `cycle`（ERROR） | 否 | 人工断开环中的一条 parent 引用 |
| 孤儿节点 | `orphan`、`parent_missing`（ERROR） | 否 | 由运行者依据素材决定归属或删除；工具绝不静默接管 |
| 兄弟重复 | `sibling_near_duplicate`（WARN） | 规范化完全相同者自动 `merge_duplicate`；仅近似（相互包含）者不合并且保留警告 | 人工确认近似对是否应合并 |
| 分支过载 | `overloaded`（WARN） | 自动 `split_overloaded`，按 kind 插入“<kind>类”分组节点 | 分组后人工复核分组轴是否合理 |
| 层级过深 | `depth`（WARN） | 否 | 人工提升中间层级或合并冗余层 |
| 节点数超预算 | `over_budget`（WARN） | 否 | 人工裁剪低价值分支或上调预算 |
| 标签超长 | `long_label`（WARN） | 自动 `truncate_label`（前 39 字符 + “…”，总长 40） | 人工改写为精炼标签 |
| 同案例重跑需确定性 | ——（设计保证） | —— | 两脚本均按固定顺序、排序键处理；同输入必得同输出，幂等 |

## 8. 最小合成示例说明（合成数据）

`examples/` 下为**合成示例（synthetic）**，课题“多孔材料Z的合成”系虚构，仅用
于演示工具行为：

- `examples/synthetic-input/messy_tree.json`：约 20 节点的 `purpose=paper` 导图，
  人为植入缺陷——兄弟重复标签 1 对（n-dup1/n-dup2）、9 子过载且混用 4 种 kind
  的分支 1 处（n-r）、单子链 1 处（n-q→n-c1→n-c2→n-c3）、孤儿节点 1 个
  （n-orphan，其 parent 引用已删除的 n-deleted）、超长标签 1 条（n-lim，47 字
  符）、全图缺失 `conclusion`。
- `examples/synthetic-output/lint_report.json`：体检结果，`errors=2
  warnings=7`，各植入缺陷均被正确识别（孤儿节点同时触发 `parent_missing` 与
  `orphan` 两条 ERROR）。
- `examples/synthetic-output/rebalanced.json` 与 `changes.jsonl`：再平衡结果及
  其 5 条修复记录（1 次 `merge_duplicate`、2 次 `collapse_chain`、1 次
  `split_overloaded`、1 次 `truncate_label`）。
- `examples/synthetic-output/lint_report_after.json`：复检结果，`errors=2
  warnings=3`。孤儿节点仍列为 ERROR——**结构错误（多根、环、孤儿）不在自动修
  复范围内**，须由运行者依据素材裁决；残留 WARN 为两处 `kind_mixing`（拆分后
  分组轴显性化所致，供人工复核）与缺失 `conclusion`。此输出如实地展示了工具
  契约：机械问题自动修复，语义问题只报告不代决。

## 9. 限制

- 仅支持 Python 3.10+ 标准库；无网络访问；不调用外部模型。
- 树形假设：每个节点至多一个父节点；网状知识需先人工树化。
- 自动修复为纯结构操作：不生成新内容、不改写语义；截断标签可能造成信息损失
  （原文保留在 `changes.jsonl`）。
- `split_overloaded` 按 kind 机械分组，分组质量依赖 kind 标注质量；kind 标注
  混乱时建议人工重新标注后再运行。
- 标签规范化按 Unicode 标点与空白处理，对语义同义（如“合成方法”与“制备路
  线”）无识别能力。
- 深度、子节点数、标签长度等阈值为固定启发式（5 / 7 / 40），不构成普适标准。
