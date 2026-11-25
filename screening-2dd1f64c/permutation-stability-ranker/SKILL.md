---
name: permutation-stability-ranker
description: 文献筛选与排序任务的过程质量控制引擎。把排序稳定性作为一等交付物：对候选输入顺序做置乱、对特征权重做 ±10% 播种抖动，跨 N 次扰动运行量化每条记录的名次极差、翻转次数与 Kendall's W 和谐系数，名次不稳定的记录被显式移入 pending_review 复核带而非静默排除。全部评分确定、可解释、无需模型即可运行；可选的一次批量模型判定仅作为一个加权特征注入。当任务要求筛选排序结果本身可信、可复核、抗扰动时使用。
---

# permutation-stability-ranker

## 用途与重心

本 Skill 的重心是**过程质量控制**：一个稍微扰动候选顺序或特征权重就会翻转的排序不值得信任。多数筛选流水线只交付"那个排序"，本 Skill 交付"这个排序有多稳"——基准排序完全由确定性、可解释的加权特征算出（无需模型），再用固定种子的 N 次扰动运行（输入置乱 + 权重 ±10% 抖动）逐条记录报告名次极差（rank range）、相对基准的翻转次数，以及全体运行的 Kendall's W 和谐系数。判为 fragile 的记录不被排除，而是带着明确理由移入 pending_review 复核带。可选的语义相关性分（一次批量模型调用产出）只是权重表中的一个普通特征，不改变任何流程。

## 适用条件

- 输入为 `/input/case.json`（固定研究问题、实际查询输入、有限候选快照；部分案例含以 `fixture_note` 等字段显式标注的合成重复导出/冲突观点夹具——仅作 provenance，绝不当作 ground truth）与 `/input/task.md`。
- 候选快照约 9 条真实署名文献，要求**全记录筛选**：最终 ranking 与 pending_review 带合起来恰好覆盖每条输入记录一次。
- 平台运行契约：在 `/app/work` 下工作，最终结果写入 `/app/output/result.json`，必须含 `case_id`（回显）与案例 `output_contract` 声明的全部字段，以及诚实的 `status{state,completed,incomplete,limits}`、`uncertainty`、`change_records`。

## 运行契约与预算纪律（64 次模型请求 / 900 秒）

按以下五步执行，模型调用 **≤2 次**；任何一步失败立即跳到第 4 步的退化路径，先保底交付诚实 partial：

1. **特征化（脚本，无模型调用）**
   `python3 /skills/weekly-skill/scripts/stability_engine.py featurize --case /input/case.json --out /app/work/features.json`
   每条记录产出可解释特征（标题/摘要词元重叠、年份在检索范围内、有无摘要/DOI、venue 层级启发式、recency 归一），全部定义写入 features.json 的 `meta.feature_definitions`，可手工复算。
2. **（可选，1 次模型调用）批量语义判定**：对全部记录一次性输出 `[{"record_id","semantic_score":0..1}]`，存 `/app/work/judgments.json`。9 条规模禁止逐条调用；判不了就不给分（缺省跳过该特征），不得编造。
3. **评分与扰动（脚本，无模型调用）**
   `python3 /skills/weekly-skill/scripts/stability_engine.py score --case /input/case.json --features /app/work/features.json --weights /skills/weekly-skill/examples/minimal/weights.example.json --runs 50 [--judgments /app/work/judgments.json] --out /app/work/stability.json`
   输出基准排序（score 降序 → record_id 升序，平分共享名次并列 `tie_group`）、每条记录的 rank min/max/mean 与翻转次数、Kendall's W（公式见 `references/stability-method.md`）、stable/watch/fragile 分类。同一输入必得同一 stability.json（种子 20261125）。
4. **装配（脚本）**
   `python3 /skills/weekly-skill/scripts/stability_engine.py assemble --case /input/case.json --stability /app/work/stability.json --out /app/output/result.json`
   stable/watch 记录保持基准次序；fragile 记录移入 pending_review 带并写明理由 "rank unstable under perturbation (rank range X)"；镜像 output_contract 的每个字段——同名输入字段回显、*omission*/*coverage*/*note* 类字段生成诚实说明、无法产出的字段显式 `null` + `status.incomplete`。**退化路径**：stability.json 缺失或不完整时，本步单独运行即产出全 pending_review 的 partial（`stability_report: null`，原因写入 `status.incomplete`），不伪造任何评分。
5. **交付校验（脚本）**
   `python3 /skills/weekly-skill/scripts/stability_engine.py validate --case /input/case.json --result /app/output/result.json`
   校验 case_id 回显、契约字段齐全、全记录恰好覆盖一次、final_rank 无未说明的重复、stability_report 的 N≥1 且 W∈[0,1]（partial 退化态豁免）。FAIL 打印问题清单并以退出码 1 终止，修复后重跑第 4 步；PASS 才视为可交付。

时间不足时：跳过第 2、3 步，直接以不存在的 stability 路径跑第 4 步，再跑第 5 步——两分钟内核验通过的诚实 partial。

## 输入与输出

- 输入：`/input/case.json`、`/input/task.md`；中间物：`/app/work/features.json`、`/app/work/judgments.json`（可选）、`/app/work/stability.json`。
- 输出：`/app/output/result.json`，含 `case_id`、`screened_records`（base_rank/final_rank/band/stability/rank_range/分数/理由）、`ranking`、`stability_report`（Kendall's W、翻转计数、runs N、种子、权重抖动规格、阈值）、`summary`、`status`、`uncertainty`、`change_records`（每条移入 pending_review 的记录一条变更记录），以及契约声明的每个其他字段。

## 异常处理

- case.json 无法解析 → 脚本以退出码 2 终止并说明，不猜测。
- 候选定位宽容：依次尝试 candidates/records/papers/references/pool/items，否则取最大的"含 title 的字典列表"；record_id 依次尝试 record_id/id/paper_id/doi，缺省 rec-NNN。
- 特征值为 null（年份/范围不可解析、无摘要等）→ 按中性 0.5 计入（定义写在 features.json meta），不丢弃记录。
- weights 中声明但所有记录都缺失的特征（如无 judgments 时的 semantic_score）→ 整列跳过并按剩余权重归一。
- judgments 缺失/部分缺失 → 缺失记录该特征为 null，走中性插补；绝不反向编造分数。
- 夹具字段（fixture_note 等）仅可引用为 provenance，不得作为排序或正确性依据。
- 契约字段无法产出 → 显式 null + `status.incomplete`，`status.state` 降 partial，绝不静默丢字段。

## 方法说明与限制

- 方法细节（特征定义、权重依据、扰动设计、Kendall's W 公式与并列修正、stable/watch/fragile 阈值、fragile 为何进复核带而非排除、平局协议）见 `references/stability-method.md`。
- 限制：词元重叠是主题相关性的词法代理，venue_tier 是字符串启发式（标注 `heuristic:true`）；语义判断质量取决于可选的第 2 步；稳定性结论以所选权重族为前提，权重本身变化超过 ±10% 时的行为不在保证范围内。
- 本 Skill 不补造文献、不做快照外召回声明；候选池是有限快照。
- 自查方法：`validate` PASS 且 `status.state` 与人工预期一致；同一 case 连跑两次 `score` 应得到逐字节相同的 stability.json；`examples/minimal/`（合成示例，不冒充正式案例结果）中端到端预期输出见该目录 README。
