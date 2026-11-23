---
name: evidence-adjudicator
description: Answer questions about a paper the way a reviewer adjudicates claims — decompose every requested question into a ledger, retrieve candidate evidence windows, run a two-sided search (for and against), and deliver each answer with a verdict (supported / contradicted / not_reported / ambiguous), verbatim quotes and chunk anchors. Use for paper Q&A, claim verification, evidence checking and any reading task where every answer must carry its grounds.
---

# Evidence Adjudicator

重心在任务姿态：阅读任务按“裁定”处理——每个问题都要双侧检索（支持证据与反对证据都要搜），裁定只能是 supported / contradicted / not_reported / ambiguous，且必须留检索词与逐字引文。宁可答 not_reported，不可把猜测写成事实。

## 运行契约

- 输入：`/input/case.json`（`case_id`、`output_contract`，可能还有 `questions`）、`/input/task.md`、真实论文材料。工作区 `/app/work`，交付 `/app/output/result.json`（含 `case_id` 与全部合同字段）及中间账本。
- 诚实状态：裁定违规或合同缺项 → `partial`（逐条列出）；材料不可读 → `failed` + 接管指引；全部通过才可 `success`。预算 64 请求 / 900 秒，先落盘骨架再增量充实。
- `not_reported` 是一等裁定，但必须在 `searched.for` 里写明你检索过哪些词。

## 流程（K 为本 SKILL.md 所在目录）

### 1. 建立证据窗口

```sh
python3 "$K/scripts/chunk_source.py" --pdf /input/<paper>.pdf --case-id "$CASE_ID" --out /app/work/src
# 或 --text-file <平台文本导出>
```

产出 chunks.json：字符窗锚点 `c{页}-{序号}`（默认 1200 字符、200 重叠，含字节偏移）。

### 2. 问题台账

```sh
python3 "$K/scripts/decompose_questions.py" --case /input/case.json --task /input/task.md \
  --out /app/work/questions.json
```

每个请求项得到 q_id（问题）或 s_id（合同字段槽）。台账的意义是**任何一项都不能被静默漏掉**；裁定前逐项填 slots（subject/comparator/metric/setting），分不清比较对象的问题最容易答错。

### 3. 双侧检索与裁定

对每个问题，至少两轮检索（支持与反对各一轮），检索词含同义词、缩写与数值写法变体：

```sh
python3 "$K/scripts/retrieve_windows.py" --chunks /app/work/src/chunks.json \
  --question "<问题原文>" --terms "term A|term B|ABBR" --limit 8
```

裁定规则详见 [references/verdict-rules.md](references/verdict-rules.md)。要点：

- `supported`：≥1 条 evidence_for，quote 逐字落在锚点块内，且 quote 本身支撑整个改写后的答案（不是只沾边）。
- `contradicted`：原文明确相反；给出反对证据与数值/条件对比。
- `not_reported`：`searched.for` 非空、evidence_for 为空；写明查过的章节/窗口范围。
- `ambiguous`：双侧证据冲突或条件不全；两面都列出，不下结论。

逐条写入 `/app/work/verdicts.json`（格式见 [references/verdict-rules.md](references/verdict-rules.md)），并把 output_contract 要求的最终内容写进 `contract_fields`。

### 4. 校验与交付

```sh
python3 "$K/scripts/adjudicate.py" --case /input/case.json --ledger /app/work/questions.json \
  --chunks /app/work/src/chunks.json --verdicts /app/work/verdicts.json --out /app/output
```

校验 V1–V6（裁定合法、引文逐字、证据要求、检索留痕、覆盖完整），输出带 `adjudication` 摘要的 result.json。违规必须修复或下调裁定；禁止为空交付。

## 异常处理

- 材料不可读：chunk_source 返回 unreadable + handover，停止并说明。
- 检索全空：换同义词/缩写/数值格式再检；仍空 → not_reported，写明检索词。
- 图表/公式内的决定性数值：窗口文本不含图内数值，需回渲染页核对后在 uncertainty 记录。
- 超长论文：窗口检索天然可扩展；只对命中窗口精读，未命中区域不算“不存在”的证据——除非检索词覆盖了该区域同义表述。

## 最小示例（合成）

```sh
sh "$K/examples/synthetic-case/run_example.sh /tmp/eva-demo"
```

材料为虚构论文与三个演示问题，输出标注为合成示例。

## 依赖

Python 3.9+ 标准库；PDF 经 `pdftotext` 或平台文本工具导出。不联网、不装包。
