---
name: semalign-contract
description: 上游契约与字段语义对齐门禁。当任务是科研数据分析（/input 含 case.json 的 case_id 与 output_contract、task.md、数据字典、CSV 快照或 SQLite 数据库，要求清洗/统计/可视化/查询并在 /app/output 交付可复核 result.json）时使用。重心在链路上游：先把 output_contract 编译成机器可核对的契约清单，把数据字典字段与实际列名做归一化相似度对齐（未对齐项强制人工裁决），并在任何计算之前落盘 result.json 诚实骨架；交付前用契约门逐项核对，缺字段、空值、图文件不存在、case_id 不符一律以退出码 1 阻断。不适用：需要训练模型、机理解释或论文写作的任务。
---

# semalign-contract：先钉住契约，再开始计算

## 为什么重心放在上游

本场景中"跑通了但算错了"的事故，一半以上在第一步就埋下：字段名与数据字典对不上（`Compressive Strength (MPa)` vs `strength`）、契约字段漏交付、把缺失标记当 0、case_id 抄错。下游再精细的统计也救不回上游的错位。本 Skill 不做统计计算本身，它提供两个确定性工具动作，把"任务要求什么"与"数据实际有什么"固化为可机检工件：

- `inspect`：输入档案 + 契约编译 + 字段对齐 + result.json 骨架（最先做）。
- `gate`：交付前契约门（最后做，FAIL 即禁止交付）。

你的角色：读 profile/contract/mapping 三份工件 → 用任意方法完成真实计算并填充骨架 → 过 gate。统计计算请用平台科学 Python 环境自行完成；本工具不替你算，也不接受你绕过它改骨架。

## 固定路径与运行契约

- 工具：`/skills/weekly-skill/scripts/semalign.py`（纯标准库，`python3` 直接运行）
- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`、数据字典与数据文件
- 工作区：`/app/work`（profile.json、profile.md、contract.json、field_mapping.json）
- 交付：`/app/output/result.json` + 图表/清洗表等附件；result.json 必须含 `case_id` 与 output_contract 列出的**全部字段**、list 型 `anomalies`、含 `input_hashes` 的 `provenance`
- 诚实 partial：任何字段无法完成时，result.json 置 `status="partial"`，并在 `missing_fields` 中逐项给出 `[{"field": ..., "reason": ...}]`；gate 允许有说明的 partial，拒绝无声的 null

## 执行协议

### 第 0 步：建档（一切计算之前）

```bash
python3 /skills/weekly-skill/scripts/semalign.py inspect \
  --input /input --work /app/work --output /app/output
```

产出 `/app/work/profile.md`（每个文件的 sha256、编码、分隔符、行列数、每列类型/缺失数/数值范围/完全重复行数；SQLite 的表结构与逐列 NULL 计数）、`contract.json`（case_id、契约字段清单、义务条款）、`field_mapping.json`（字典字段→实际列，含 score 与 `needs_human_confirm` 标记），以及 `/app/output/result.json` 骨架（全部契约字段 null、status=in_progress、provenance 已含输入哈希与 Python 版本）。

### 第 1 步：裁决对齐歧义

`field_mapping.json` 中 `needs_human_confirm=true` 或 `column=null`（UNMAPPED）的条目，必须对照数据字典原文与 profile.md 中的列取值范围人工裁决；把裁决理由写入最终 `anomalies`。单位只以数据字典为准——profile 给出的数值范围用于 sanity check（例如强度列若出现 0–1 区间的小数，提示单位或缩放问题，记录而非擅自换算）。

### 第 2 步：真实计算并填充骨架

按 task.md 完成清洗、统计、图、SQL 查询。填充规则：

- 每个数值必须来自对 `/input` 原始数据（或由其派生的、行数可对账的清洗表）的真实计算；清洗造成的行数变化（原始行→删除缺失→去重→最终行）写入 result.json 的行数对账字段或 `anomalies`。
- 图文件写入 `/app/output` 后在契约字段中登记路径。
- 缺失、异常、空查询、无法解释的结果全部进 `anomalies`，不得静默删改。

### 第 3 步：契约门（交付前最后一步）

```bash
python3 /skills/weekly-skill/scripts/semalign.py gate \
  --input /input --output /app/output
```

检查项：case_id 一致；每个契约字段存在且非 null（partial 须有 missing_fields 说明）；status 合法且 success 时 missing_fields 为空；声明的图文件真实存在；anomalies 为数组；provenance.input_hashes 完整。任何一项不满足，退出码 1 并列出问题清单——逐项修复后重跑 gate，**禁止**直接编辑 result.json 蒙混（gate 可重复运行，修复后必须自然通过）。

## 异常处理原则

- `inspect` 对不可读文件、无法解析的 case.json 只记录 WARNING 并继续，保证骨架始终落盘；你不应因为输入残缺而空手而归。
- 数据与字典冲突（列无对应字典字段、单位不明、重复记录是否该合并无法判断）：取保守口径（不删、不换算、不参与统计），在 anomalies 记录两种解释与所选方案。
- 时间紧张：骨架 + 已完成字段 + missing_fields 说明 = 合法的 partial 交付，优于仓促的"完整"。

## 最小调用示例（合成示例，非正式案例结果）

`examples/` 内含一份合成案例（`synthetic_case/`：case.json、task.md、data_dictionary.json、带缺失与重复行的 measurements.csv）与 `run_example.sh`：

```bash
cd /skills/weekly-skill/examples && bash run_example.sh
```

脚本依次执行 inspect → `fill_demo.py`（扮演 Agent 角色，用 stdlib 完成真实计算并填充骨架）→ gate，最终在 `examples/out/result.json` 得到 status=success 的交付。示例数据为人工合成，仅用于说明接口与流程，输出不对应任何正式案例。

## 资源

- `scripts/semalign.py` — inspect / gate 两命令，零依赖，Python ≥3.8
- `references/contract_protocol.md` — 契约字段填写规范、partial 语义、常见契约违例清单
