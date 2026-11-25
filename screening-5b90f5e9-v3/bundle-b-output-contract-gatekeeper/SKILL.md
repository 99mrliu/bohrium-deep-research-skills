---
name: output-contract-gatekeeper
description: 交付契约守门员——在 Bohrium Playground 挑战赛 challenge-5b90f5e9「系统性文献检索与纳排筛选」等"限时、限请求、合同化交付"的评测运行时中，把"result.json 是否合法、完整、诚实"做成可执行门禁：开工先跑 contract_probe 从 case.json/task.md 的多种形态（嵌套 dict、字段列表、自由文本）探测 output_contract 字段清单与 case_id 并留痕；随即用 scaffold_result 落"零分钟骨架"（status=in_progress、全部合同字段就位、占位 null），保证 900 秒预算内任何时刻中断都有可交付物；案例实质筛选工作进行中以 fill_ledger 逐字段追踪 fill_state（filled/null_with_reason/pending）、来源产物与时间，禁止静默空字段；交付前由 validate_result 强制校验 case_id 一致性、字段齐全、status 词表、诚实规则（completed 不允许空字段、partial 必须有非空限制说明、failed 必须有 reason）与引用路径真实存在，违反即 exit 3 拦截。本技能只守门交付物契约与诚实性：不做文献纳排判定本身、不做检索质量诊断、不做报告渲染；它包裹而非替代案例的实质筛选工作。
---

# output-contract-gatekeeper（交付契约守门员）

## 适用场景与边界（红线）

**适用**：评测器把本 Skill 安装到 `/skills/weekly-skill`，由 DeepSeek Harness 在固定离线案例上运行；
输入 `/input/case.json` 与 `task.md`，中间产物在 `/app/work`，交付 `/app/output/result.json`；
预算 64 请求 / 900 秒——**超时零交付是最常见失败**，本技能的核心动机就是"尽早落骨架、增量填充"：
从第一分钟起磁盘上就存在一份合法（虽未完成）的 result.json。

**红线（本技能不做）**：
- 不做文献纳排判定本身（title/abstract 筛选、去重裁决、冲突调解均由模型按案例要求完成）；
- 不做检索质量/诊断分析；不做任何渲染与排版；
- 不预置任何案例答案；不伪造人工复核；不修改输入 `/input`；
- 不删除合同字段；填不了的字段填 `null` 且必须在台账与 `uncertainty` 中说明原因。

## 运行环境

- Python 3 标准库，无第三方依赖；全部脚本含顶层 `try/except` 兜底。
- 退出码统一：`0`=成功/通过；`2`=用法错误/IO 错误/未捕获内部错误；`3`=合同不可用或门禁违规（交付被拦截）。
- 路径默认值可被命令行覆盖：`--input /input`、`--work /app/work`、`--output /app/output`，
  以及 `--spec / --ledger / --result / --report` 单文件级覆盖。
- 幂等：`scaffold_result.py` 只做并集补全、绝不覆盖已有填充；`fill_ledger.py mark` 重复同值标记只刷新时间戳；
  `validate_result.py` 只读校验 + 原子重写报告；写文件一律 `tmp + os.replace` 原子替换，中断不留半截文件。

## 工作流程

> 本技能**包裹而不是替代**案例的实质筛选工作：第 3 步是模型按 task.md 完成的真实筛选，
> 守门链路（1→2→4→5→6）只保证其交付物合法、完整、诚实。

1. **合同探测 [脚本]** `contract_probe.py --input /input --work /app/work`
   从 case.json（优先，支持嵌套 dict、`fields`/`properties` 包装、键即字段、列表、自由文本字符串）
   与 task.md（兜底，解析"输出合同/result.json"小节的列表与表格）提取 `case_id` 与合同字段清单，
   变形与兜底全部写入 `contract_spec.json` 的 `warnings`/`provenance` 留痕；`case_id` 探测不到 → exit 3。
2. **零分钟骨架 [脚本]** `scaffold_result.py --work /app/work --output /app/output`
   立即落 `result.json`（`status=in_progress`、合同全部字段就位、业务字段占位 `null`、
   `sources/uncertainty/change_records` 初始化为空容器）与 `fill_ledger.json`（字段全 pending）。
   **此后任何时刻被杀死，`/app/output/result.json` 都是一份可交付的合法骨架。**
3. **案例实质工作 + 增量填充 [模型] + [脚本]**
   模型按 task.md 执行检索式解析、题录筛选、去重、冲突处理等实际工作，把中间产物写入 `/app/work`；
   每完成一块，立刻用 `fill_ledger.py mark --field X --state filled --value ... --source /app/work/...`
   把值写入 result.json 并记账；确实填不了的字段
   `mark --state null_with_reason --reason "..."`（缺 reason 直接 exit 3），并在 `uncertainty` 中说明。
   随时 `fill_ledger.py report [--strict]` 查看进度。
4. **终态定级 [模型]** 按 `references/status_honesty_rules.md` 的诚实状态机判定
   `completed / partial / failed`，`fill_ledger.py mark --field status --state filled --value '"<终态>"'`。
   拿不准一律降级：宁可 partial 不可假 completed。
5. **校验门 [脚本]** `validate_result.py --work /app/work --output /app/output`
   七项检查（V1 case_id 一致 / V2 字段齐全 / V3 status 终态 / V4 诚实规则 / V5 台账一致性 /
   V6 引用路径存在 / V7 运行时最低保障字段），任一违规 exit 3 并输出 `validation_report.json`。
6. **终检 [脚本]** `validate_result.py` 重跑确认 exit 0；报告随交付物一并留在 `/app/output`。
   exit 3 时回到第 3/4 步修复或降级，**禁止绕过门禁直接交付**。

## 输出合同映射

| 合同/运行时要求 | 守门实现 |
|---|---|
| `case_id` 与输入一致 | contract_probe 提取 → V1 校验 |
| `output_contract` 全部字段、不得删字段 | scaffold 全字段落位 → V2 校验缺失 |
| 填不了的填 `null` 并在 `uncertainty` 说明 | `null_with_reason` 强制 `--reason` → V4/V5 校验 |
| `status` 诚实（completed/partial/failed） | 诚实状态机（references/）→ V3/V4 校验 |
| 含 `sources`、`uncertainty`、`change_records` | scaffold 结构性落位 → V7 校验 |
| `partial` 必须说明限制 | V4_HONESTY_PARTIAL 强制非空 `uncertainty`/`limits` |
| 引用产物真实存在 | V6 递归收集路径语义字段并逐个 `os.path.exists` |

## 异常处理表

| 异常 | 探测/表现 | 行为 | 退出码 |
|---|---|---|---|
| case.json 缺失/JSON 损坏 | probe warning | 转 task.md 兜底；仍无 case_id 则失败 | 0→3 |
| 合同形态变形（嵌套/列表/自由文本） | probe `contract_shape:*` warning | 归一化提取并留痕 | 0 |
| 完全探测不到业务合同 | `contract_missing_fallback_runtime_minimum` | 回退运行时最低保障字段，要求人工确认 | 0 |
| case_id 探测失败 | spec 落盘 + stderr | 无法守门身份，中止 | 3 |
| 已有 result.json 的 case_id 与 spec 不符 | scaffold 比对 | 拒绝覆盖，中止 | 3 |
| `null_with_reason` 缺 reason | mark 参数检查 | 拒绝静默空字段 | 3 |
| filled 来源产物不存在 | mark `os.path.exists` | 拒绝记账 | 3 |
| 标记合同外字段 | mark 台账比对 | 拒绝静默新增字段 | 3 |
| status=in_progress 就交付 | V3 | 骨架不可交付 | 3 |
| completed 但存在空/pending 字段 | V4/V5 | 拦截，要求填充或降级 partial | 3 |
| partial 无限制说明 / failed 无 reason | V4 | 拦截 | 3 |
| 引用路径不存在 | V6 | 拦截 | 3 |
| 脚本内部未捕获异常 | 顶层 try/except | stderr 输出 FATAL | 2 |

## 最小调用示例

```bash
# 1) 合同探测 → 2) 零分钟骨架（开工前两行，必须先跑）
python3 /skills/weekly-skill/scripts/contract_probe.py --input /input --work /app/work
python3 /skills/weekly-skill/scripts/scaffold_result.py --work /app/work --output /app/output

# 3) 实质筛选过程中增量填充（示例）
python3 /skills/weekly-skill/scripts/fill_ledger.py --work /app/work --output /app/output \
  mark --field decisions --state filled --source /app/work/decisions.jsonl \
  --value "$(python3 -c 'import json;print(json.dumps(json.load(open("/app/work/decisions.json"))))')"
python3 /skills/weekly-skill/scripts/fill_ledger.py --work /app/work --output /app/output \
  mark --field limits --state null_with_reason --reason "有限快照缺 2 篇全文，无法核对全文排除原因"

# 4) 定终态 → 5) 校验门 → 6) 终检
python3 /skills/weekly-skill/scripts/fill_ledger.py --work /app/work --output /app/output \
  mark --field status --state filled --value '"partial"'
python3 /skills/weekly-skill/scripts/validate_result.py --work /app/work --output /app/output
echo "gate exit=$?"   # 0 才允许交付；3 必须修复或降级
```

bundle 自身平台约束自查：`python3 scripts/selfcheck.py`（≤50 文件 / ≤500KB 单文件 / ≤2MB / 全 UTF-8 / 无符号链接 / frontmatter 合法）。

## 维护信息

- 版本：v1.0.0
- 日期：2026-11-25
- 维护方：bohrium-deep-research-skills 项目组
- 仓库：见 `GITHUB_URL.txt`
