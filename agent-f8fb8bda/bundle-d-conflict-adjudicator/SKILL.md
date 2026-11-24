---
name: dr-conflict-adjudicator
description: 深度研究场景下的证据综合与冲突裁定技能，面向文献综述类任务。重心为冲突证据的机器可查裁定（conflict adjudication）与 A-D 证据分级，强制综合文本句级 [事实]/[推断]/[无法确定] 标注审计。触发词包括 深度研究, 证据综合, 冲突证据, 证据分级, 冲突裁定, 文献综述, deep research, evidence synthesis, conflict adjudication, evidence grading, conflicting evidence, literature review。
---

# dr-conflict-adjudicator —— 深度研究：证据综合与冲突裁定

## 1. 用途与边界

本技能用于文献综述类深度研究任务：把检索到的研究组织为可机检的证据矩阵，自动检出相互矛盾的结论，强制每对冲突留下可复核的裁定依据，按 A-D 规则校验证据分级，并对综合文本做句级事实标注审计。本技能不执行网络检索，不替代领域判断；它保证的是过程可复核、冲突不丢失、结论有边界。

## 2. 运行环境与产物约定

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md` 及材料文件。
- 工作目录：`/app/work`；中间产物（矩阵、登记表、裁定、结论、综合文本）一律落盘于此，便于复核。
- 最终产物：`/app/output/result.json`，必须含原样 `case_id` 与 `output_contract` 声明的全部字段，并诚实标注 `status`（success / partial / failed）、`sources`、`uncertainty`；partial 必须说明限度。
- `output_contract` 的字段名因案例而异：**一律从 case.json 动态读取，禁止硬编码字段名**。
- 脚本仅依赖 Python3 标准库，不需要网络。

## 3. 五阶段流程协议

### 阶段一 契约初始化

解析 case.json，确认 `case_id` 与 `output_contract` 的实际字段名，在 `/app/work` 建立产物清单。防御式读取（字段缺失时以 null 呈现，不得假设结构）：

```bash
python3 -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(json.dumps({'case_id':d.get('case_id'),'output_contract':d.get('output_contract')},ensure_ascii=False,indent=2))" /input/case.json
```

按读到的字段名搭建 result.json 骨架，每个契约字段先置 null，随阶段推进填充。

### 阶段二 问题拆解

将研究问题拆为 3-7 个可独立检索的子问题，每个子问题标明对应的一个或多个结局域（outcome_domain，自定中文短语，全任务内保持一致，冲突检出按它分组）。拆解结果写入 result.json 对应区块。

### 阶段三 检索执行

按子问题逐一检索与阅读材料；每条来源记录 `ref_id` 与文献内定位 `locator`（如 "p.3 表2"）。未检得证据的子问题标记为研究空白，不得编造。

### 阶段四 证据矩阵、冲突裁定与综合（核心）

**4.1 构建研究证据矩阵** `/app/work/study_matrix.jsonl`：每行一研究，字段见第 5 节。随后过结构门控（退出码 0 通过 / 1 违例 / 2 用法或 IO 错误）：

```bash
python3 /skills/weekly-skill/scripts/matrix_check.py --matrix /app/work/study_matrix.jsonl
```

**4.2 冲突检出**：自动检出同结局域内 positive × negative 的冲突对，生成 `/app/work/conflict_registry.json`：

```bash
python3 /skills/weekly-skill/scripts/conflict_adjudicate.py --matrix /app/work/study_matrix.jsonl --registry /app/work/conflict_registry.json
```

**4.3 裁定回填**：对登记表中每个 `conflict_id`，按 `references/adjudication_rules.md` 的框架撰写裁定，写入 `/app/work/adjudications.json`（格式见第 5 节）。裁定必须沿设计层级、样本量与功效、一致性与适用条件展开；禁止只写"尚存争议"。

**4.4 分级结论**：按 `references/grading.md` 给每条结论定级并写适用条件，写入 `/app/work/conclusions.json`。

**4.5 综合文本**：撰写 `/app/work/synthesis.md`，每句以 [事实] / [推断] / [无法确定] 结尾；[事实] 句必须引用矩阵内存在的 [S-编号]。

**4.6 联合门控**：一次执行 C1-C4 全部校验：

```bash
python3 /skills/weekly-skill/scripts/conflict_adjudicate.py --matrix /app/work/study_matrix.jsonl --registry /app/work/conflict_registry.json --adjudications /app/work/adjudications.json --conclusions /app/work/conclusions.json --synthesis /app/work/synthesis.md
```

退出码非 0 时按 stdout 的 C 编号逐项修复后重跑，直至通过；无法修复的违例必须转化为 result.json 中的 uncertainty 说明，不得绕过门控。

### 阶段五 交付门

组装 `/app/output/result.json`：`case_id` 原样写入；`output_contract` 各字段按下节映射填充；附 `status`、`sources`（含 ref_id 与 locator）、`uncertainty`。交付前重跑一次 4.6 的联合门控确认 exit 0；若有任一阶段未完成，status 置 partial 并在 uncertainty 中说明限度。

## 4. 六要点与 result.json 区块映射

字段名以 `output_contract` 实际声明为准，按下表把六要点对号入座（一名称一区块，缺失即失分）：

| 六要点 | 内容来源 | result.json 区块写法 |
|--------|----------|----------------------|
| 问题拆解 | 阶段二 | 子问题清单，各带结局域 |
| 检索覆盖 | 阶段三 | sources：每条 ref_id + locator；未覆盖的子问题单列 |
| 证据回链 | 矩阵与结论 | 每条结论的 evidence 列 study_id，矩阵内可回查 source.locator |
| 冲突证据 | 阶段四 | conflict_registry 全部冲突对 + adjudications 裁定依据与 verdict |
| 综合结论 | 阶段四 | conclusions（含 grade 与适用条件）+ synthesis.md 要点 |
| 研究空白 | 阶段三/四 | 证据缺失的子问题；与"无法确定"分区书写（见 references/grading.md 第 3 节） |

## 5. 数据格式契约

**study_matrix.jsonl**（每行一个 JSON 对象，必填键缺失即 S1 违例）：

```json
{"study_id": "S-1", "design": "rct", "n": 120, "population": "…", "intervention": "…", "outcome_domain": "…", "direction": "positive", "magnitude": "…", "limits": "…", "source": {"ref_id": "…", "locator": "p.3 表2"}}
```

- `design` ∈ {rct, cohort, case_control, cross_sectional, in_vitro, in_silico, review, meta_analysis, other}
- `direction` ∈ {positive, negative, null, mixed}；`n` 为正整数或 null；`magnitude` 字符串可空。

**adjudications.json**（以 conflict_id 为键的对象；`_` 开头的键被忽略，可放备注）：

```json
{"C-1": {"design_comparison": "…", "n_comparison": "…", "consistency_note": "…", "verdict": "coexist_by_context"}}
```

- verdict ∈ {favor_a, favor_b, coexist_by_context, undecidable}；前三项至少两项非空；undecidable 时 consistency_note ≥20 字且须说明无法裁定的具体原因。

**conclusions.json**：

```json
{"conclusions": [{"statement": "…（含适用条件）", "grade": "B", "evidence": ["S-1", "S-3"]}]}
```

- grade A/B 要求 evidence 中 ≥2 个一致方向且 design ∈ {rct, meta_analysis, cohort} 的研究；涉及未裁定冲突对的结论不得高于 C。

**synthesis.md**：标题行（# 开头）与空行豁免；其余每句以 [事实] / [推断] / [无法确定] 结尾，[事实] 句必须含矩阵内存在的 S-编号。

## 6. 退出码与失败处理

两个脚本统一约定：0 通过；1 门控违例（stdout 逐项清单，matrix_check 用 S 编号、conflict_adjudicate 用 C 编号加行号/句号）；2 用法或 IO 错误（stderr）。任何 exit 2 先修输入再重跑；exit 1 按清单修复，不得以删除冲突对、降低标注覆盖率等方式规避。

## 7. 参考文档与示例

- `references/adjudication_rules.md`：裁定框架、verdict 使用条件、为何"尚存争议"是失败产物。
- `references/grading.md`：A-D 定义、结论边界写法、研究空白与无法确定的区分。
- `examples/`：合成示例（synthetic），`bash examples/run_example.sh` 一键演示合规与埋雷两条路径，产物保留在 `examples/output_demo/`。
