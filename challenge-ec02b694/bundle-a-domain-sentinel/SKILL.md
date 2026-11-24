---
name: domain-sentinel
description: 可行域哨兵——当任务要求"实验参数优化建议"且涉及设备量程、材料耐温、安全阈值、历史实验边界等硬约束时使用；在起草任何推荐参数之前，强制完成约束抽取、可行域冲突扫描与提交前机器硬闸门审计，越界即否决并给出证据定位。
---

# domain-sentinel（可行域哨兵）

## 1. 定位声明

本技能**不替 Agent 写实验方案**，也不是通用流程套壳。它是方案产出的**上游约束真实性层 + 提交前硬闸门层**，对应挑战方向 1「关键参数识别与可行域约束」：

- 从设备手册、材料规格、安全阈值与历史实验中**规则化抽取**参数上下限、步进与互斥关系，形成可被判定的可行域（domain.json）；
- 对可行域做**内部一致性扫描**（conflict_scan）；
- 对任何拟提交方案做**机器硬闸门审计**（domain_audit）：每条推荐值必须落在有来源证据（file/line/quote）的可行域内，越界、违步进、犯互斥、无依据（ungrounded）一律否决，退出码非零。

核心主张：Agent 最常见的失败是推荐值越界（超出设备量程、材料耐温、安全阈值）却不提示。本技能把"每条参数建议必须落在有来源证据的可行域内"变成**强制检查**，而不是建议性自查。

## 2. 运行契约（评测环境）

- 技能安装路径：`/skills/weekly-skill`；以下命令中的 `$SKILL` 即该路径。
- 运行时输入：`/input/case.json`（含 `case_id`、任务描述、`output_contract` 字段清单、材料路径）、`/input/task.md`、案例材料（真实 PDF/文本/CSV）。
- **PDF 无预提取答案层**：Agent 须自行用 `pdftotext` 把 PDF 转成文本到 `/app/work/text/`，再作为材料交给抽取脚本。
- 工作目录 `/app/work`；最终结果写 `/app/output`，必须含 `result.json`。
- 预算：约 **64 次模型请求 / 900 秒**。三个脚本均为确定性 Python 3 标准库程序，**零网络、零模型请求、秒级完成**，可无限次重跑，放心纳入修复循环。
- `result.json` 必须：`case_id` 照抄输入；**动态读取 case.json 的 `output_contract` 并逐项给出字段，不得硬编码**；`status ∈ {success, partial, unable_to_determine, refused}` 且必须诚实；含 `sources`、`uncertainty`、变更记录（`change_log`）。**尽早落盘诚实 partial。**

## 3. 何时使用 / 不适用

**何时使用（触发条件）**
- 任务要求给出实验/工艺参数优化建议，且材料中存在设备量程、材料耐温、安全阈值、流量/压力/速率界限、历史实验边界；
- 任务显式给出参数域或 targets，需要核验目标可行性；
- 多份材料可能对同一参数给出不同界限，需要取最紧并定位证据。

**不适用**
- 纯文献综述、无参数推荐的问答任务；
- 材料中完全不存在任何数值界限，且 case.json 也无显式约束（此时脚本会如实产出空 domain，任何推荐都将是 ungrounded，应直接按 partial/unable_to_determine 处理，而不是强行使用本技能"凑"可行域）；
- 需要跨参数物理耦合建模（如热力学平衡计算）的场景——本技能只做**显式界限**的判定，不做机理推导。

## 4. 固定命令顺序（不得跳步、不得乱序）

```bash
# 0) 材料准备：PDF → 文本（无预提取答案层，必须自行解析）
mkdir -p /app/work/text /app/output
for f in /input/materials/*.pdf; do pdftotext -layout "$f" "/app/work/text/$(basename "$f" .pdf).txt"; done

# 1) 抽取可行域（exit 0；失败也落盘并记录 errors）
python3 $SKILL/scripts/extract_domain.py \
  --case /input/case.json \
  --materials /input/materials --materials /app/work/text \
  --out /app/work/domain.json

# 2) 可行域一致性扫描（exit 0 无冲突；exit 3 有冲突 → 按 recommended_action 处理后才能继续）
python3 $SKILL/scripts/conflict_scan.py \
  --domain /app/work/domain.json \
  --out /app/output/conflicts.json

# 3) Agent 起草方案（本步骤由 Agent 完成，脚本不代写）：写入 /app/work/proposal.json
#    只允许引用 domain.json 中存在的参数；格式见 references/constraint-schema.md 第 4 节。

# 4) 提交前硬闸门审计（exit 0 方可进入 result.json 组装；exit 3 必须修复后重跑本步）
python3 $SKILL/scripts/domain_audit.py \
  --domain /app/work/domain.json \
  --proposal /app/work/proposal.json \
  --out /app/output/audit_report.json
```

铁律：**proposal.json 每修改一次，必须重跑第 4 步**；`audit_report.json` 的 `status` 必须为 `pass`（exit 0）才允许在 result.json 中标记 `success`。第 2 步 exit 3 时按冲突的 `recommended_action` 处理：`degrade`＝以约束界限替代并写入 uncertainty；`handoff`＝列入 confirmation_items 请求人工确认；`terminate`＝停止推荐相关参数并在 result.json 中如实说明（status 不得为 success）。

## 5. 工作流程与预算分配（900 秒 / ~64 次模型请求）

| 时间窗 | 动作 | 模型请求预算 |
|---|---|---|
| T0–60s | 读 case.json 与 task.md；**动态记录 output_contract 字段清单**；pdftotext 解析全部 PDF | ≤4 |
| T60–180s | 跑第 1 步 extract_domain；人工抽读核对 ≥3 条约束的原文行（file/line/quote 是否对得上） | ≤6 |
| T180–240s | 跑第 2 步 conflict_scan；冲突按 recommended_action 处置并记录 | ≤4 |
| T240–600s | 起草 proposal.json；每改一版就跑第 4 步审计（脚本免费）；修复循环 | ≤20 |
| T600–780s | 组装 result.json：动态字段、sources、uncertainty、change_log、闸门证据 | ≤8 |
| T780–900s | 缓冲。**无论如何在 T–120s 前落盘当前最诚实的版本（允许 partial）** | 余量备用 |

要点：脚本是确定性的，**不要用模型请求去做脚本能做的事**（如反复"目测"参数是否越界）；把请求省给证据核对与方案权衡。

## 6. 输出物说明表

| 文件 | 产生步骤 | 内容 | 消费方 |
|---|---|---|---|
| `/app/work/domain.json` | 第 1 步 | 约束列表（parameter/unit/lower/upper/step/mutex_group/safety_related/source{file,line,quote}）、targets、ungrounded_parameters、uncertainty、extraction_log | 第 2/4 步与 Agent |
| `/app/output/conflicts.json` | 第 2 步 | 可行域内部冲突：type/evidence/recommended_action(degrade/handoff/terminate) | Agent 处置 + result.json 附件 |
| `/app/work/proposal.json` | 第 3 步（Agent 手写） | 参数名 → 建议值/允许区间 | 第 4 步 |
| `/app/output/audit_report.json` | 第 4 步 | 每参数 verdict(pass/violation/ungrounded) + 失败原因 + 证据 quote | result.json 的闸门证据 |
| `/app/output/result.json` | 组装 | 见第 8 节契约 | 评测方 |

## 7. 异常处理表

| 异常 | 脚本行为 | Agent 处置 |
|---|---|---|
| case.json 缺失/损坏 | extract_domain 仍写出 domain.json（约束为空，errors 记录），exit 0 | status=unable_to_determine，uncertainty 说明 |
| 材料目录为空/路径失效 | files_skipped 记录原因，exit 0 | 若约束为空 → 不得标 success |
| PDF 无法 pdftotext | 脚本不处理 PDF（files_skipped 注明需先转换） | 换 `pdftotext -raw` 或放弃该文件并记入 uncertainty |
| 抽取到 0 条约束 | domain.json 为空可行域并播种 uncertainty | 任何推荐均 ungrounded → partial/unable_to_determine |
| conflict_scan exit 3 | conflicts.json 含 recommended_action | degrade/handoff/terminate 按第 4 节铁律处置 |
| audit exit 3 且时间不足修复 | audit_report.json 已含违例证据 | 移除越界参数后重跑；仍不行则 status=partial，违例参数从 experiment_plan 剔除并写入 confirmation_items |
| 方案引用 domain 中不存在的参数 | 判 ungrounded，按违规处理，exit 3 | 回材料找证据后重跑第 1 步，或从方案移除 |
| 脚本输出路径不可写 | stderr 报错，exit 1 | 换 /app/work 下可写路径重跑 |

## 8. result.json 契约

```json
{
  "case_id": "<照抄 /input/case.json 的 case_id>",
  "status": "success | partial | unable_to_determine | refused",
  "<output_contract 字段 1>": {},
  "<output_contract 字段 2>": {},
  "...（output_contract 有多少字段就有多少键，动态读取，不得硬编码）": {},
  "sources": ["材料文件路径 + 关键行定位"],
  "uncertainty": ["含 domain.json 的 ungrounded_parameters 与 conflicts 的 degrade 处置声明"],
  "change_log": ["每次方案修改 + 对应 audit 重跑结果"],
  "gate": {
    "conflict_scan_exit": 0,
    "domain_audit_exit": 0,
    "audit_report": "/app/output/audit_report.json",
    "conflicts": "/app/output/conflicts.json"
  }
}
```

诚实规则：
- 任一硬闸门未通过（conflict exit 3 未处置 / audit exit 3）→ **不得标 success**；
- conflict 为 terminate（如目标值突破安全/耐温约束）→ 相关推荐拒绝给出，status=refused 或 partial 并说明；
- 存在 ungrounded 参数被剔除 → partial；
- 可行域为空 → unable_to_determine。

## 9. 合成示例

`examples/` 内含**完全合成**的端到端示例（管式炉焙烧工序，数据为虚构）：synthetic-input 提供 case.json（output_contract 三字段 experiment_plan / evidence_and_risk / confirmation_items）、设备规格文本与历史实验 CSV、两份方案（合格 / 播种越界 1200°C）与一个播种冲突的 domain 变体；synthetic-output 为三个脚本的真实运行产物（domain.json、audit_pass.json、audit_violation.json、conflicts.json、conflicts_clean.json）。复现命令见 `examples/README.md`。

## 10. 局限

- 规则抽取不做过单位换算（如 K 与 °C 不会自动统一）；同一参数以不同单位出现时，界限取最紧可能失真——须人工核对证据 quote。
- "室温–上限"型表述的下界记为 null（开放）；真负温区间需显式数字才能识别。
- 跨参数物理耦合（如"焙烧温度不得超过催化剂耐温"这类**隐式**联动）不会自动推理；Agent 应在 proposal 中把受约束的每个参数都显式列出（示例中同时申报"温度"与"催化剂温度"），由审计分别核验。
- 互斥语义仅支持"同组不得同时赋值"，不支持"二选一必须其一"等更强语义。
- PDF 表格/多栏排版经 pdftotext 后可能错行，导致 quote 与数值错位；人工抽读核对（第 5 节 T60–180s）是强制环节。
- 抽取模式清单与更多已知局限见 `references/extraction-patterns.md`。
