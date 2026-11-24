# 覆盖矩阵（coverage_matrix.csv）三视图定义与缺口处置

`validate_rules.py` 输出 `coverage_matrix.csv`，列：
`view,item,detail,covered_by,status,disposition`。三个视图回答三个不同的问题，
**任何缺口都必须显式登记处置方式**，并最终写入 result.json 的 uncertainty。

## 视图一：field —— 数据字段 × 规则覆盖

- 数据 CSV 表头的每一列（以及规则指向但数据中缺失的字段）一行。
- `covered_by`：作用于该字段的全部 rule_id（`;` 分隔）。
- `status`：`covered` / `uncovered`。
- 缺口处置：未覆盖字段一律 **原样保留**（disposition=“原样保留”），写入
  `rules.final.json` 的 gaps（type=uncovered_field）并抄入 result.json
  uncertainty。**不得**因为没有规则就自行发明处理。

## 视图二：dict_line —— 字典行 × 被引用情况

- 字典中每一个内容行（表格数据行、条目行、键值行、未解析行）一行；
  标题/表头/分隔/说明行不入视图。
- `status`：
  - `parsed`：该行已编译为规则（covered_by 列出 rule_id）；
  - `parsed_no_rule`：描述/登记行，本身不产生规则（如“自由文本备注”）；
  - `resolved`：未解析行经 approve/adjust 裁决补全为规则；
  - `rejected`：未解析行经 reject 裁决不执行（disposition 抄录 rationale）；
  - `unresolved`：未解析行**无人裁决** —— 这是缺口。
- 缺口处置：`unresolved` 写入 gaps（type=unresolved_line，
  disposition=“未裁决，未执行”）与 uncertainty。规则出处核验（source 文件存在、
  行号有效、原文与源文件实际行一致）失败不属于本视图缺口，而是直接
  **退出码 4 整批拒绝**。

## 视图三：workorder —— 工单条目 × 规则覆盖

- 每个工单条目按“涉及字段 × 动作关键词”展开为需求对；动作关键词与规则类别
  的映射：缺失/哨兵→sentinel_missing；换算/单位→unit_scale；去重→dedup；
  范围/物理界/质控/QC→range_qc 或 physical_bound；检出限→lod_below。
- `status`：`covered`（全部需求对有对应规则）/ `partial`（部分有）/
  `uncovered`（全没有）。
- 缺口处置：partial/uncovered 写入 gaps（type=workorder_gap），disposition
  写明“无法执行：哪个字段/哪个动作无对应可执行规则”，抄入 result.json
  uncertainty，status 相应降为 partial。**不得**为完成工单而临时手写无出处
  规则塞进执行阶段——新规则只能经 compile → resolutions → validate 正途进入。

## 缺口总表

`rules.final.json` 的 `gaps` 数组汇总三类缺口：

| type | 含义 | 固定处置 |
| --- | --- | --- |
| uncovered_field | 数据字段无任何规则 | 原样保留 |
| unresolved_line | 字典未解析行无人裁决 | 未裁决，未执行 |
| workorder_gap | 工单条目（部分）无法执行 | 写明无法执行原因 |

交付时：`digest.md` 的“覆盖缺口与不确定性”一节与 result.json 的
`uncertainty` 字段必须与 gaps 全量一致。
