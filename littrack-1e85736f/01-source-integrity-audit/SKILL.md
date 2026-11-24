---
name: source-integrity-audit
description: >-
  上游数据真实性审计（Bohrium Playground challenge-1e85736f「最新文献发现与追踪」方向之一）。
  在一切文献追踪/增量逻辑之前，对组织方本地固化的 Crossref / Europe PMC / arXiv / 出版商
  API 题录快照做完整性与真实性校验：SHA-256 哈希台账（source_ledger.json）、题录 Schema
  校验、元数据一致性（DOI 语法 / 日期合法且非未来 / arXiv 格式 / PMID 纯数字）、异常检测
  （源内重复、空标题、撤稿与更正标记、同源 v1/v2 快照结构漂移、增量导入状态中已导入记录
  消失），并给出 quarantine 清单与 gating 决策（proceed / proceed_with_quarantine /
  block），最终组装满足 case.json output_contract 的 result.json。完全离线、脚本仅用
  Python 标准库、所有事实性字段值带 locator（文件 + JSON Pointer）供复核，绝不编造
  DOI / 元数据 / 检索结果。与其他方向的边界：不做窗口调度、不做提醒投递、不做重试编排、
  不做 QA 评分。
---

# source-integrity-audit — 上游数据真实性审计

## 1. 适用场景与边界

**适用**：评测/实际任务给出本地固化的上游题录材料（Crossref、Europe PMC、
arXiv、出版商 API 响应快照、参考图谱、本地增量导入状态快照），要求在
**使用这些数据之前**先回答一个问题：*这批源数据本身可信吗？* 本 Skill 用
确定性脚本完成校验，模型只负责判断、解释与写作。

**差异化能力**（区别于常规"追踪/增量"流程）：

1. SHA-256 内容哈希台账：每个源文件的哈希、字节数、固化时间（取自材料自身
   字段，不编造）；
2. 题录级 Schema 校验（必备字段存在性与类型）；
3. 元数据一致性：DOI 语法 `^10\.\d{4,9}/\S+$`、日期合法且不得为未来（以
   `case.json` 窗口终点为"现在"）、arXiv 号格式、PMID 纯数字；
4. 异常检测：源内重复、未来日期、缺失日期、空标题、撤稿/更正标记、同源
   v1/v2 快照结构漂移、增量导入状态中已导入记录在当前源快照消失；
5. 输出 `integrity_report.json` + `quarantine` 清单 + gating 决策，汇入
   最终 `result.json`。

**明确不做**（属于其他方向的职责）：窗口调度（何时跑下一窗口）、提醒投递
（通知/邮件/消息）、重试编排（失败任务的重新排队）、QA 评分（对追踪结果
质量打分）。本 Skill 只产出"源数据是否可用、哪些记录应隔离"的判定。

## 2. 运行环境与输入定位兜底

- 运行环境：平台把本 Skill 安装到 `/skills/weekly-skill`；工作目录
  `/app/work`；最终必须写 `/app/output/result.json`。
- 案例输入为 `/input/case.json` 与 `task.md` 及材料文件，但**不要假设固定
  布局**。先用 `find` 定位：

```bash
find /input /app -maxdepth 4 -name 'case.json' 2>/dev/null
find /input /app -maxdepth 4 -name 'task.md' 2>/dev/null
find /input /app -maxdepth 5 -name '*.json' 2>/dev/null | sort
```

- 材料目录判定：读 `case.json` 看是否有 `materials_dir` 之类的路径提示；
  否则把 `case.json` 同级或 `/input` 下包含题录响应（Crossref/Europe PMC/
  arXiv 快照、`previous_snapshot.json` 增量导入状态）的目录作为材料目录。
- 全部脚本仅依赖 Python3 标准库、完全离线；复制脚本到 `/app/work` 下运行，
  产物也写到 `/app/work`，最终 `result.json` 写到 `/app/output/`。

## 3. 编号工作流程

> 确定性工作全部交给脚本（64 次模型请求 / 900 秒预算内，模型只做判断与
> 写作）。任何一步失败都要诚实降级，见 §5。

1. **读案例**：读 `case.json`（取 `case_id`、`task`、`window`、`materials_dir`
   提示、`output_contract`）与 `task.md`；确认材料目录与窗口终点
   `window.end`（作为"现在"）。
2. **哈希台账**：
   `python3 scripts/hash_ledger.py --materials <材料目录> --out /app/work/source_ledger.json`
3. **Schema 校验**：
   `python3 scripts/validate_schema.py --materials <材料目录> --out /app/work/schema_report.json`
4. **异常检测**：
   `python3 scripts/detect_anomalies.py --materials <材料目录> --window-end <window.end> --window-start <window.start> --out /app/work/anomaly_report.json`
   （若材料中有增量导入状态快照，加 `--previous <路径>`；缺省会自动探测
   `<材料目录>/previous_snapshot.json`。）
5. **gating 决策**：
   `python3 scripts/gate.py --ledger /app/work/source_ledger.json --schema /app/work/schema_report.json --anomalies /app/work/anomaly_report.json --out-dir /app/work`
   产出 `integrity_report.json`、`quarantine.json`、`gating_decision.json`。
6. **模型复核**（这是模型的核心工作）：阅读 `anomaly_report.json` 与
   `gating_decision.json`，抽查每条异常的 locator 与 evidence 是否与材料
   一致；判断 gating 结论是否合理（阈值见
   `references/integrity-rules.md` §5，异常分类见
   `references/anomaly-taxonomy.md`）；把结论写成简短说明。
7. **组装结果**：
   `python3 scripts/assemble_result.py --case <case.json> --out-dir /app/work --result /app/output/result.json`
   该脚本强制校验 `output_contract` 字段齐全，缺失以 null 补齐并降级
   `status=partial`。
8. **最终自检**：读 `/app/output/result.json`，确认 `case_id` 与 case.json
   一致、`output_contract` 全部字段存在且非 null、`sources` /
   `uncertainty` / `change_records` 非空；不满足则回到对应步骤修复或诚实
   标注 partial。

若材料布局与脚本假设不完全一致（如题录在 `message.items`、顶层 list），
脚本已内置兼容（见 `scripts/common.py` 的 `extract_records`）；仍无法抽取
时，先检查材料真实结构，再决定是补充 locator 说明还是降级 partial，
**不要**为了让脚本通过而改动材料文件。

## 4. 输出契约（result.json 字段）

`/app/output/result.json` 必须包含 `case_id` 以及 `case.json` 中
`output_contract` 列出的全部字段；本方向约定如下（若 case 的
output_contract 有更多字段，以 case 为准）：

| 字段 | 内容 |
| --- | --- |
| `case_id` | 原样取自 case.json |
| `status` | `complete` / `partial` |
| `window` | 原样透传 case 的窗口配置 |
| `gating_decision` | `proceed` / `proceed_with_quarantine` / `block` 及理由、阈值 |
| `integrity_report` | 台账摘要 + Schema 摘要 + 异常清单（含 locator/evidence） |
| `quarantine` | 被隔离记录清单（locator、异常类型、动作） |
| `sources` | 每个源文件：路径、sha256、字节数、固化时间及其 locator |
| `uncertainty` | 不确定性声明（离线约束、固化时间不可独立验证等） |
| `change_records` | 台账初始化、结构漂移、与增量导入状态差异等"变化"记录 |
| `limitations` | partial 原因等限制说明（complete 时为空列表） |

所有事实性字段值必须来自案例材料或脚本产物，并带 locator
（`文件路径 + #JSON Pointer`）供复核；严禁编造 DOI、标题、日期、检索结果。

## 5. 异常处理与诚实 partial

- 任一脚本失败：保留已产出的中间产物，运行 `assemble_result.py`（它会把
  缺失产物记为 null 并自动降级 `status=partial`、在 `limitations` 写明
  哪一步缺失），绝不伪造中间产物。
- 源文件无法解析：该文件整文件进 quarantine，gating 为 `block`，
  `status=partial` 并在 limitations 说明。
- 模型判断与脚本输出冲突时，以材料原文 + locator 复核为准；若确认是脚本
  误报/漏报，在 `uncertainty` 中如实记录分歧，而不是悄悄改掉脚本输出。
- 时间预算不足时优先保证：台账 + Schema + 异常检测 + gating + 组装
  （主链五步），复核写作可以精简，但 `status` 必须反映真实完成度。

## 6. 最小调用示例

bundle 内置合成示例（数据全部为演示而编造，详见
`examples/minimal/README.md`）。在 bundle 根目录一键端到端运行：

```bash
python3 scripts/run_minimal_example.py
```

依次执行 §3 的第 2–5、7 步，产物写入 `examples/minimal/output/`
（`source_ledger.json`、`schema_report.json`、`anomaly_report.json`、
`integrity_report.json`、`quarantine.json`、`gating_decision.json`、
`result.json`），并自动做输出契约自检（PASS/FAIL 逐条打印）。示例刻意
埋入 10 类异常各 1 个（未来日期、非法 DOI、撤稿标记、源内重复、非法
PMID、空标题、缺失日期、非法 arXiv 号、v1/v2 结构漂移、已导入记录
消失），预期 gating = `proceed_with_quarantine`、quarantine 6 条；清单见
`references/anomaly-taxonomy.md` 末节。

## 7. 与其他方向的边界划分

| 职责 | 归属 |
| --- | --- |
| 源快照哈希台账 / Schema / 元数据一致性 / 异常检测 / quarantine / gating | **本 Skill** |
| 窗口调度（何时推进追踪窗口） | 其他方向，不做 |
| 提醒投递（通知用户新文献） | 其他方向，不做 |
| 重试编排（失败任务重新排队） | 其他方向，不做 |
| QA 评分（追踪结果质量打分） | 其他方向，不做 |

本 Skill 的输出（gating 决策与 quarantine 清单）是上述方向的**前置门**：
gating 为 `block` 时后续流程不应继续消费该批源数据。

## 8. 文件导航

- `scripts/common.py` — 共享工具（locator、日期、标识符校验、题录抽取）
- `scripts/hash_ledger.py` — 步骤 2：SHA-256 台账
- `scripts/validate_schema.py` — 步骤 3：Schema 校验
- `scripts/detect_anomalies.py` — 步骤 4：元数据一致性与异常检测
- `scripts/gate.py` — 步骤 5：quarantine 与 gating
- `scripts/assemble_result.py` — 步骤 7：组装 result.json
- `scripts/run_minimal_example.py` — 合成示例一键运行
- `references/integrity-rules.md` — 校验规则与阈值
- `references/anomaly-taxonomy.md` — 异常类型、严重度与示例预期检出
- `examples/minimal/` — 合成示例（case.json / task.md / materials / output）
