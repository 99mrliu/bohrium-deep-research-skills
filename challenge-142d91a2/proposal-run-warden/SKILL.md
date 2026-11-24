---
name: proposal-run-warden
description: |
  开题报告运行过程守门员（Run Warden for Proposal Writing）。重心不在写稿方法，而在运行过程质量控制与交付契约守门：在 64 请求/900 秒/16384 tokens 硬预算下，用预算分配表与降级阶梯（L0–L4）编排进度，用原子检查点保证任何时刻 /app/output/result.json 都是有效且诚实的交付，用 append-only 台账在用量 >80% 时强制收尾，最后用契约终检门逐字段核验并对缺项强制 partial、全程留痕。
  触发：task.md 要求撰写开题报告/研究计划书且预算受限，需保证中断可交付、缺项不谎报、逐步改进可复核时；多案例重复运行需过程稳定性时。不触发：研究选题判断、科学内容裁决、语言润色本身。
  Trigger: runtime quality control for research-proposal writing under a hard request/time/token budget — atomic checkpoints, append-only budget ledger with forced-finalize alerts, L0–L4 degradation ladder, and a final contract gate that forces honest partial. Not for: topic selection, scientific-correctness adjudication, prose polishing itself.
---

# 开题报告运行守门员（Proposal Run Warden）

## 1. 定位与差异化

本 bundle 的重心是**运行过程质量控制与交付契约守门**：同样能力的 Agent，在 64 请求/900 秒
预算下写开题报告的实际得分差异，主要来自过程失控——前半程挥霍请求导致风险章节没时间写、
中断时磁盘上是半个 JSON、字段缺失却自称完成。本 bundle 不管「怎么写好」（那是其他 bundle
的领域），只保证四件事：**任何时刻有有效交付、改进逐步落盘、缺项诚实 partial、全程留痕可复核**。
解决的真实失败模式：预算超支截断、中断交付无效 JSON、契约字段漏填、status 虚报 ok。

## 2. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`output_contract` 逐字段抄录，不凭题面猜字段名 |
| 材料 | `/input/` 附带材料须真实读取；PDF 一律 `pdftotext -layout` 解析，无预提取答案层 |
| 工作目录 | `/app/work`（草稿、台账、checkpoint 日志、中间产物） |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）+ `guard_report.json` |
| 预算 | 64 次模型请求 / 900 秒 / 每响应 16384 tokens（含推理）——本 bundle 的存在理由 |
| Skill 路径 | `/skills/weekly-skill`；路径不同时替换命令前缀 |

## 3. 必需工作流

预算分配、时间检查点与降级阶梯的完整规程见 `references/runbook.md`；下列命令与之对应。

**步骤 0（T+30 秒内完成）——契约读取 + 诚实 partial 落盘：**
```
python3 /skills/weekly-skill/scripts/checkpoint.py init /input/case.json /app/output/result.json \
  --log /app/work/checkpoint_log.jsonl --requests-used 2
```

**步骤 1——材料通读（≤10 请求）：** PDF 用 `pdftotext -layout`；每份材料读完或登记不可读；
台账自记：
```
python3 /skills/weekly-skill/scripts/budget_ledger.py add /app/work/budget_ledger.jsonl \
  --purpose "材料通读：<文件名>" --tokens <估计值> --requests-left <剩余> --phase reading
```

**步骤 2——要素起草（≤20 请求）：** 七要素逐一成段，**每完成一要素立即 checkpoint**（原子替换）：
```
python3 /skills/weekly-skill/scripts/checkpoint.py save /app/output/result.json \
  --log /app/work/checkpoint_log.jsonl \
  --set-file proposal_draft=/app/work/draft.md --sources-file /app/work/sources.json \
  --note "<本次完成的要素>" --requests-used <N> --tokens-used <T> \
  --completion <0-100> --level <L0-L4>
```

**步骤 3——校验修订（≤16 请求）：** 引文逐字抽验 ≥30%；指标阈值逐条对照周期/经费/人员约束；
每轮修订后 `checkpoint.py save` 并台账 `add`。

**步骤 4——强制收尾（T+600s 或用量 >80% 触发，预算 4 请求）：**
```
python3 /skills/weekly-skill/scripts/budget_ledger.py report /app/work/budget_ledger.jsonl
python3 /skills/weekly-skill/scripts/contract_guard.py /input/case.json \
  /app/output/result.json /app/output/guard_report.json
python3 /skills/weekly-skill/scripts/checkpoint.py status /app/output/result.json \
  --log /app/work/checkpoint_log.jsonl
```
`contract_guard` 退出码 1 表示存在 fail 项：它已把 result.json 强制回 `status:"partial"`
并在 uncertainty 点名；只修复可速修项后允许重跑一次。

## 4. 异常处置表

| 异常 | 处置 |
|---|---|
| 材料缺失 | uncertainty 点名缺失文件；受影响要素按 L3 骨架处理，其余正常推进 |
| 材料乱码/不可读 | 换 `pdftotext -raw` 或按页分次重试一次；仍失败记 uncertainty，不反复重试 |
| 周期过短（任务周期 < 常规） | 在 schedule 中压缩至约束内并在 uncertainty 声明依据，禁止超期里程碑 |
| 指标不可达 | 以材料给出的量级为阈值依据改写目标；不可改写时记 uncertainty 并降级到 L2 |
| 预算不足（>80% 或 T+600s） | 执行 runbook §4 强制收尾：冻结改进，只补空缺字段 + 终检 |
| 重复运行 | checkpoint 日志与台账重开文件；产物字段集合必须与上次一致，差异只能来自内容判断 |

## 5. 交付前自查清单

- [ ] `checkpoint.py status` 可正常解析 result.json（任何时刻有效交付）
- [ ] `contract_guard.py` 已运行且 `guard_report.json` 落盘；退出码与 status 一致
- [ ] status 诚实：缺字段/缺要素必为 partial，且 uncertainty 逐条点名
- [ ] checkpoint 日志含时间戳、预算消耗自报、完成度自评、当前降级层级
- [ ] 台账 append-only、无手工改动；>80% 预警出现时已执行强制收尾
- [ ] 降级层级变化均有 note 说明理由；机动余量 ≥8 未被提前挪用
- [ ] 契约字段名与 `case.json.output_contract` 逐字一致，无自造字段

## 6. 最小示例说明

`examples/` 为**合成示例（非正式案例结果）**，题材「固态锂电池界面工程」。
`bash examples/run_example.sh` 演示：init → 两次模拟 checkpoint（含一次预算 82% 预警）→
对故意缺 `risk_register` 字段、缺「风险与备选」要素的合成 result.json 跑 `contract_guard`，
展示缺项拦截与 partial 强制；`expected/` 为真实跑出的产物，`result.json` 即一份诚实 partial。
