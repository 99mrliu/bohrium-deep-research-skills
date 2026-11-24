---
name: result-contract-replay-compiler
description: 下游交付与可复跑工程的收口工具——当任何检索/分析管线准备交付 result.json 时必须触发，负责把案例 output_contract 镜像成诚实脚手架（首分钟内落地 partial、未填字段为 null 且列入 uncertainty）、以 V1–V6 规则校验契约完整性与状态自洽、把运行日志编译为带 SHA-256 哈希链的 replay manifest 并判定 fresh/stale/missing-input 复跑状态、渲染中文复核报告，从而保证交付物契约完整、诚实标注、可由第三方仅凭记录独立复跑。
---

# result-contract-replay-compiler

下游交付与可复跑工程：result.json 契约镜像与校验、运行日志 → replay manifest、复核报告渲染。
本 skill 不做号码解析、查询构造、引文台账或许可分级——那些属于其他 bundle；本 skill 是**所有案例交付前的最后一道工序**。

## 用途与适用条件

- 适用：任何案例在产出 `/app/output/result.json` 之前、之中、之后的交付收口；预算紧张时保证"诚实 partial 先落地"；交付前强制过闸；交付后供复核人/第三方复跑。
- 不适用：检索策略设计、查询语法构造、号码格式解析、引文比对、许可层级判定（请路由到对应上游 skill）。
- 输入：`case.json`（含 `case_id` 与 `output_contract`，形态任意，脚本防御式提取）、管线产物、运行中产生的文件。
- 产出：`result.json`（契约镜像）、`validate_report.json`、`run_log.jsonl`、`replay_manifest.json`、`review.md`。

## 运行时契约

1. 评测方将本 Skill 安装于 `/skills/weekly-skill`，以官方 DeepSeek Harness 运行 3 个固定隐藏案例。运行时输入为 `/input/case.json` + `/input/task.md` + 材料文件。**必须读取真实文件内容，绝不根据文件名臆测。**
2. 工作目录为 `/app/work`；交付物为 `/app/output/result.json`，须含 `case_id`、诚实的 `status`（ok/partial/failed）、`sources`、`uncertainty`、`change_records`，并**镜像该案例 output_contract 的全部字段**（未填写 → 置 null 且列入 `uncertainty`）。本 bundle 正是该契约的执行机器。
3. 预算 64 次请求 / 900 秒。**第一条命令永远是 scaffold_result**：诚实的 partial 在第一分钟内落入 `/app/output`；此后每一次改进都重写 result.json 并追加一条 `change_records`。
4. 绝不编造缺失字段；partial 结果必须点名自身限制（`uncertainty` 条目以字段名开头）。
5. bundle 约束：≤50 个 UTF-8 文本文件，单文件 ≤500KB，总体 ≤2MB，无符号链接、无二进制。

## 调用方式（完整交付闭环）

所有脚本仅用 python3 标准库。退出码约定：`0` 成功；`1` 校验失败；`2` 用法/输入错误。

```bash
S=/skills/weekly-skill/scripts
# 0) 第一条命令：脚手架落地（/app/output/result.json 立即存在，status=partial）
python3 $S/scaffold_result.py --case /input/case.json --out /app/output --note "初始脚手架"
# 1) 主干管线工作（其他 skill / 手工分析），每完成一批就合并一次：
python3 $S/scaffold_result.py --case /input/case.json --out /app/output \
    --fill /app/work/fill_batch1.json --note "填入候选与证据"
# 2) 每步记录运行日志（输入/输出文件即时哈希）：
python3 $S/replay_pack.py log --runlog /app/work/run_log.jsonl \
    --cmd "scaffold_result.py --fill fill_batch1.json" \
    --inputs /input/case.json /app/work/fill_batch1.json \
    --outputs /app/output/result.json --workdir /app/work
# 3) 契约校验（三闸之一）：
python3 $S/contract_validate.py --case /input/case.json \
    --result /app/output/result.json --out /app/work/validate_report.json
# 4) 打包 replay manifest（三闸之二）并核验 fresh/stale：
python3 $S/replay_pack.py pack --runlog /app/work/run_log.jsonl --out /app/work/replay_manifest.json
python3 $S/replay_pack.py verify --manifest /app/work/replay_manifest.json
# 5) 渲染复核报告（三闸之三）：
python3 $S/report_render.py --result /app/output/result.json \
    --manifest /app/work/replay_manifest.json --out /app/output/review.md
# 6) 最终再校验一次（状态若升级为 ok 必须真的无 null 契约字段）：
python3 $S/contract_validate.py --case /input/case.json \
    --result /app/output/result.json --out /app/work/validate_final.json
```

**交付门槛：validate（exit 0）+ replay verify（无 missing-input）+ render 复核报告，三闸全过才允许交付。**

## 输出

| 文件 | 说明 |
| --- | --- |
| `/app/output/result.json` | 契约镜像结果：case_id / status / 契约字段 / sources / uncertainty / change_records |
| `validate_report.json` | V1–V6 逐条 pass/fail/warn 及消息，overall 结论 |
| `run_log.jsonl` | 每行一步：ts、cmd、workdir、输入/输出文件 SHA-256 |
| `replay_manifest.json` | 有序步骤 + 文件哈希 + 环境说明（python 版本、平台、路径说明） |
| `review.md` | 中文复核报告（六章节，见下） |

## 关键方法

1. **契约镜像即脚手架**：从任意形态的 case.json 防御式提取 `output_contract`（支持 `{字段:描述}`、字符串列表、`{"name":...}` 列表三种形态；找不到则空镜像 + 警告），全部字段先置 null 并列入 uncertainty，后续 `--fill` 深度合并（dict 递归、其余替换），已填字段自动从 uncertainty 移除；fill 中 `case_id` 与 `_` 开头注释键一律忽略。
2. **校验规则 V1–V6**：V1 case_id 一致；V2 契约字段顶层齐备（缺失 fail；为 null 必须列入 uncertainty）；V3 status ∈ {ok,partial,failed} 且自洽（ok 禁止 null 契约字段，partial 要求 ≥1 条 uncertainty 点名限制）；V4 sources 每条含 name + query_date/access_date；V5 编造标记检查（候选 evidence 为空、出现 TODO/PLACEHOLDER 等 → warning，不单独致 fail）；V6 change_records 非空。
3. **run-log 哈希链 → manifest → fresh/stale**：每步在命令执行后立即 log（输入缺失 exit 2；输出缺失记 null + 警告）；pack 固化环境说明；verify 重新哈希：全部一致 = fresh，哈希不符 = stale（如实报告、exit 0），输入缺失 = missing-input（exit 1，无法复跑）。
4. **复核报告结构**：案例标识与状态 / 主结果表（候选 + 证据定位符）/ 来源清单（名称、版本、查询日期）/ 不确定性与未完成项 / 变更记录 / 可复跑性（逐步骤 fresh/stale/missing-input，渲染时重新哈希实测）。

## 案例路由表

| 案例类型 | 本 skill 的角色 |
| --- | --- |
| 号码类案例（公开号/申请号检索） | 上游号码解析与检索管线跑完后，一律收口：scaffold → validate → replay → render |
| 主题类案例（技术主题/语义检索） | 同上；主题召回不全时必须保持 partial 并在 uncertainty 点名 |
| 法律状态类案例 | 同上；`legal_status` 等契约字段未确认前不得置 ok |
| 任何其他形态案例 | 本 skill 与上游无关，凡交付 result.json 必经三闸 |

## 异常处理表

| 异常 | 行为 | 退出码 |
| --- | --- | --- |
| case.json 无 output_contract | 空镜像 + stderr 警告，继续 | 0（validate 时 V2 记 warn） |
| case.json 无 case_id | 占位 UNKNOWN-CASE + 警告 | 0（validate 时 V1 fail） |
| 输入文件不存在 / JSON 解析失败 | stderr 报错 | 2 |
| fill 含 case_id 或 `_` 开头键 | 忽略 + 警告，绝不覆盖 case_id | 0 |
| result 缺契约字段 / null 未列入 uncertainty | V2 fail | 1 |
| status=ok 但仍有 null 契约字段 | V3 fail（过度声明） | 1 |
| sources 记录缺 name/日期 | V4 fail | 1 |
| 候选 evidence 为空 / 出现 TODO 等标记 | V5 warning（不单独致 fail） | 0 |
| replay log 时输入文件缺失 | 报错 | 2 |
| verify 时步骤输入缺失 | 逐步报告 + 汇总 | 1 |
| verify 时文件哈希不符 | 标 stale，如实报告 | 0 |

## 自查

```bash
python3 /skills/weekly-skill/scripts/selfcheck.py   # 37 项断言，全过 exit 0
```

## 最小示例

```bash
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json \
    --out /tmp/out --note "初始脚手架"
python3 scripts/contract_validate.py --case examples/fixtures/case_fixture.json \
    --result /tmp/out/result.json --out /tmp/out/validate_report.json
```

完整可走查示例见 `examples/example_walkthrough.md`；契约语义见 `references/contract_fields.md`；复跑协议见 `references/replay_protocol.md`。
