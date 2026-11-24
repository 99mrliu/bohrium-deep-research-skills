---
name: skill-d-calibration-chamber
description: 学术规范与合规审查的判定校准与误报抑制。当需要对论文/科研材料做质量、引用、事实、方法、统计、逻辑或规范审查并逐条给出证据与严重度时使用：草稿 findings 先经严重度规则引擎机械校准（判定强度不得超过证据强度），再经风格/违规鉴别表拦截学科惯例误报，最后对抗式控辩复核执行降级纪律。适用于任何需要"误报与漏报同样扣分"的审查任务。
---

# Calibration Chamber：判定校准与误报抑制

## 1 用途与新增价值

通用 Agent 做学术合规审查的典型失败有两种：**过度定罪**（把学科惯例、体例风格、
善意疏忽误判为学术不端）与**判定强度越界**（无证据却报 critical）。本 skill 在
Agent 写出 findings 草稿之后、交付之前，插入三道**机械闸门**，保证每条 finding 的
判定强度与证据强度匹配：

1. **severity_gate.py**（规则引擎 R1–R8）：按证据种类（evidence_kind）封顶严重度；
   无证据/纯推断一律封顶 minor 并转 `待复核`；诚信类指控无外部记录双信号封顶
   major 并转 `待复核`；逐条触发规则写入 audit_trail。
2. **fp_screen.py**（误报鉴别 FP-01…FP-10）：机器可读鉴别规则表，把无 DOI 的会议
   文献、作者名拼写变体、预印本、p 值写法差异等典型误报 drop/downgrade，并给出
   规则名与理由。
3. **adjudicate.py**（对抗式复核 A1–A5）：为幸存的每条 finding 生成控辩复核卡
   （prosecution 原文证据 vs defense 善意解释），执行降级纪律后给出
   维持/降级/待复核裁定，供 Agent 终审。

**注意**：闸门只校准判定，不替代审查本身。Agent 仍须完成 case.json 声明的**全部
审查面**并产出完整审查报告；未覆盖的审查面必须列入 `not_reviewed` 并说明原因。

## 2 适用条件与不适用情况

适用：
- case.json 要求类型化 findings + 严重度 + 证据的审查任务（质量/引用/事实/方法/
  统计/逻辑/规范）。
- 草稿 findings 可能来自模型推断，需要机械降级纪律与可复跑的审计轨迹。

不适用：
- 没有草稿 findings 时（闸门不替你发现新问题——先用你自己的审查能力写出草稿）。
- 需要联网外部核验本身（那是 skill-c 的重心；本 skill 只消费核验结果
  evidence_kind=external_record，断网时一律按待复核处理，不凭空补结论）。

## 3 运行时契约与路径

- 输入：`/input/case.json`、`/input/task.md`、`/input/` 下的论文材料（真实 PDF，
  须亲自读文件，不得从标签臆测）。
- 工作目录：`/app/work`（中间产物：抽取文本、findings 草稿、闸门输出）。
- 交付：`/app/output/result.json`（必填 `case_id` 与 output_contract 全部字段，
  诚实标注 status / sources / uncertainty / change_log）。
- 脚本安装位置：`/skills/weekly-skill/scripts/`，参考表在
  `/skills/weekly-skill/references/`。
- 脚本仅依赖 Python 3 标准库，确定性，单次 <5 秒，缺键不崩（exit 0，错误写入
  输出的 `*_errors` 字段）。

## 4 工作流（编号步骤，命令可直接复制）

0. **读案例**：读 `/input/case.json` 与 `/input/task.md`，列出全部审查面；读真实
   材料文件。
1. **保底**：先在 `/app/output/result.json` 落一份合法 partial（status=partial，
   not_reviewed 列出全部审查面），再开始迭代（见 §8）。
2. **逐面审查**：按审查面写出 findings 草稿 `/app/work/findings_draft.json`。
   每条 finding 要素：`id`、`type`、`category`（fact_error /
   insufficient_evidence / norm_issue / suggestion）、`claimed_severity`
   （critical/major/minor/info）、`location`{file,page,section,quote 逐字}、
   `quote`（逐字摘录）、`evidence`（本地规则名或外部来源+检索到的原文）、
   `evidence_kind`（verbatim_quote / external_record / local_rule /
   model_inference / none）、`suggestion`、`verdict_status`、`context_flags`
   （鉴别筛所需的结构化上下文，如 reference_type、no_doi、name_variants_only、
   missing_ethics_statement、p_value_style_only 等，见
   references/discrimination_rules.md）。**诚实标注 evidence_kind**：没有逐字
   摘录就写 model_inference，这是闸门正确工作的前提。
3. **严重度闸门**：
   ```bash
   python3 /skills/weekly-skill/scripts/severity_gate.py \
     --input /app/work/findings_draft.json \
     --output /app/work/gated_findings.json \
     --log /app/work/severity_downgrade_log.json
   ```
4. **误报鉴别筛**：
   ```bash
   python3 /skills/weekly-skill/scripts/fp_screen.py \
     --input /app/work/gated_findings.json \
     --output /app/work/screened_findings.json \
     --log /app/work/fp_screen_log.json
   ```
5. **对抗式复核**：
   ```bash
   python3 /skills/weekly-skill/scripts/adjudicate.py \
     --input /app/work/screened_findings.json \
     --output /app/work/adjudication.json
   ```
6. **人工终审**：逐条读 adjudication.json 的复核卡；对照
   `references/discrimination_rules.md` 的 FP-11…FP-18（未内嵌脚本的人工条目）
   与 `references/severity_rubric.md`。**覆写脚本裁定必须写理由**并记入
   change_log；drop 的 finding 不删除，保留"误报排除"状态。
7. **交付**：把终审后的 findings 写入 `/app/output/result.json`，逐条满足 §5
   要素；无法确认的标 `待复核`+理由；未审查面进 `not_reviewed`。

## 5 输出契约（result.json 字段与 findings 要素）

result.json 至少包含 case.json `output_contract.required_fields` 声明的全部字段，
通常：`case_id`、`status`（complete/partial/blocked）、`findings`、`uncertainty`、
`sources`、`change_log`、`not_reviewed`。

每条最终 finding：`id`、`type`、`category`、`severity`（闸门+终审后的最终值）、
`location`{file,page,section,quote 逐字}、`evidence`、`suggestion`、
`verdict_status`（确认 / 待复核+理由 / 误报排除+鉴别规则名），并保留
`fp_rule`、`ruling` 等审计字段以便复跑一致。

## 6 失败模式与止损表

| 失败模式 | 症状 | 止损 |
|---|---|---|
| 草稿不写 evidence_kind 或乱标 | 闸门全按 none 处理，全部降 minor+待复核 | 诚实标注；这是特性不是 bug，补证据后重跑 |
| context_flags 缺失 | fp_screen 全部 keep，误报漏拦 | 按 discrimination_rules.md 补结构化 flags |
| 把缺声明报成 misconduct | fp_screen FP-05 会 downgrade 为 norm_issue | 接受降级；缺声明≠不端 |
| 断网还想判 fabrication | severity_gate R3 / adjudicate A3 强制待复核 | 转待复核并在 uncertainty 说明，不硬判 |
| 输入 JSON 缺键/损坏 | 脚本 exit 0，输出含 `*_errors` | 读 errors 字段修输入，脚本不会崩 |
| 图像相似凭视觉印象报 critical | R1+R3 降到 minor+待复核 | 必须补像素级对比或外部记录 |

## 7 降级策略（honest partial）

预算或时间不足时：已完成的审查面照常过三道闸门交付；未完成的审查面写入
`not_reviewed` 并说明原因；result.json `status=partial`，`uncertainty` 列出
"哪些判定仅基于 model_inference 待复核""哪些外部核验因断网未完成"。partial 必须
指明局限，不得把未核验条目写成"确认"。

## 8 预算意识

- **先存 partial 再迭代**：第 1 步先落保底 result.json，之后每完成一个审查面
  就更新一次，任何时刻中断都有合法交付。
- 三道脚本总计 <1 秒、零模型请求；把它们当免费闸门，每个审查面的草稿随时过闸，
  不要攒到最后。
- 人工终审只读 adjudication.json 的复核卡（控辩各一句），不要重读全文。
- 64 次模型请求预算的大头留给：读真实材料、写高质量草稿 findings、终审覆写。
