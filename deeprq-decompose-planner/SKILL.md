---
name: deeprq-decompose-planner
description: 深度研究任务的"问题拆解 + 检索规划 + 可复跑执行日志"引擎——把 case.json/task.md 中的综述类研究问题结构化为六要素拆解树（研究对象、机制/干预、对照、结局指标、时间范围、证据要求），生成带依赖 DAG、检索波次、停止条件与预算分配的检索计划，执行时以 append-only 运行日志逐笔记录每次工具调用的输入参数、返回计数与内容哈希，使整条研究路径可被第三方按日志逐笔复跑。Use when a task asks to conduct deep research, literature review, systematic screening, trend analysis or topic evaluation from a fixed research question (深度研究, 文献综述, 检索规划, 问题拆解, 可复跑, run journal).
---

# 深度研究拆解与检索规划引擎（deeprq-decompose-planner）

## 何时使用

案例给出一个综述/筛选/趋势分析/选题评估类研究问题（`task.md` + `case.json`，可能附 PDF 等材料），要求交付有来源定位的综合结论时，使用本 Skill。典型平台场景：`/input/case.json` + `/input/task.md`，结果写入 `/app/output`（含遵守 `output_contract` 的 `result.json`）。本 Skill 的核心增益在链路前端：把问题拆成可独立检索的子问题、为子问题安排有依赖、有停止条件的检索计划，并让每一步都可复跑；证据回填与综合阶段提供结构化骨架，与任何下游写作方式兼容。

## 运行方式（三步）

```bash
# 1) 一条命令生成拆解树、检索计划与执行骨架（先产出 partial result.json）
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output

# 2) 按 /app/output/retrieval_plan.json 的波次执行检索；
#    每完成一次工具调用，立即记一笔日志（一行一条，绝不留到事后补记）：
python3 /skills/weekly-skill/scripts/journal.py append \
    --journal /app/output/run_journal.jsonl \
    --tool web_search --args '{"query":"...","numResults":5}' \
    --results-count 5 --results-digest sha256前16位 \
    --note "W1 波次，SQ-2 饱和检查：新增相关文献 0 篇"

# 3) 检索覆盖达标后，填证据与结论，校验并收尾：
python3 /skills/weekly-skill/scripts/finalize.py \
    --case /input/case.json --work /app/work --out /app/output
cat /app/output/coverage_matrix.json   # 每个子问题 × 每个来源的覆盖状态
```

若非平台环境，把路径换成用户给定的输入/输出目录。全程预算意识：模型请求 ≤ 60 次、检索调用 ≤ 25 次为规划默认值，超支前必须先完成当前波次再决定是否追加（见 resources/retrieval_policy.md）。

## 流水线做了什么（每步都可重跑）

1. **拆解（decompose.py）**：从 task.md 提取研究问题的六要素——研究对象（population/材料体系）、机制或干预（mechanism/intervention）、对照（comparator）、结局指标（outcome/metric）、时间范围、证据要求（证据类型与最低强度）——生成 `decomposition_tree.json`。每个子问题 SQ-n 必须满足：可独立检索（自带中英文检索式）、有明确验收标准（什么样的一条文献算"回答了本子问题"）、标注依赖（depends_on 为空表示前置/可并行）。模板禁止只把原句改写成关键词：每个 SQ 必须写出"检索什么字段、比较什么、纳排什么"。
2. **检索规划（plan.py）**：把拆解树编译为 `retrieval_plan.json`：波次 W1 背景定界（先行，1–2 次调用）→ 波次 W2 各 SQ 并行检索（按依赖分层调度，同层并发）→ 波次 W3 缺口补检（仅当 coverage_matrix 显示某 SQ 未达标时触发）。每个检索动作带：来源范围（检索 API、Crossref/OpenAlex、网页、本地材料）、检索式、停止条件（每 SQ 相关命中 ≥ 3 篇或连续 2 次检索新增相关数为 0）、去重键（DOI 或首作者+年份+标题前缀）。同一批文献不得被两个 SQ 重复检索——命中共享走"一次检索、多 SQ 标注"。
3. **执行留痕（journal.py）**：append-only JSONL 日志，逐笔记录工具名、完整输入参数、返回条数、返回内容 SHA-256、时间戳与备注。日志支持 `journal.py verify`（重算哈希链，发现缺笔/改笔即报错）与 `journal.py replay`（按日志顺序打印复跑清单，供第三方照着重放）。任何失败重试也必须记一笔（status=retry/failed），失败原因不丢。
4. **覆盖与缺口（coverage 计算于 finalize）**：由日志与检索结果自动生成 `coverage_matrix.json`：行=子问题，列=来源/波次，单元格=达标/未达标/未检索。研究空白只从该矩阵导出：searched_but_absent 记为高置信缺口，not_searched 记为无法判断，禁止凭印象写空白。
5. **综合骨架**：finalize 生成 `synthesis.md` 骨架——每条结论句预留 `[SQ-n][E-xx]` 锚点位置、冲突证据段、空白段；Agent 按骨架填写，凡写不出锚点的结论句必须移入"无法确定"段并说明原因。

## 输入 / 输出

- 输入：`case.json`（含 `case_id`、`output_contract`）、`task.md`、可选材料文件（PDF 等，路径以实际文件为准，不依据目录标签推断内容）。
- 输出（`/app/output`）：`result.json`（遵守 `output_contract` 全部字段 + 原始 `case_id`，含诚实 `status`/`sources`/`uncertainty`）、`decomposition_tree.json`、`retrieval_plan.json`、`run_journal.jsonl`、`coverage_matrix.json`、`synthesis.md`、`run_manifest.json`（环境、CLI/脚本版本、输入文件哈希、时间线）。

## 依赖与异常处理

- 仅依赖 Python 3 标准库；拆解/规划全部为确定性脚本，检索本身由 Agent 按 plan 调用其可用工具完成。
- 输入文件缺失：立即在 result.json 写 `blocked` 状态并指出缺哪个文件，不猜测内容。
- 检索为空：该 SQ 标 `未命中`，触发一次放宽检索式（记日志），仍为空则如实进入缺口分析。
- 工具报错/限流：记 failed 笔，按退避顺序降级（检索 API → 网页直取 → 本地材料），降级决策写入日志备注。
- 子问题依赖成环或 SQ 超过 12 个：plan.py 报错并输出诊断，Agent 须先合并/删除子问题再继续，不允许带病执行。
- result.json 从第 1 步起就存在；任何中断都留下可检查的部分产物与已记日志。

## 不适用边界

- 不做单篇文献逐句精读、不做文献元数据方法学审查、不做全文翻译与润色（相邻课题，本 Skill 只消费其输入）。
- 不代替 Agent 执行检索：本 Skill 给计划与留痕框架，检索动作由 Agent 完成并记账。
- 不预制任何案例答案；所有结论必须由本次运行的检索与材料产生。

## 复跑方法

把 `run_journal.jsonl` 交给第三方，按 `journal.py replay` 打印的顺序与参数逐笔重放工具调用，对比 `results-digest` 与 `coverage_matrix.json`，即完成独立复核；日志哈希链由 `journal.py verify` 保证未被事后修改。

## 最小调用示例（示意输出，非正式案例结果）

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
  --case /input/case.json --input-dir /input --work /app/work --out /app/output
# 生成 decomposition_tree.json（含 5 个 SQ 与依赖 DAG）、retrieval_plan.json（3 波 11 个检索动作）、
# run_journal.jsonl（空日志，哈希链头已建立）、coverage_matrix.json（全"未检索"）、partial result.json
python3 /skills/weekly-skill/scripts/journal.py append --journal /app/output/run_journal.jsonl \
  --tool web_search --args '{"query":"perovskite defect passivation 2023 review","numResults":5}' \
  --results-count 5 --results-digest 9f2c... --note "W2 SQ-3"
python3 /skills/weekly-skill/scripts/journal.py verify --journal /app/output/run_journal.jsonl
# {"ok": true, "entries": 1, "chain_head": "a41b..."}
python3 /skills/weekly-skill/scripts/finalize.py --case /input/case.json --work /app/work --out /app/output
# 输出 synthesis.md 骨架与最终 result.json（status 依覆盖达标情况为 success/partial）
```

以上输出为接口示意；正式运行以平台 3 个固定案例的实际执行为准。
