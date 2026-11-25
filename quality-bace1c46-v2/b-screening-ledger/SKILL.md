---
name: screening-decision-ledger
description: >-
  科研文献检索与筛选过程的质量审计技能。当任务要求“找到文献，也保留筛选依据”、
  要求 PRISMA-2020 风格流程计数、要求每条纳入/排除决定都带有标准条款编号、
  理由与可被机器核验的原文证据引句（quote 必须能在该候选条目自身的标题/摘要中
  逐字找到）、需要去重合并记录、空缺/零结果也必须显式声明时使用。适用于输入为
  离线快照（Crossref/EuropePMC 快照、引用图谱、导入状态列表）且无网络的评测环境。
  不用于实时联网检索、不用于“最新进展/新颖性”断言。
---

# screening-decision-ledger（筛选决定台账）

## 解决什么问题

把“检索—去重—筛选—排序—流程计数”这一**过程**本身变成一等交付物：

- 从案例中收割候选文献台账（候选可能藏在任意键下），不臆造任何候选；
- 去重并留下合并记录（谁被吸收进谁、依据什么键）；
- 每条筛选决定（include / exclude / uncertain）都必须携带：标准条款 id + 中文理由 +
  **机器可核验的证据引句**（该引句经 NFKC + casefold + 空白折叠归一化后，必须是该候选
  “标题+摘要”的子串；核验不过的决定行会被拒绝并记录原因，绝不放行）；
- 生成 PRISMA-2020 风格流程计数并做算术不变量校验；
- 显式写出遗漏声明：未筛选列表、待定（uncertain）列表、零结果声明。

核心信条：**没有任何一条候选在无记录理由的情况下被排除；没有任何一条候选是被发明的。**

## 适用条件

- 评测方把本技能安装到 `/skills/weekly-skill`；
- 输入为 `/input/case.json`（案例，含候选文献快照）与 `/input/task.md`（任务说明）；
- 素材是**离线快照**（Crossref / EuropePMC 快照、引用图谱、导入状态列表等）；
- **全程无网络**：绝不发起任何 fetch / 检索请求；绝不作“最新发表”“新颖性”类断言；
- 预算：模型请求 ≤ 64 次，总时长 ≤ 900 秒。

## 输入契约

- `/input/case.json`：JSON 对象。候选列表可能出现在**任意层级、任意键名**下，常见键：
  `candidates / documents / papers / references / results / items / records`（大小写不敏感，
  递归搜索）。条目可能是纯字符串（视为标题），也可能是元数据对象（title/authors/year/doi/
  source/abstract 等字段名也可能有变体）。
- `case.json` 中可能有 `output_contract / contract / output_fields / required_fields`
  （同样递归防御式搜索），声明了 result.json 必须镜像的字段。
- `/input/task.md`：自然语言任务，可含纳入/排除口径（时间窗、语言、设计类型等）。
- 一切解析都必须防御式：结构不符时降级处理并在 notes/uncertainties 里说明，**绝不崩溃**。

## 运行方式

所有脚本仅用 Python 3 标准库。退出码约定：`0` 正常；`1` 校验/不变量失败（详见各脚本）；
`2` 用法或 IO 错误。草稿与中间产物放 `/app/work`，交付物放 `/app/output`。

```bash
W=/app/work; O=/app/output
python3 /skills/weekly-skill/scripts/init_ledger.py \
    --case /input/case.json --task /input/task.md --workdir $W --output-dir $O
# → $W/candidates.jsonl, $W/duplicates.jsonl, $W/harvest_report.json, 骨架 $O/result.json

# 模型阅读 candidates.jsonl 与 task.md 后，逐条撰写决定（见下）写入 $W/decisions.jsonl
python3 /skills/weekly-skill/scripts/apply_decisions.py --workdir $W --decisions $W/decisions.jsonl
# → $W/screening.jsonl（有效行）、$W/rejected_decisions.jsonl（被拒行+原因）

python3 /skills/weekly-skill/scripts/flow_check.py --workdir $W
# → $W/flow.json, $W/flow_report.md；不变量被违反时退出码 1

python3 /skills/weekly-skill/scripts/build_result.py --workdir $W --output-dir $O --case /input/case.json
# → $O/result.json, $O/screening_report.md
```

## 工作流（模型侧分工）

**脚本做收割与校验，模型只做筛选判断与理由。** 模型不得手写计数、不得绕过
apply_decisions.py 的引句核验。

1. **第 0 步（最先做）**：先运行 `init_ledger.py`，它会顺带在 `--output-dir` 写出一个
   **骨架但合法、诚实标注 status=in_progress 的 result.json**。之后每完成一个阶段就重建
   result.json，保证任何时刻被打断都有诚实结果。
2. **收割（脚本）**：`init_ledger.py` 递归收割候选、归一化为
   `{cand_id, title, authors, year, doi, source, abstract_snippet}`，按
   （有 doi 用 doi，否则用归一化标题；双索引下 DOI 相同**或**归一化标题相同均判重，
   以覆盖一方缺 DOI 的快照对）去重，合并记录写入 `duplicates.jsonl`。
3. **阅读（模型）**：读 `candidates.jsonl` 与 `task.md`，建立筛选口径。
4. **决定（模型）**：为每个 cand_id 写一行决定：
   `{"cand_id","decision": include|exclude|uncertain,"criterion","rationale","evidence_quote","stage"?}`。
   - `criterion` 必须来自标准目录（见 `references/screening_criteria.md`：C-POP / C-TOP /
     C-DESIGN / C-DATE / C-LANG / C-RTYPE / C-DUP / C-OTHER）；
   - `evidence_quote` 必须**逐字摘自该候选自身的标题或摘要**（标点大小写空白差异会被归一化
     容忍，但内容必须真实存在）；引不出来就先重读原文，不要编造；
   - 元数据不足以下判断时选 `uncertain`（弃权规则：宁可 uncertain，绝不猜）。
5. **应用与校验（脚本）**：`apply_decisions.py` 逐行校验：cand_id 存在、criterion 已知、
   evidence_quote 归一化后是该候选“标题+摘要”的子串。不合格行进
   `rejected_decisions.jsonl` 并给出原因——**被拒绝的行必须修正后重投**，直至没有未处理的
   候选，或显式把剩余候选写进 omissions。
6. **流程计数（脚本）**：`flow_check.py` 计算 PRISMA 风格计数并验证不变量
   （identified − duplicates = unique；screened = include + exclude + uncertain；
   每条 exclude 至少有一条 criterion），自动生成遗漏声明。退出码 1 时必须修复后重跑。
7. **组装（脚本）**：`build_result.py` 组装最终 `result.json` 与 `screening_report.md`。

## 预算分配（≤64 次模型请求 / 900 s）

- 初始化与收割：≈2 次请求（跑脚本 + 看报告）；
- 阅读候选与撰写决定：主要开销，候选多时**分批**写 decisions.jsonl（每批 10–20 条）；
- 校验—修正循环：预留 ≥3 次（被拒行修正重投）；
- 流程校验 + 组装 + 复核：≈4 次；
- 任何时候预计超预算：立即跑 `flow_check.py` + `build_result.py`，以 partial 状态交付并
  在 uncertainties/limits 中如实说明覆盖了哪些候选、哪些未完成。

## 异常处理

- **空候选集**：init 正常产出空 `candidates.jsonl`；不要编造候选。继续跑完整流水线，
  `build_result.py` 会给出 `status=partial` 并附零结果声明（检索到了 0 条、可能原因、
  建议），而不是 success。
- **全部排除**：合法结果。flow 中 included=0，result.json 的 status 仍可 success
  （前提：每条 exclude 都有 criterion + rationale + 已核验引句，且不变量通过）， omissions
  中自动出现“筛选后无纳入文献”的空结果声明。
- **决定行校验失败**：看 `rejected_decisions.jsonl` 的 `reason`（cand_id 不存在 / criterion
  未知 / 引句不在原文中 / 缺字段）。修正后重投；同一候选多行决定时**最后一行生效**，
  全部历史留存在 screening.jsonl 与 change_records 中。
- **解析异常**：条目不是对象、字段缺失、编码问题等，一律降级（字符串按标题处理、缺字段
  留空），并在 harvest_report.json 的 notes 中记录，绝不中断。

## result.json 契约

`/app/output/result.json` 必须包含：

- `case_id`：防御式取自 case.json（case_id / id / case 等键），取不到给 "unknown"；
- **output_contract 声明的全部字段逐一镜像**：递归搜索
  `output_contract / contract / output_fields / required_fields`，声明了而暂无法填的字段
  填 `null` 并在 uncertainties 里说明；
- `status`：`success | partial | failed`。规则：全部候选均有有效决定且流程不变量通过 →
  success；存在未筛选/待定候选或空候选集 → partial 并在 limits 说明；流水线未能产出可信
  结果 → failed；
- `screening`：每条候选的 {metadata, source, decision, criterion, rationale,
  evidence_quote, rank_rationale}；
- `evidence_records`：每条被采用决定的 {cand_id, evidence_quote, verified:true}；
- `flow`：PRISMA 风格计数与不变量校验结果；
- `omissions`：未筛选列表、待定列表、空结果声明（如适用）；
- `uncertainties`：弃权项、元数据缺失、镜像字段为 null 的说明等；
- `change_records`：全过程变更日志（init / apply / reject / rebuild）。

参考文件：`references/prisma_flow.md`（流程阶段与不变量）、
`references/screening_criteria.md`（标准目录与弃权/排序规则）。
