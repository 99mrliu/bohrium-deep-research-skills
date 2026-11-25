---
name: evidence-offset-verifier
description: 文献筛选任务的可解释性工程与反编造校验引擎。每条筛选决定必须携带逐字证据引文，并由脚本把引文锚定到该记录自身标题或摘要的字符偏移区间；校验器逐条重算锚点，编造或错引的"证据"一律进入拒绝登记簿并自动降级为 pending，无法以任何标签幸存。交付物是经核验的理由卡片与 result.json，而不是裸标签。当任务要求可复核、反编造的文献筛选与排序交付时使用。
---

# evidence-offset-verifier

## 用途与重心

本 Skill 的重心是**可解释性工程与反编造校验**：筛选结论的价值不在标签，而在可被独立重算的理由。每条决定必须附 `evidence_quote`——该记录标题或摘要中的逐字子串；脚本将其锚定为 `{field, start, end, surface_form}` 字符偏移对象，validate 子命令再从 result.json 反向重算每一个锚点（`surface_form` 必须等于源字段切片 `[start:end]`）。定位失败的引文进入 `rejected_register`（附 difflib 最近邻匹配供一次修复），其决定**无条件降级为 pending**，理由是 "evidence anchor failed verification"——证据无法核验的决定绝不保留原标签。模型只在一次批量调用中产出判定与引文，其余全部由确定性脚本保证。

## 适用条件

- 输入为 `/input/case.json`（固定研究问题、实际查询输入、约 9 条真实署名文献的有限快照；部分案例含以 `fixture_note` 等字段显式标注的合成重复导出/冲突观点夹具——仅可作 provenance 引用，绝不可当作预期答案）与 `/input/task.md`。
- 要求**全记录筛选**：每条输入记录恰好出现在输出中一次；判不了的一律 `pending`，不得编造。
- 平台运行契约：在 `/app/work` 下工作，最终 `/app/output/result.json` 必须回显 `case_id` 并含 `output_contract` 声明的全部字段；部分完成必须显式标注 honest partial。

## 运行契约与预算纪律（64 次模型请求 / 900 秒）

模型调用 **≤2 次**（1 次批量判定 + 至多 1 次引文修复），其余全为脚本；任何一步失败都跳到第 4 步交付诚实 partial。

1. **锚定（脚本，无模型调用）**：先由 Agent 读取 case.json 与 task.md，在**唯一一次批量模型调用**中对全部记录一次性输出 `/app/work/decisions.json`（格式：`{"decisions":[{"record_id","label"∈{keep,pending,exclude},"relevance"∈{direct,indirect,none},"confidence"∈[0,1],"criterion_hit","evidence_quote"}]}`，`evidence_quote` 必须是该记录标题或摘要的**逐字子串**，禁止改写、翻译、拼接）。然后：
   `python3 /skills/weekly-skill/scripts/evidence_engine.py anchor --case /input/case.json --decisions /app/work/decisions.json --out /app/work/anchored.json`
   检查 anchored.json 的 `rejected_register`：若为空直接进入第 3 步；若非空，可用**第二次（也是最后一次）模型调用**按 `nearest_match` 提示修复引文后重跑本步——只允许修改 `evidence_quote`，不得为提高 verification_rate 而改标签规避降级。
2. **卡片与装配（脚本）**：
   `python3 /skills/weekly-skill/scripts/evidence_engine.py cards --case /input/case.json --anchored /app/work/anchored.json --out /app/output/result.json --cards-md /app/output/rationale_cards.md`
   脚本完成：确定性排序（label 层级 keep<pending<exclude → confidence 降序 → record_id）、逐记录理由卡片（锚定引文 + 偏移 + 源字段 ±40 字符上下文 + 核验状态）、`verification_report`、契约字段镜像——不可产出的字段以显式 `null` + `status.incomplete` 说明，绝不静默丢弃。
3. **交付校验（脚本）**：
   `python3 /skills/weekly-skill/scripts/evidence_engine.py validate --case /input/case.json --result /app/output/result.json`
   validate 会**重算每一个锚点**：任何 `surface_form` 与源字段切片不符即 FAIL（退出码 1）。FAIL 时按打印清单修复后重跑第 1–2 步；PASS 才视为可交付。
4. **退化路径（脚本-only，诚实 partial）**：时间不足或模型预算耗尽时，省略 decisions：
   `python3 /skills/weekly-skill/scripts/evidence_engine.py anchor --case /input/case.json --out /app/work/anchored.json`
   全部记录 pending（"not judged"），`verification_rate=0.0`，`status.state=partial`，validate 仍 PASS——partial 是合法交付态，先保底再改进。

## 输入与输出

- 输入：`/input/case.json`、`/input/task.md`；中间物：`/app/work/decisions.json`（Agent 写）、`/app/work/anchored.json`。
- 输出：`/app/output/result.json`（`case_id`、`screened_records`（含 label/relevance/confidence/criterion_hit/evidence 锚点对象）、`ranking`、`verification_report{total_decisions, anchors_verified, anchors_rejected, verification_rate, downgrades}`、`rejected_register`、`summary`、`status{state,completed,incomplete,limits}`、`uncertainty`、`change_records`，以及契约声明的每个其他字段）与 `/app/output/rationale_cards.md`（经核验的理由卡片，本 Skill 的核心交付物）。
- 锚定规则细节见 `references/anchoring-spec.md`。

## 异常处理

- case.json / decisions.json 无法解析 → 脚本以退出码 2 终止并说明，不猜测、不补造。
- `evidence_quote` 无法定位（含空串、非字符串）→ 进入 `rejected_register`（附最近邻匹配 ratio 与实际子串），决定降级为 pending。
- decisions 缺失或 record_id 不在候选池 / 重复决定 → 记录为 pending "not judged" 或拒绝登记，绝不把未知决定安到记录上。
- 契约字段不可产出 → 显式 `null` + `status.incomplete`；`status.state=complete` 当且仅当全部已发出决定 verification_rate==1.0、无未判定记录、无未填契约字段。
- `fixture_note` 等夹具标注仅作 provenance 引用，绝不作为判定的 ground truth。

## 方法说明与限制

- 排序与锚定是确定性的：同一 decisions.json 必得同一 result.json，任何第三方可用 validate 独立重算复核。
- 反编造保证是**机械性**的：脚本只核验"引文是否逐字存在于该记录标题/摘要及偏移是否正确"，不核验判据语义是否成立——语义质量取决于批量判定调用。
- 限制：证据来源仅限标题与摘要（无全文可得），间接相关可能被高估或低估，已在 `uncertainty` 中声明；白空白归一化回退仅容忍空白差异，不容忍任何字符级改写。
- 自查方法：validate PASS 且打印的 `verification_rate` 与 `status.state` 符合预期（全部引文核验通过且无未判定记录时应为 1.0000 + complete）；`rationale_cards.md` 中每条引文的 ±40 字符上下文可人工抽读核对。完整可运行示例见 `examples/minimal/`（合成示例，不冒充正式案例结果）。
