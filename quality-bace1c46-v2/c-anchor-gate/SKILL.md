---
name: evidence-anchor-gate
description: 证据锚定与门控技能。当任务要求对文献做出逐条质量判断、且每条判断都必须有可在原文中 Ctrl-F 回溯的逐字摘录与页/段定位时使用；适用于文献研究质量评估、证据可追溯性审查、审稿式核查等需要把证据定位从"章节级"推进到"页/段/句级"并让每条引文可被机器验证的场景。触发词：证据锚定、anchor、逐字摘录、locator、quote 验证、门控、可追溯证据。
---

# evidence-anchor-gate：证据锚定与门控

## 解决什么问题

模型对文献做判断时，常见三类失真：

1. **定位太粗**：只说"见方法部分"，审稿人无法快速核对；
2. **转述冒充引文**：把"模型记得的意思"当成原文，无法 Ctrl-F 回溯；
3. **静默幻觉**：摘录是编造的，但没有任何机制拦下它。

本技能把证据定位工程化：先由**脚本**为每篇文档建立 `p<页>.¶<段>` 锚点索引，再让模型只在候选锚点窗口内做判断并给出**逐字摘录**，最后由**门控脚本**对每条判断的摘录做归一化子串匹配，给出 `verified / repaired_locator / verified_span / abstain_unverifiable / abstain_no_text_layer` 五种裁决。找不到的摘录**不会放行**，判断被降级为弃权并写明原因。本技能的重心是锚定+门控机制本身，不绑定任何特定质量评分量表。

## 适用条件

- 材料为本地 PDF / TXT / MD（或离线快照），**无实时网络**；
- 至少一篇文档具有可用文本层（纯扫描件全部进入 `abstain_no_text_layer`）；
- 判断以 JSONL 行提交，每行带逐字摘录与定位符；
- 只依赖 Python 3 标准库 + 系统 `pdftotext`（poppler）。pdftotext 缺失时 PDF 标记 `no_text_layer` 并继续，不崩溃。

## 输入契约

- 安装路径：`/skills/weekly-skill`（本 SKILL.md 所在处）。
- 输入：`/input/case.json` + `/input/task.md`。
- `case.json` 至少含 `case_id` 与 `output_contract`；文档清单必须**防御式递归发现**：在整棵 JSON 树中递归查找 `documents / papers / references / files / literature / corpus / materials` 等键；条目可能是字符串路径，也可能是含 `path / file / filename / url(本地快照) / title / id` 字段的元数据对象。找不到清单时降级为空列表并在结果中显式说明，不得猜测。
- 工作目录：`/app/work`（锚点索引、门控中间产物）。
- 交付目录：`/app/output`，必须含 `result.json`。

## 运行方式

```bash
# 1. 建索引（脚本，不耗模型预算）
python3 /skills/weekly-skill/scripts/build_index.py \
  --input-dir /input --case /input/case.json \
  --workdir /app/work --output-dir /app/output

# 2. 模型阶段：读 index.json 与 pages/*.jsonl，只在候选锚点窗口内判断，
#    输出 /app/work/judgments.jsonl，每行：
#    {"doc_id","claim_id","judgment","quote","locator","rationale"}
#    quote 必须是从该页/段文本中逐字复制的一段（可跨相邻两段）。

# 3. 门控（脚本，不耗模型预算）
python3 /skills/weekly-skill/scripts/gate.py \
  --workdir /app/work --judgments /app/work/judgments.jsonl

# 4. 组装交付
python3 /skills/weekly-skill/scripts/build_result.py \
  --workdir /app/work --output-dir /app/output --case /input/case.json
```

## 工作流（脚本建索引与门控，模型只做窗口内判断）

1. **索引**：build_index.py 发现文档 → txt/md 直接读、pdf 走 `pdftotext -layout` → 按换页符 `\f` 分页、按空行分段 → 赋锚点 `p<页>.¶<段>` → 写 `workdir/pages/<doc_id>.jsonl`（每行 `{"anchor","page","para","text"}`）与 `workdir/index.json`（文档清单、页/段数、text_layer 标志、sha256），并尽早写骨架 result.json（status=in_progress）。
2. **判断**：模型阅读 index.json 与相关页的 jsonl，**只在候选锚点窗口内**做判断，摘录必须逐字复制窗口内文本。禁止凭记忆改写。
3. **门控**：gate.py 对 quote 与段落文本做归一化（NFKC、casefold、空白折叠、断行连字符重接），子串匹配：
   - 命中声称定位符所在段 → `verified`；
   - 命中相邻两段拼接文本 → `verified_span`；
   - 在同篇文档别处命中 → `repaired_locator`，change_records 记录 old→new；
   - 全篇无命中 → `abstain_unverifiable`（写明原因，**不放行**）；
   - 文档无文本层 → `abstain_no_text_layer`。
4. **组装**：build_result.py 汇总为 result.json 与 evidence_table.md。

## 预算分配

- 上限 **64 次模型请求、900 秒**。脚本步骤（索引/门控/组装）不占模型请求。
- 建议：发现与计划 ≤4 次；通读索引与选候选窗口 ≤12 次；逐条判断 ≤40 次；自检与修补 ≤8 次。
- **尽早**写出骨架但合法的 result.json（build_index.py 已自动写一个 in_progress 骨架），此后每次模型阶段结束都刷新它；预算耗尽时保证已有产物可交付。

## 异常处理

| 异常 | 处理 |
|---|---|
| PDF 无文本层 / pdftotext 输出为空 | 标记 `no_text_layer`，该文档所有判断 → `abstain_no_text_layer`，继续其他文档 |
| 纯扫描件 | 同上；不做 OCR（离线、无依赖保证），在 uncertainties 中说明 |
| 摘录拼接跨段 | gate 自动尝试相邻两段拼接匹配，命中记 `verified_span` |
| 图表/公式不可解析 | 对应判断弃权（`abstain_unverifiable`，reason 注明 figure/table unparseable），不得编造 |
| 文档清单缺失/为空 |  honest partial：status=partial，limits 写明，exit 0 不崩溃 |
| judgments.jsonl 行格式错误 | gate 列出所有坏行并以 exit 1 结束；坏行不进 result.json |
| 文档路径不存在 | index 中标记 missing，继续其余文档 |

## result.json 契约

顶层字段：

- `case_id`：取自 case.json；
- **output_contract 镜像**：对 case.json 中 `output_contract` 声明的每个字段做防御式递归查找并镜像其值/占位；未声明则省略；声明了但无值的填 null 并在 uncertainties 说明；
- `status`：`success | partial | failed`。规则：≥1 条 verified 锚定且无畸形输入 → `success`；全部弃权 → `partial`（limits 说明）；无任何文档 → `partial`（explanation 说明）；脚本级致命错误 → `failed`；
- `evidence_records`：仅含 `verified / repaired_locator / verified_span` 行，每条带 quote + 最终定位符；
- `abstentions`：每条弃权显式列出并附 reason；
- `anchor_coverage`：每篇文档的已索引段落数与已锚定判断数；
- `uncertainties`：自由文本列表（无文本层、图表不可解析、契约字段缺失等）；
- `change_records`：所有定位修复（old_locator → new_locator）与状态迁移记录。

细节见 `references/anchoring.md`（锚点语法、归一化规则、匹配算法、四种门控裁决与弃权规则）。
