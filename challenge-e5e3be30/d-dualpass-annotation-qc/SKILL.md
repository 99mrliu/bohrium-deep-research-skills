---
name: dualpass-annotation-qc
description: 文献证据溯源与事实核验的过程质量控制 Skill。当任务要求对一组论断（claims）逐条对照论文原文给出 supported / partially_supported / contradicted / insufficient_evidence 四级判定，并要求判定可信度可度量（而非仅声明）时使用：对同一批论断做双通道独立标注（Pass A 正常顺序、Pass B 逆序换检索起点），用 Cohen's kappa 与定位一致率度量通道间一致性，再按公开仲裁规则保守合并分歧。尤其适用于评测环境（如 challenge-e5e3be30，skill 根为 /skills/weekly-skill）中需要可复用标注资产与诚实质量报告的场景。不适用于：单纯翻译/摘要、无原文可对照的创作任务、论断数极少（<3）且预算不足以支撑双通道的情形。
---

# 双通道标注质控：文献证据溯源与事实核验

## 核心理念

单次通过的核验没有质量仪表。本 Skill 把标注研究（annotation study）的标准做法移植到 Agent 核验：

1. **双通道独立标注**：同一论断由两个互不参照的通道独立给出判定与证据定位，防锚定；
2. **一致性度量**：用 Cohen's kappa 与定位一致率**度量**判定可信度，低一致性必须在 result.json 如实报告；
3. **仲裁协议**：分歧项按公开规则取保守默认，模型只在仲裁环节复核证据，不得直接改结论；
4. **可复用资产**：标注规范、仲裁协议、批量核验清单可脱离本 Skill 独立复用复跑。

## 何时使用 / 何时不使用

**使用**：输入含一组待核验论断 + 可检索的论文原文；任务要求输出逐条判定与证据来源；预算允许至少两遍有限的原文接触。

**不使用**：
- 论断数 < 3 且无法证明双通道开销合理（kappa 在极小样本上不稳定，度量无意义，应如实说明）；
- 论文原文不可获取（无 PDF、无文本提取通道）——此时所有论断只能判 insufficient_evidence，双通道退化为形式；
- 预算耗尽风险高到连单通道都难完成——直接走"诚实降级"路径（见异常处理表），不要启动双通道后烂尾。

## 评测运行契约（必须遵守）

评测方把本 Skill 安装到 `/skills/weekly-skill`，用官方 DeepSeek Harness 在 3 个固定案例上运行加载了该 Skill 的 Agent。运行时：

- 输入在 `/input/`：`case.json`（含 case_id 与 output_contract）、`task.md`、`claims-to-verify.json`（**论断是待核验的问题，不是权威事实**）、论文 PDF、`environment/resources.yaml`（若有）。
- 工作目录 `/app/work`；最终成果 `/app/output`，必须有 `result.json`：case_id + output_contract 全部字段 + 诚实 status + sources + uncertainty + change_records。
- 预算 **64 请求 / 900s / 16k tokens 每响应**。
- 四级判定：supported / partially_supported / contradicted / insufficient_evidence；**主题相关 ≠ 支持；未报告 ≠ 反驳；冲突并列双方原话**。
- 下文脚本路径一律写 `<skill>/scripts/xxx.py`，评测时 `<skill>` = `/skills/weekly-skill`。

## 标准流水线

### 第 0 步：输入盘点（1–2 个请求）

1. 读 `/input/case.json` 与 `task.md`，记录 case_id 与 output_contract 字段清单；
2. 读 `claims-to-verify.json`，统计论断条数 N；
3. 提取论文 PDF 全文为纯文本（pdftotext 或 Python），按页切分，建立**页码 → 原文段落**索引，保存为 `/app/work/paper_pages.json`。**该索引只建一次，两个通道复用**——这是 Pass B 低成本设计的关键；
4. 若 PDF 提取失败：所有论断判 insufficient_evidence，status 记 partial，uncertainty 说明原因，直接跳到产出步。

### 第 1 步：写骨架 result.json（partial）（第 1 个产出请求）

在深入核验**之前**，先写 `/app/output/result.json` 骨架：case_id、output_contract 全部字段（空值/占位）、status="partial"、sources=[]、uncertainty="核验进行中"、change_records=[{初始骨架}]。此后每完成一个阶段**增量覆写**同一文件，确保任何时刻中断都有诚实产物。

### 第 2 步：Pass A 标注（正常顺序）

- 按 claims 原始顺序 C1→CN 逐条核验；
- 每条论断：在页码索引中定位相关段落（先关键词检索，再上下文精读），按 `references/annotation-spec.md` 的操作定义给出四级判定、evidence_pages（页码数组）、evidence_quote（原文引句，≤80 词）、rationale（≤50 字）；
- 产出 `/app/work/passA.json`，格式见 `templates/annotation-pass.json`；
- **请求预算提示**：N ≤ 10 时可每 2–3 条论断一个响应；不要逐条逐页单独发请求。

### 第 3 步：Pass B 标注（逆序 + 换检索起点，低成本）

Pass B 的目的不是重做 Pass A，而是提供一个**独立第二判**，开销必须显著低于 Pass A：

- **复用**第 0 步的 `paper_pages.json` 索引，不重新解析 PDF；
- 按 **CN→C1 逆序**处理，检索起点与 Pass A 不同（Pass A 从关键词命中页起步，Pass B 从摘要/结论/图表说明反向追溯）；
- 不看 Pass A 的任何判定与引句（防锚定）；
- **第二遍只重看分歧高风险项的原文**：对事实型论断（含具体数值/样本量/统计量）精读核对，对显然无原文依据的论断快速判 insufficient_evidence，不做全文重来；
- 产出 `/app/work/passB.json`，格式同 Pass A。

### 第 4 步：一致性度量（本地脚本，零请求）

```bash
python3 <skill>/scripts/agreement.py /app/work/passA.json /app/work/passB.json \
    -o /app/work/agreement-report.json
```

脚本计算：verdict 的 Cohen's kappa（含观测/期望一致率）、定位一致率（每条论断两通道页码集合的 Jaccard 均值与"至少一页精确重合"比例）、逐条分歧表。kappa < 0.6 时脚本打印质量警告（仍 exit 0）。

### 第 5 步：仲裁（本地脚本，零请求；仅分歧项允许复核原文）

```bash
python3 <skill>/scripts/adjudicate.py /app/work/passA.json /app/work/passB.json \
    /app/work/agreement-report.json -o /app/work/adjudicated.json --log /app/work/adjudication-log.md
```

仲裁规则（详见 `references/adjudication-protocol.md`）：

- 两通道 verdict 一致 → 直接采纳；页码不一致 → 采纳 verdict 但 needs_review=true（理由 location_divergence），页码取并集；
- {supported, partially_supported} → 降 partially_supported；
- {supported, insufficient_evidence} → 降 partially_supported；
- {partially_supported, insufficient_evidence} → 降 insufficient_evidence；
- contradicted 与其他任何判定分歧 → provisional=partially_supported + conflict=true，**双方原话并列**，不强行选边；
- 所有分歧项标记 needs_review=true 并附仲裁理由。

模型在仲裁环节**只允许**针对 needs_review 项回查原文以补充证据定位，**不得绕过脚本直接改最终判定**；若回查后确有依据推翻保守默认，须在 change_records 记录理由，且 result.json 中该论断保留 conflict 标记。

### 第 6 步：产出与自查

1. 把 adjudicated.json 的最终判定映射进 `/app/output/result.json` 的 output_contract 字段；
2. sources：每条 supported/partially_supported/contradicted 论断附页码与引句；
3. uncertainty：**必须包含** kappa 值、定位一致率、needs_review 条数；kappa < 0.6 必须明确写"双通道一致性低，判定标准不稳定，结论可信度受限"；
4. status：全部论断有最终判定且 kappa ≥ 0.6 → "success"；存在 needs_review 或低 kappa → "partial"（诚实优先）；
5. change_records：追加骨架→Pass A→Pass B→度量→仲裁→终稿各节点；
6. 运行输出契约自查清单（见下节），逐项核对后结束。

## 输出契约自查清单

- [ ] result.json 存在于 /app/output 且为合法 JSON；
- [ ] case_id 与 /input/case.json 完全一致；
- [ ] output_contract 声明的**每一个字段**都存在（无遗漏、无多余拼写变体）；
- [ ] 每条论断的判定 ∈ {supported, partially_supported, contradicted, insufficient_evidence}；
- [ ] status 诚实：有 needs_review / 低 kappa / 预算降级时不得写 success；
- [ ] sources 非空（有支持/反驳证据的论断均有页码+引句）；
- [ ] uncertainty 含 kappa、定位一致率、needs_review 计数；
- [ ] change_records 按时间顺序记录全部阶段；
- [ ] agreement-report.json、adjudication-log.md 作为质控工件保留在 /app/work 或随产出提交（若契约允许）。

## 预算与增量保存策略

| 阶段 | 请求预算参考（N≈10 论断） |
|---|---|
| 输入盘点 + PDF 索引 | 2–4 |
| 骨架 result.json | 1 |
| Pass A | 6–10 |
| Pass B（复用索引，逆序轻量） | 3–6 |
| agreement + adjudicate（脚本） | 0 |
| 仲裁复核（仅分歧项） | 0–3 |
| 终稿覆写 + 自查 | 2–3 |

硬性纪律：
- 每完成一个阶段立即增量覆写 result.json；
- Pass B 禁止重新解析 PDF、禁止重读 Pass A 输出；
- 剩余请求 < 8 时停止 Pass B 精查，已标部分照常度量，未标部分走诚实降级；
- 单响应接近 16k tokens 时先落盘 work 文件再续写。

## 异常处理表

| 异常 | 处理 |
|---|---|
| PDF 无法提取文本 | 全部判 insufficient_evidence；status=partial；uncertainty 说明提取失败；不再启动双通道 |
| 单通道预算耗尽（Pass A 未完成） | 已标论断照常出判定；未标论断判 insufficient_evidence 并在 uncertainty 注明"单通道预算耗尽"；status=partial；**不得**伪造 Pass B |
| Pass B 预算耗尽 | 只完成单通道：kappa 不可计算，uncertainty 必须写明"仅完成单通道，无一致性度量，判定未经交叉验证"；status=partial |
| 论断数 N < 3 | 可跑双通道但 kappa 无统计意义；uncertainty 注明样本过小 |
| kappa < 0.6 | 脚本警告；result.json 照常产出但 status ≤ partial，uncertainty 如实报告低一致性；仲裁结果全部保留 needs_review |
| claims JSON 格式损坏 | 尽量解析可读部分；无法解析时 status=failed 并说明 |
| 脚本 schema 报错（exit 1） | 按报错字段修正标注 JSON 后重跑；不得跳过度量直接手填 kappa |
| 两通道 claim_id 集合不一致 | agreement.py 报错退出；对齐 claim_id 后重跑 |

## 交付物结构

```
SKILL.md                          # 本文件
scripts/agreement.py              # Cohen's kappa + 定位一致率 + 逐条分歧清单
scripts/adjudicate.py             # 双通道保守合并 + 仲裁日志
scripts/checklist.py              # claims → 可勾选批量核验清单（CSV + Markdown）
references/annotation-spec.md     # 标注规范：四级判定操作定义、定位格式、边界情形
references/adjudication-protocol.md # 仲裁协议与保守默认规则
references/reuse-guide.md         # 复用指南：把本套规范用于其他批量核验任务
templates/annotation-pass.json    # 单通道标注记录模板
examples/                         # 合成示例（paper.txt 为虚构论文，passA/passB 为演示输入）
GITHUB_URL.txt
```

## 可复用资产说明

`references/annotation-spec.md` 与 `references/adjudication-protocol.md` 不依赖本 Skill 的其余部分，可直接拷贝到其他核验项目；`scripts/checklist.py` 把任意 claims 列表转成可勾选的 CSV/Markdown 清单，供人工复核或他 Agent 复跑。复用方法见 `references/reuse-guide.md`。
