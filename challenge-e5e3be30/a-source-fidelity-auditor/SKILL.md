---
name: source-fidelity-auditor
description: 文献证据溯源与事实核验 Skill（重心：上游数据真实性 / 原文保真机检）。适用于给定论文（PDF 或纯文本）与待核验论断清单、需要把每条结论落到原文证据并保证 quote 真实存在的核验任务：加载后用确定性脚本对全部 evidence quote 做归一化子串/模糊匹配机检与数值漂移比对，编造引用、页码漂移、四舍五入改写一律拦截、修复或降级并留痕，最终交付满足 output_contract 的 result.json。不适用于：论文材料完全无法访问（无 PDF 无文本且无 OCR 条件）时的强行判读、非证据引用类任务（如纯翻译、纯摘要）、以及不需要引用原文 quote 的开放性问答。
---

# source-fidelity-auditor：引文保真机检驱动的文献证据溯源与事实核验

## 0. 一句话定位

模型最常在"证据引用"上造假或漂移——引用原文不存在的句子、页码标错、数值被
四舍五入改写、把转引当本文结果。本 Skill 把**保真机检**设为硬门：任何 evidence
quote 进入最终结果前必须通过确定性脚本的机检，不过门的必须**修复、降级或剔除**
并写入 change_records。判定与拆解规则保持简明（见
`references/fidelity-rules.md`），工程深度集中在保真门。

## 1. 何时使用 / 何时不使用

**使用（触发条件）**
- 任务给出科研论文材料与待核验论断（问题，不是权威事实），要求判断支持度
  （supported / partially_supported / contradicted / insufficient_evidence）。
- 任务要求"给出依据/证据/定位"，即结果中会出现 quote + 页码 形式的引用。
- 需要复核已有证据卡片或引用核验清单的真实性。

**不使用（拒绝场景）**
- 输入中没有可访问的论文材料，或用户只需要翻译、摘要、改写而不需要原文证据。
- 论断属于本材料完全无关的领域且用户明确不要求核验（引导用户回到核验意图）。
- 纯扫描 PDF 且无 OCR 工具（见 §7 异常处理表，此时 status=cannot_determine，
  而不是编造证据）。

## 2. 评测运行契约（必读）

- 评测方把本 Skill 安装到 `/skills/weekly-skill`，用官方 DeepSeek Harness 在
  3 个固定案例上运行加载了本 Skill 的 Agent。
- 输入在 `/input/`：`case.json`（含 `case_id` 与 `output_contract` 字段清单）、
  `task.md`、`claims-to-verify.json`（论断是**待核验的问题**）、论文 PDF
  （可能有扫描件、无文本层）、`environment/resources.yaml`（可用工具清单，若有）。
- 工作目录 `/app/work`；最终成果放 `/app/output`，其中必须有 `result.json`：
  包含 `case_id` 与 `output_contract` 的**全部字段**，诚实的
  `status`（success / partial / cannot_determine / refused），以及
  `sources`、`uncertainty`、`change_records`。
- 预算：**64 次模型请求 / 900 秒 / 每响应 16384 tokens**。脚本能做的事
  绝不花模型请求；先写骨架 result.json（status=partial）再增量覆写。
- 四级支持度判定：supported / partially_supported / contradicted /
  insufficient_evidence。主题相关≠支持；未报告≠反驳（unsupported
  extrapolation 属 insufficient_evidence，不是 contradicted）；冲突来源要
  并列双方原话与定位。
- 不得预制答案、不得依据材料标签臆造数据；一切以 `/input/` 实际文件为准。

## 3. 路径与依赖

- 评测时 Skill 根为 `/skills/weekly-skill`。若当前环境不同，先定位：
  `find / -maxdepth 4 -name quote_audit.py 2>/dev/null` 或直接把
  `<skill>/scripts/*.py` 复制到 `/app/work/` 后运行（脚本均为
  **Python 3 纯标准库**，单文件可独立执行）。
- 外部命令仅一个：`pdftotext`（Poppler，PDF 抽取用）。缺失时自动降级为
  只支持 `.txt` 输入并给出清晰报错（exit 1），不静默失败。
- 脚本调用一律写作 `<skill>/scripts/xxx.py`；三个脚本均支持
  `--help`，退出码语义统一：**0 通过 / 1 有失败项或运行错误 / 2 用法错误**。

## 4. 输入盘点（第一个动作，零模型成本）

在 `/app/work` 下用脚本与 shell 完成（不花模型请求）：

```bash
ls -la /input/ /input/environment/ 2>/dev/null
cat /input/case.json        # 记录 case_id、output_contract.fields
cat /input/task.md
head -c 4000 /input/claims-to-verify.json
cat /input/environment/resources.yaml 2>/dev/null
ls /input/*.pdf /input/*.txt 2>/dev/null
```

盘点结论记入 `/app/output/change_records` 的第一步：有哪些材料、格式、
是否有文本层线索（文件大小异常小、resources.yaml 未列 OCR 工具等）。

## 5. 预算与增量保存策略

1. 全流程中模型请求只用于：读论文关键段落、做论断拆解与支持度语义判定、
   撰写 rationale。**检索、匹配、数值比对、页码核对全部交给脚本**。
2. 流水线启动后立即写 `/app/output/result.json` 骨架：
   `case_id` 照抄，`status: "partial"`，output_contract 每个字段给占位值
   （空列表/空字符串），`change_records` 记第一步。
3. 每完成一个阶段（抽取完成、判定完成、保真门通过）就**原子覆写**
   `result.json`（先写临时文件再 `mv`），并在 `change_records` 追加一条。
   任何中途失败都留有可用的部分结果，绝不让 result.json 处于缺字段状态。
4. 时刻估算剩余请求数：单次阶段超过约 8 次请求仍未收敛时，立即固化当前
   部分结果并降级 status。

## 6. 端到端流水线

```
输入盘点(§4) → 骨架 result.json(§5) → [1] 抽取 → [2] 拆解 → [3] 定位与判定
→ [4] 保真门(★核心) → [5] 修复-降级-剔除循环 → [6] 产出与自查
```

### 步骤 1：抽取分页文本（脚本）

```bash
python3 <skill>/scripts/extract_pages.py \
  --input /input/<论文>.pdf --output /app/work/pages.jsonl
```

- PDF：`pdftotext -layout`，按 `\f` 分页；`.txt`：按 `=== PAGE n ===` 标记或
  每 ~3000 字符虚拟分页。
- 产物每行 `{"page": n, "chars": m, "text": "..."}`；`chars<50` 的页标
  `suspect_scan: true`；页眉页脚正则猜测的印刷页码写入 `printed_page`
  与 `header_lines/footer_lines`。
- 若 `suspect_scan` 页占比高 → 触发 §7 异常处理"PDF 无文本层"。

### 步骤 2：论断拆解（简明规则）

按 fact / comparison / causal / scope 拆子判断，保留比较词、否定词、
限定条件（温度、压力、样本、时间窗）；逐条子判断列出所需证据类型。
细则见 `references/fidelity-rules.md` §4。

### 步骤 3：证据定位与判定（简明规则）

- 在 pages.jsonl 中检索关键词定位候选段落，**逐字复制原文**为 quote
  （保留原始标点、全角字符、换行位置），标注物理页 `page`（必要时对照
  `printed_page`）。
- 支持度判定细则见 `references/fidelity-rules.md` §3：四级定义、
  "主题相关≠支持"、"未报告≠反驳"、冲突双方原话并列。
- 每条 evidence 条目按 `templates/evidence-entry.json` 填写。

### 步骤 4：保真门（★本 Skill 的核心，脚本执行，零模型成本）

```bash
python3 <skill>/scripts/quote_audit.py \
  --result /app/output/result.json --pages /app/work/pages.jsonl \
  --output /app/work/fidelity-report.json

python3 <skill>/scripts/num_drift.py \
  --claims /input/claims-to-verify.json --result /app/output/result.json \
  --output /app/work/num-drift.json
```

- `quote_audit.py`：对每条 quote 做 NFKC 归一化、弯引号→直引号、跨行连字符
  拼接、空白折叠后的**子串匹配**；失败则用 `difflib.SequenceMatcher` 做
  页内最佳模糊匹配并报告 ratio：`≥0.95` → verbatim_ok（标注 normalized）；
  `0.80–0.95` → near_match（警告，需人工）；`<0.80` → not_found（ERROR）。
  同时核对标注页 vs 实际命中页，不符报 page_drift（ERROR）。
  任何 not_found / page_drift → 脚本 exit 1，门未通过。
- `num_drift.py`：抽取论断与 quote 中的全部数值（百分数、小数、科学计数、
  中文数字"百分之三十"），按等价规则（`30% ≡ 0.3 ≡ 30 percent`）比对；
  缺失或数值不一致输出 drift 清单（exit 1）。这是"判定前自查论断数字是否
  被原文支持"的机检。
- 归一化逐项定义见 `references/normalization-spec.md`。

### 步骤 5：修复–降级–剔除循环

按 `references/fidelity-rules.md` §2 处置矩阵执行，每次处置写入
`change_records`（时间、条目、原值、新值、机检项名）。常见循环：

1. not_found → 回 pages.jsonl 重新检索正确原文 → 替换 quote → 重跑保真门；
2. 找不到真实出处 → 剔除该证据，对应论断降级为 insufficient_evidence；
3. value_mismatch → 论断数值改回原文值，或在 uncertainty 中显式说明
   "论断写 78.2%，原文为 78%"；
4. page_drift → 以实际命中页更正 page。
循环直至 `quote_audit.py` exit 0 且 `num_drift.py` 的 drift 项全部得到
处置（修复或如实降级并在 uncertainty 留痕）。

### 步骤 6：产出与自查

按 §8 自查清单逐项核对后，将 `status` 从 partial 覆写为最终诚实值
（保真门未全过但有处置留痕 → partial；材料无法支撑任何判定 →
cannot_determine）。`result.json` 放 `/app/output/`。

## 7. 异常处理表

| 异常场景 | 识别信号 | 处置 | status 建议 |
|---|---|---|---|
| PDF 无文本层（扫描件） | extract_pages 输出 `suspect_scan` 页占比高；pdftotext 产出空文本 | 查 resources.yaml 是否有 OCR 工具；有则 OCR 后按 .txt 流程；无则在 uncertainty 明示"该页证据无法机检"，仅对已抽取页做核验 | partial |
| pdftotext 缺失 | extract_pages exit 1 且 stderr 提示 Poppler 缺失 | 改用 .txt 材料；无 .txt 则无法抽取，如实报告 | cannot_determine |
| 定位失败（关键词无候选段落） | pages.jsonl 全文检索无命中 | 换同义/英文术语重检；仍无 → 该子判断 insufficient_evidence，**不**编造 quote | partial |
| 证据互相冲突 | 两条 verbatim_ok 证据对同一子判断给出矛盾数值/结论 | 并列双方原话+页码，verdict 给出 qualified 结论（如 partially_supported 并注明冲突），写入 uncertainty | partial |
| 材料缺失（case 引用文件不存在） | §4 盘点发现 | result.json 照常交付，缺失材料写入 uncertainty 与 change_records | partial / cannot_determine |
| quote 无法修复（not_found 且原文确无） | 保真门循环两轮仍 not_found | 剔除该证据并降级论断，留痕；禁止保留 | partial |
| 输出契约字段与证据结构冲突 | case.json output_contract 字段缺失于模板 | 以 output_contract 为准扩展字段，不删字段 | 按实际 |
| 预算耗尽 | 请求计数接近 64 | 立即固化当前 result.json，status=partial，change_records 说明中断点 | partial |

## 8. 输出契约自查清单（交付前逐项确认）

- [ ] `case_id` 与 `/input/case.json` 完全一致。
- [ ] `output_contract` 中**每个字段**均存在（骨架阶段也不缺字段）。
- [ ] `status` 为四级诚实值之一，且与保真门结果一致（门未全过 → 不得写 success）。
- [ ] `evidence` 中每条 quote 均为**原文逐字复制**，且 `quote_audit.py` 最近一次运行 exit 0。
- [ ] 每条 evidence 含 `page`（或 `printed_page`）定位；跨页证据逐页标注。
- [ ] `num_drift.py` 的 drift 项已全部修复或在 `uncertainty` 中如实说明。
- [ ] 四级支持度判定符合 `references/fidelity-rules.md` §3：无"主题相关当支持"，
  无"未报告当反驳"。
- [ ] 冲突来源（若有）并列双方原话与定位。
- [ ] `sources` 列出实际使用的材料文件与页范围；`uncertainty` 写明残余不确定
  （扫描页、归一化不可区分的字形、near_match 待人工项）。
- [ ] `change_records` 覆盖：骨架写入、每次机检结果、每次修复/降级/剔除、
  status 变更。

## 9. 文件清单

```
SKILL.md                            本文件
scripts/extract_pages.py            PDF/txt → pages.jsonl（分页文本层 + 印刷页码猜测）
scripts/quote_audit.py              引文保真机检（核心保真门）
scripts/num_drift.py                数值漂移检查
references/fidelity-rules.md        保真判定规则（机检项定义、处置矩阵、判定/拆解简明规则）
references/normalization-spec.md    归一化规范（文本 + 数值等价）
templates/evidence-entry.json       证据条目模板
examples/                           合成示例（paper.txt / claims.json / case.json /
                                    run_example.sh / EXPECTED.md），EXPECTED.md
                                    记录了端到端实测的退出码状态
```

## 10. 限制与维护

- 机检只能证明"quote 存在于原文"，不能证明"判定正确"——语义判定仍由模型
  完成，near_match 与 near-threshold 案例保留人工核对通道。
- 模糊匹配阈值 0.95/0.80 是合成示例上调校的经验值；对高度模板化文本
  （如公式密集论文）可能出现 near_match 偏严，可在 change_records 中记录
  并按 fidelity-rules.md 的处置矩阵人工放行。
- 扫描件、双栏复杂版式的印刷页码猜测可能失败；物理页 `page` 永远是主键，
  `printed_page` 仅为辅助。
- 维护：脚本阈值与规则文件同源更新；修改脚本后必须重跑
  `examples/run_example.sh` 并更新 `examples/EXPECTED.md` 的实测状态。
