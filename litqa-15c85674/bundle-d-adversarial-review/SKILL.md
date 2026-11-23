---
name: litqa-adversarial-review
description: 文献智能问答的"对抗式过程质量控制"路线。当任务给出 /input/case.json（带段落编号的论文案例包与中文问题清单）并要求把结构化结果写入 /app/output/result.json 时使用。本 Skill 的重心在过程：写作与审核强制分离——模型在草稿文件中自由作答，审核器逐论断做五路证伪（引文逐字、论断数值必在引文、否定/转折语境、比较论断需双取值、单位风险），verdict=pass 之外的论断机械降级为 unanswered_parts 条目而不是带病交付；修订-复审循环直到全 pass 或预算耗尽，状态由审核记录推导而非模型自述。适用于可靠性要求高、需诚实部分结果的文献问答。
---

# 对抗式过程质量控制（litqa-adversarial-review）

版本：1.0.0　运行环境：Python 3.10+（仅标准库）、shell。零外部依赖。

**方法重心**：一次性"写完自查"的失败在于写作者检查自己的作品——
幻觉数值、含糊比较、断章引文都会安然过关。本 Skill 把过程切成不可妥协的两半：
**模型只写草稿，机器独立证伪，渲染器只放行 pass 的论断**。
未通过审核的论断不会被删掉，而是降级为 `unanswered_parts` 条目并附审核原因——
诚实 partial 是机制输出，不是事后表态。

## 1. 运行契约

- 输入：`/input/case.json`；工作目录 `/app/work/`；输出 `/app/output/result.json`
  与 `/app/answers.json`（render 的 `--legacy` 写出，同内容）。
- `result.json` 字段契约：`case_id`、`paper_id`、`material_version`；
  `answers[]`（`question_id`、`answer`、`conditions[]`、`status`
  ∈ `answered|partial|insufficient_evidence|input_error`、`claims[]`
  （`claim_id` 由渲染器按 `Q<n>-C<i>` 机械分配、`text`、`kind`、`evidence[]`）、
  `unanswered_parts[]`）；`coverage`（`--coverage` 传入留痕文件或留空如实说明）。
  `output_contract` 额外字段：渲染后手工并入并复核。
- **诚实 partial**：prepare 立即写 partial 骨架；render 只交付 pass 论断；
  预算耗尽时直接 render，未过审部分如实降级。

## 2. 流程（每案例约 3 个工具调用 × 1–3 轮 + 读写）

```bash
mkdir -p /app/work /app/output
SRC=$(find /skills -maxdepth 3 -name review_loop.py -path '*/scripts/*' 2>/dev/null | head -1)
[ -z "$SRC" ] && SRC=$(find /app /opt -maxdepth 5 -name review_loop.py -path '*/scripts/*' 2>/dev/null | head -1)
cp -r "$(dirname "$SRC")" /app/work/scripts && ls /app/work/scripts

# 步骤 1：准备（退出码 2 = 输入损坏，input_error 骨架已写，结束）
python3 /app/work/scripts/review_loop.py prepare --case /input/case.json --work /app/work --out /app/output

# 步骤 2：通读 /input/case.json 全部段落，按草稿模板写 /app/work/drafts/Q*.md
#   CLAIM reported|inferred | 中文论断 | P段号 "逐字引文" ; ...
#   NOTE | 缺口 | 原因 | 已核对: P1,P3

# 步骤 3：对抗审核
python3 /app/work/scripts/review_loop.py audit --work /app/work
#   读 /app/work/audit.md：凡 REVISE / UNSUPPORTED 按原因修订草稿，重跑 audit。

# 步骤 4：渲染交付（只有 pass 的论断进 result.json；未过审的机械降级）
python3 /app/work/scripts/review_loop.py render --work /app/work \
    --out /app/output --legacy /app/answers.json
```

## 3. 五路证伪规则（详见 references/audit-rules.md）

| 规则 | 证伪内容 | 命中后 |
|-|-|-|
| F1 | 引文逐字（空白归一化） | UNSUPPORTED |
| F2 | 论断中每个数值都必须出现在引文中 | REVISE |
| F3 | 引文含否定/转折词（not/however/failed to…）而论断未体现 | REVISE |
| F4 | 论断含比较措辞（更高/优于/倍…）但引文中不同取值不足两个 | REVISE |
| F5 | 论断含数值但引文中无单位 | WARN（不阻断，人工确认） |

渲染器的状态推导：`claims 全 pass 且无缺口 → answered`；
`有 pass 论断但有降级条目 → partial`；`无论断但 NOTE 通过 → insufficient_evidence`；
顶层 `completed` 要求所有问题 ∈ {answered, insufficient_evidence}。

## 4. 预算与降级

- 审核与渲染是脚本，不占模型预算；模型预算只花在读、写、改上。
- 剩余预算不足一轮修订时：直接 render——已 pass 的论断照常交付，
  其余如实降级，不留空文件。

## 5. 已知限制

- 证伪是词面启发式：F3 可能误伤含 however 但不影响论断的引文（此时按
  "在论断中体现转折语境"的方式修订，而非删论断）；F4 不判断语义比较对象。
- 审核不查"引文是否真的支持论断的语义"——这是模型的责任，机器只兜底可机械判定的部分。
- 草稿格式必须严格遵守模板；格式错误的 CLAIM 行会被静默忽略并在渲染时缺席——
  render 后对 answers[].claims 数量做一次目测复核。

## 6. 资源清单

| 路径 | 作用 |
|-|-|
| `scripts/review_loop.py` | prepare / audit / render 三子命令 |
| `references/audit-rules.md` | 五路证伪的判定逻辑、误报处理与修订范式 |
| `examples/synthetic-case.json` | 合成示例输入（虚构论文，含一处摘要-正文数值冲突） |
| `examples/run-record.md` | 合成示例的两轮真实运行记录（含故障注入与修订闭环） |
| `examples/audit.synthetic.md` | 第二轮审核报告的真实输出 |
| `examples/result.synthetic.json` | 最终渲染的真实输出（9/9 论断 pass） |
| `GITHUB_URL.txt` | 本作品的 GitHub 公开链接 |
