---
name: risk-fmea-fallback
description: 用于「实验方案比较与选择」中把风险论证做成可机检产物的场景：为每个候选方案建立结构化风险登记（触发条件、后果量级、S/L/D 定级、缓解、回退），用确定性脚本完成 FMEA 分级、风险调整期望代价比较与回退路径完备性校验，区分「可接受风险」与「不可行」。当任务要求比较多个实验/工艺方案、且评分点涉及风险触发条件、后果量级、缓解措施、替代路径或期望代价时触发。不适用于：无风险的纯文献综述、单一方案无比较对象、或需要真实安全审批/真实供应商报价的场景（本技能只处理情景给定数据，结论均为建议性、需专家确认项不写成事实）。
---

# risk-fmea-fallback：风险与异常驱动的方案决策（FMEA + 期望代价 + 回退路径）

## 解决什么问题

题目点名的典型失败：风险写成「存在一定风险」——没有触发条件、后果量级和缓解措施；不区分「可接受风险」与「不可行」；关键失败场景没有替代路径。本技能把风险做成：**结构化登记 → 确定性分级 → 期望代价比较 → 回退路径图校验**，每一步都有脚本质量门把关，缺陷以退出码 3 拦截。

## 何时使用 / 不适用

- 使用：多候选实验方案比较；需要论证风险、缓解、回退与风险调整代价；rubric 涉及风险完整性。
- 不适用：无风险维度的纯综述；单一方案无比较；任何把情景数字当真实实测/报价的表述（本技能只输出建议性结论，安全/伦理结论必须留给专家确认）。

## 评测运行时契约（必须遵守）

- Skill 安装于 `/skills/weekly-skill/`；输入为 `/input/case.json` 与 `/input/task.md`，科研材料（真实论文 PDF、前瞻性资源/价格/预订契约、每案 3 个版本化候选方案、有限参数域、rubric/硬阈值）在 `/input/` 或其子目录。**必须先读真实文件**，不得凭文件名臆测；PDF 无预抽取答案层。
- 案例是组织方构造的规划情景：契约数字是前瞻性给定，**不是**真实实验室/供应商报价或安全审批；引用时注明「情景给定」。
- 工作目录 `/app/work`；最终结果放 `/app/output/`，必含 `result.json`：`case_id` + `output_contract` 全部原始字段（逐键从 case.json 读取，不漏键不臆造），含诚实 `status`、`sources`、`uncertainty`、变更记录；partial 必须写明限制。**尽早落盘部分结果，再增量改进**。
- 预算：64 次模型请求、900 秒、每响应 16384 token。确定性工作全部交给本技能 stdlib 脚本；模型只做读取、抽取、裁决、文字撰写。

## 分工原则

- **模型**：阅读 /input 真实材料；识别风险；按 `references/severity_anchors.md` 与 `references/likelihood_anchors.json` 锚点定 S/L/D 并挂依据（evidence_source 写明锚点维度/论文页码/契约条目）；设计缓解措施与回退动作；撰写 result.json 文字。
- **脚本（确定性，模型不心算）**：`fmea.py` 做分级算术与登记完备性校验；`expected_cost.py` 做期望代价算术与方案排序；`fallback_graph.py` 做回退完备性与三态结论；`selfcheck.py` 做自查。

## 工作流（严格按序）

三个脚本（fmea.py / expected_cost.py / fallback_graph.py）均支持可选 `--note <文本>`：在 JSON 产物顶层加 `note` 键、Markdown 产物首行加 `> …` 引用标注；生成示例/演示产物时必须传入合成示例标注，正式案例产物可不传（默认行为不变）。

### 步骤 0：读 /input，尽早落盘部分 result.json

读 `/input/case.json`、`/input/task.md` 及材料清单；逐键读取 `output_contract`。立即在 `/app/output/result.json` 写入骨架：`case_id`、output_contract 全部原始键（值可先为 null 或 pending 标注）、`status: "partial"`、`sources: []`、`uncertainty`、变更记录。后续每完成一步增量更新。

### 步骤 1：模型为每个方案填 risk_register.json

每方案一个文件（放 `/app/work/`），结构：

```json
{
  "plan_id": "P1",
  "risks": [{
    "risk_id": "P1-R1", "title": "…",
    "trigger_condition": "可判定的触发条件（禁止『存在一定风险』式空话）",
    "consequence_magnitude": "量级+单位，如『延误 7 天 / 增支 9000 CNY / 均匀性降至 ±8%』",
    "severity": 1, "likelihood": 1, "detectability": 1,
    "mitigation": "非空缓解措施",
    "mitigation_cost_cny": 0, "mitigation_time_days": 0,
    "fallback_ref": "P1-F1 或 null",
    "consequence_cost_cny": 0, "consequence_time_days": 0,
    "evidence_source": "锚点维度 + 情景契约条目/论文页码"
  }],
  "fallback_actions": [{
    "action_id": "P1-F1", "description": "…",
    "adds_cost": 0, "adds_time": 0,
    "requires_expert_confirm": false,
    "on_failure_ref": "可选：该回退自身失败时的下一级 action_id"
  }]
}
```

定级必须引用锚点：severity 见 `references/severity_anchors.md`（安全/进度/经费/数据质量四维取最高）；likelihood 见 `references/likelihood_anchors.json`。

### 步骤 2：fmea.py 分级

```bash
python3 scripts/fmea.py --register /app/work/rr_P1.json --outdir /app/work/P1 [--thresholds 自定义.json]
```

校验必填字段、S/L/D∈1..5、trigger_condition/consequence_magnitude 非空；RPN=S×L×D；按 `references/thresholds.json` 分级（critical: S≥5；high: S≥4 或 RPN≥60；medium: RPN≥25；阈值可覆盖并在输出声明）。输出 `fmea.json` + `fmea.md`。**critical/high 缺缓解 → exit 3**，模型须先补登记再重跑，不得绕过。

### 步骤 3：expected_cost.py 风险调整代价

```bash
python3 scripts/expected_cost.py --register /app/work/rr_P1.json --register /app/work/rr_P2.json \
    --register /app/work/rr_P3.json --base /app/work/base.json --outdir /app/work/compare
```

公式：`risk_adjusted = base + Σ P(L)×后果 + 缓解投入`（缓解为确定支出记加项；其降险效果由登记时调低 L/后果体现）。P(L) 内置映射 {1:0.05, 2:0.15, 3:0.35, 4:0.6, 5:0.85}，单条风险可用 `likelihood_prob_override` 覆盖并在输出声明。base（成本/时间）由输入给定（情景契约），**base 缺失 → exit 2**。输出每方案台账 + 多方案 `comparison.json/.md` 排序。

### 步骤 4：fallback_graph.py 回退完备性

```bash
python3 scripts/fallback_graph.py --register /app/work/rr_P1.json --fmea /app/work/P1/fmea.json --outdir /app/work/P1
```

每条 critical/high 风险必须有 `fallback_ref` 指向存在的回退动作；回退链（on_failure_ref）不得成环；缺回退/悬空/成环 → exit 3 且产物仍写出。三态 verdict：

- `acceptable_risk`：关键风险均有缓解+完整回退链；
- `needs_expert`：回退路径上任一动作 `requires_expert_confirm=true`；
- `infeasible_without_change`：存在缺陷（如 S≥5 无有效缓解/回退）→ **不可行建议，需专家确认**。

`fallback.md` 含每关键场景的替代路径叙述骨架，供 result.json 引用。

### 步骤 5：模型写 result.json

补齐七类字段——**假设、变量、对照、步骤、参数、资源、判读标准**——每类附依据与风险引用；加**确认项**（安全/伦理/设备可用性/专家确认）。规则：

- 选择与舍弃理由必须引用风险台账：如「选 P2：风险调整成本 64420 CNY（comparison.json 第 2 名）且 2 条 high 风险均有缓解与回退（fmea.json/fallback.json）」「舍弃 P3：critical 风险 P3-R1 无回退（fallback.json 缺陷清单），verdict=infeasible_without_change」。
- **pending/需专家确认项不得写成可执行事实**：needs_expert 与 infeasible_without_change 结论写入确认项并标注「建议性结论，待专家确认」。
- 情景数字注明「情景给定」；`sources` 列出实际读过的文件；`uncertainty` 写明定级主观性与概率映射假设。

## 可接受风险 vs 不可行（判据）

- 可接受：S≤4 且缓解非空；critical/high 另有完整回退链。
- 不可行建议：S≥5 且无有效缓解或无回退路径（或回退链缺陷）→ `infeasible_without_change`，必须列为确认项请专家裁决，模型不得自行宣布「方案不可行」。

## 脚本用法与退出码

| 脚本 | 用途 | 0 | 2 | 3 |
|---|---|---|---|---|
| `fmea.py` | 登记校验 + RPN 分级 | 无缺陷 | 文件缺失/JSON 非法/阈值非法 | 字段缺陷、critical/high 缺缓解 |
| `expected_cost.py` | 期望代价 + 方案排序 | 成功 | base 缺失/输入非法 | （保留） |
| `fallback_graph.py` | 回退图完备性 + 三态 verdict | 无缺陷 | 输入非法 | 无回退/悬空/成环/S≥5 无缓解 |
| `selfcheck.py` | examples 全流程自查 | 全过 | 用法错 | 任一断言失败 |

全部脚本 `--help` 可用；纯 stdlib；确定性输出（无墙钟/随机，双跑字节一致）；exit 3 时缺陷清单写 stdout、能写的产物仍写出。

## 七类字段与确认项的落地

风险台账为七类字段中的「判读标准/步骤/资源」提供量化依据：期望代价入资源对比；回退叙述骨架入步骤；trigger_condition 即判读标准中的异常判据。确认项由 verdict 与 `requires_expert_confirm` 机械导出，防止 pending 被写成事实。

## 异常分类处置

- **设备不可得**：登记为高 L 进度风险 + 回退动作（备用设备），货期超窗口按情景契约记量级。
- **耗材超预算/货期**：consequence_magnitude 记超支%/延误天数，进期望代价对比。
- **参数窗口冲突**：登记 trigger_condition 为窗口边界条件，缓解为参数域内收缩窗口。
- **候选方案全部不可行**：result.json status=partial，逐方案列 infeasible 缺陷清单与所需变更，不强行推荐。
- **材料缺失**（/input 无该文件）：相应证据标 unknown，uncertainty 声明，不臆造引用。
- **无法判断**：likelihood/severity 取锚点可辩护值并在 uncertainty 声明，或列确认项。
- **运行失败**：脚本 exit 2 查输入；exit 3 按缺陷清单补登记后重跑；不手改产物。

## 自查方法

`python3 scripts/selfcheck.py`：跑通 examples 全部正负例（正例 exit 0；P3 critical 无回退、空触发条件、回退成环三个负例 exit 3 精确命中），并做双跑字节一致比较。交付前必须 exit 0。

## 适用边界

S/L/D 定级是模型判断，脚本只校验范围与算术；概率映射与阈值是默认假设，覆盖必须声明；所有「不可行/需确认」均为建议性结论；不产出真实安全审批意见；不验证情景外真实价格。

## 合成示例说明

`examples/` 全部为**合成示例 / SYNTHETIC EXAMPLE**（虚构钙钛矿制膜三方案）：P1 低风险（acceptable_risk）、P2 高 RPN 有缓解有回退（needs_expert）、P3 critical 无回退（负例，fallback_graph exit 3，infeasible_without_change），另含空触发条件与回退成环两个负例；`outputs/` 为真实跑出的产物。命令序列见 `examples/README.md`。
