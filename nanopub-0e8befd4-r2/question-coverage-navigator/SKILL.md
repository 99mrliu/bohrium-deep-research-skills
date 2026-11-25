---
name: question-coverage-navigator
description: >-
  用于问题驱动的论文定向阅读与覆盖闭合：先把竞赛/研究任务拆成根问题、子问题、所需证据种类及答案—断言链接的 requirement matrix，再按问题定位摘要、方法、结果、图表和补充材料；尤其适合需要区分直接报告、自行计算、谨慎推断与 asked-but-unreported，并把答案、claim/evidence IDs、sources、uncertainty、change_records 闭合到任务定制 result.json 的任务。不要把它用于 PDF 版面/坐标抽取、独立数值计算器、RDF 或 nanopublication 导出、只检查格式而不回答问题的 lint，或无论文证据闭合需求的通用聊天。它可以用 nanopub 作证据载体，但绝不以“只交付 nanopub”替代逐问回答。
---

# Question Coverage Navigator

## 目标与完成标准

先回答问题，再组织证据。不是平均读完整篇 PDF，也不是从已有 nanopub 反推任务。完成必须同时满足：

1. 任务中的每个根问题与子问题都能定位到矩阵行和 result 中的直接答案。
2. 每个非未报告答案都可沿 `answer → claim ID → evidence ID → source/locator` 回查。
3. 直接报告、计算和推断不混写；已检索未报告有 `searched_scope`。
4. 最终 `/app/output/result.json` 保留原 `case_id`，包含**该任务实际 output_contract 的全部字段**；EXACT 时顶层不多也不少。
5. `/app/work`、`/app/output` 中有可恢复工作文件与最终报告；sources、uncertainty、change_records 诚实记录。

结构校验通过不等于科学正确，诚实 partial 优于编造完整。

## 一、启动：读取真实环境，不猜固定 schema

必须读取：

- `/input/case.json`：原样取得 `case_id`（或任务 manifest 指定的原 ID 位置），识别可用材料。
- `/input/task.md`：提取原问题和 `output_contract`。**任务契约优先**于 case 回退契约、示例和本 Skill 的 manifest。
- 实际 `environment/resources.yaml`（若平台挂在 `/input/environment/resources.yaml` 则读取该实例）：确认挂载来源、索引、运行限制和路径语义。它是环境信息，不得用示例键覆盖真实环境。

只用 `/app/work` 做中间工作，用 `/app/output` 做交付。不要依赖创建者个人路径，也不要假设官方字段就是示例中的 `answers/sources/uncertainty/change_records`。未知 schema 的处理见 `references/manifest-contract.md`：复制 manifest 后修改 JSON Pointer、键名和 output map。

```bash
export SKILL_DIR="/app/skill"  # 指向实际挂载且含 SKILL.md 的本目录
mkdir -p /app/work /app/output
cp "$SKILL_DIR/references/coverage-manifest.json" /app/work/coverage-manifest.json
# 根据实际 task/schema 修改 /app/work/coverage-manifest.json 后：
python3 -B "$SKILL_DIR/scripts/coverage_tool.py" skeleton \
  --task /input/task.md \
  --case /input/case.json \
  --manifest /app/work/coverage-manifest.json \
  --output /app/output/result.json
cp /app/output/result.json /app/work/result.early-partial.json
```

这个 skeleton 是**待填写的 early partial，不是通过验证的成果**。立即把已识别问题填入答案数组，未启动项标 `unanswered`、进度 0，不能用伪造来源或空泛“已解决”填充。契约允许时保留空数组；示例 manifest 的最终审计会将部分必填空字段报为缺口。每次实质更新都保存覆盖文件和 result，保留全部契约顶层字段。

## 二、先写 requirement matrix，再定向阅读

在任何全文平均通读之前，于 `/app/work/coverage.json` 建立问题树和矩阵。详细规则见 `references/question-matrix.md`。每个最小单元预登记：

- Q/子问题 ID 与逐字任务范围；
- 所需证据种类（人群、定义、比较、时间点、结局、区间、方法限制等）；
- 任务/断言链接，目标论文区域与检索同义词；
- 答案槽、预期回答模式、claim/evidence 链接、状态、置信度；
- 若为未报告，检索范围槽。

按矩阵检索摘要、方法、结果、图表标题/脚注、补充材料入口及它们的邻近限定语。只在需要定义、输入、分母、替代解释或披露检查时做最小扩读。新增发现若改变任务问题，写入 change_records，不得静默删去原问题。

### 三种有证据的回答与一种无报告回答

- `direct_report`：来源直接给出答案，提供 locator/quote 和 direct evidence。
- `computed`：答案由回答者计算，列出输入来源、公式、单位和 derivation；本 Skill 不替你做算术。
- `inferred`：明确“推断/可能”，提供 rationale 和替代解释边界，不冒充原文。
- `unreported`：仅在定向查找后使用，明确“未报告”，记录 source、区域、关键词、图表和补充材料检查。零、阴性、无显著性、尚未搜寻均不等于未报告。

混合模式应继续拆子问题。状态、进度上限和未报告语义见 `references/coverage-status.md`。

## 三、覆盖闭合与保存

按以下顺序循环，而非按 PDF 页码机械循环：

1. 选定最高优先级未闭合矩阵行。
2. 定位最小相关区域，保存 source 记录及 source-level uncertainty。
3. 先写直接答案，再写原子 claim，再链接 evidence；计算/推断补全审计材料。
4. 回写该行状态与 result 对应元素；父问题给综合回答但不能掩盖未答子级。
5. 记录实质修正、删除和模式降级到 change_records。
6. 每获得一组可相互印证的材料、每 5 分钟或每 12 次外部请求（先到者）保存 early partial。

至少维护 `/app/work/coverage.json`、`/app/work/result-skeleton.json`、`/app/work/coverage-partial.report.json`、`/app/output/result.json`、`/app/output/coverage-report.json`。中断时 result 仍是符合顶层契约的诚实 partial。

生成可填写 skeleton、检查中间覆盖并输出缺口：

```bash
python3 -B "$SKILL_DIR/scripts/coverage_tool.py" skeleton \
  --task /input/task.md --case /input/case.json \
  --manifest /app/work/coverage-manifest.json \
  --output /app/work/result-skeleton.json

python3 -B "$SKILL_DIR/scripts/coverage_tool.py" validate \
  --task /input/task.md --case /input/case.json \
  --manifest /app/work/coverage-manifest.json \
  --coverage /app/work/coverage.json \
  --report /app/work/coverage-partial.report.json \
  --skeleton /app/work/result-skeleton.json
# 退出 0：结构闭合；退出 1：读取 gaps 修复；退出 2：输入/契约/manifest 错误。
```

校验器检查根问题与子问题答案、claim/evidence IDs、claim→evidence→source 链、重复/悬空/局部重复引用、未报告 searched_scope、模式所需支持、计算 derivation、推断 rationale、状态/进度/置信度上限、sources 与全局 uncertainty、change_records，以及可填 result skeleton。报告 `gaps` 就是修复清单。

## 四、最终 result：任务契约优先，执行 EXACT

coverage 通过后，从当前 coverage 和任务实际 output map 构建结果；不要用另一套手写副本绕过一致性检查：

```bash
python3 -B "$SKILL_DIR/scripts/coverage_tool.py" build-result \
  --task /input/task.md --case /input/case.json \
  --manifest /app/work/coverage-manifest.json \
  --coverage /app/work/coverage.json \
  --output /app/output/result.json \
  --report /app/output/coverage-report.json

python3 -B "$SKILL_DIR/scripts/coverage_tool.py" audit \
  --task /input/task.md --case /input/case.json \
  --manifest /app/work/coverage-manifest.json \
  --coverage /app/work/coverage.json \
  --result /app/output/result.json \
  --report /app/output/coverage-report.json \
  --skeleton /app/work/result-skeleton.json
```

`build-result` 遇到覆盖错误会拒绝生成。`audit` 还会验证原 case ID、全部声明字段、基本字段类型、EXACT 额外字段、manifest 非空要求和 result↔coverage 映射一致性。非 EXACT 契约不因额外顶层字段自动失败，但缺字段仍失败。只有 audit 退出 0 才可宣称结构校验通过；退出 1 必须修复 gaps 后重跑。

## 五、64 requests / 900 seconds 硬预算

- 以任务开始单调计时，总墙钟不超过 **900 秒**；最后 **120 秒**只用于覆盖检查、result/report 和保存。
- 全部外部论文、检索、网页获取及重试合计不超过 **64 requests**；本地 Python 校验不消耗外部请求。若环境对 request 定义更严格，采用更严格计数。
- 前 60 秒：读完三个 `/input` 输入并生成 skeleton/early partial。前 180 秒：完成第一版全问题矩阵及案例适配 manifest。
- 请求 0–32：高优先级根问题与必需证据；33–48：未答、矛盾与未报告范围；49–64：只补审计发现的明确缺口，不扩展新问题。
- 到 48 请求后禁止广撒网；到 56 请求后不再扩展阅读，优先闭合 claim/evidence 与 EXACT。到 64 请求必须停止外部检索。
- 600 秒仍未闭合的行转为诚实 partial；已查充分但未获得信息才写 unreported，未查充分写 unanswered/partial。不得为赶预算伪造引文。

## 六、本地合成样例与真实测试

`examples/` 全部标为 **SYNTHETIC**，不是正式结果、真实论文或临床证据。最小来源为 `examples/sources/study.md`；正例有 20 条合成断言、20 条证据、6 个根问题和 24 个子问题，覆盖四种回答模式。输出文件是工具真实执行产生，而非手写预期：

- `examples/positive/input/coverage.json`
- `examples/positive/output/result.json`
- `examples/positive/output/coverage-report.json`：`ok=true`
- `examples/negative/input/coverage.json`：故意空答案及悬空 claim/evidence
- `examples/negative/output/coverage-report.json`：`ok=false`，保留真实失败 gaps

从本 Skill 根目录运行（无需网络、第三方包或个人路径）：

```bash
export SKILL_DIR="$(pwd)"
python3 -B "$SKILL_DIR/scripts/run_examples.py"
python3 -B -m unittest discover -s "$SKILL_DIR/scripts" -p 'test_*.py' -v
```

预期：正例 skeleton/build-result/audit 均退出 0；负例 validate 退出 1，且 `run_examples.py` 自身在确认这个预期失败后退出 0；34 项单元测试通过。恢复/重建合成 fixture 可运行 `python3 -B "$SKILL_DIR/scripts/create_synthetic_fixture.py"`，随后重跑 `run_examples.py` 生成结果与报告。

## 结果与限制

交付主结果是逐问回答的 `/app/output/result.json`；`/app/output/coverage-report.json` 是结构审计。工具仅使用 Python 3.9+ 标准库，可读 JSON 和含 JSON 代码块的 task Markdown，不解析 YAML（Agent 须读取 resources），不验证引文与原始文件的语义一致性，不做算术、跨段抽取、PDF 坐标/版面分析、RDF 导出或纯 lint，也不证明科学真实性。任意新科学规则需人工/领域复核并扩展测试；不能为了让 unseen schema 通过而静默放宽 manifest。
