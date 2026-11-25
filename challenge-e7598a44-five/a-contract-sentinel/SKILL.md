---
name: rq-contract-sentinel
description: 科研问题驱动检索的"契约哨兵"——以 output_contract 为唯一验收标准的过程质量控制技能。先探针解析 /input/case.json 生成契约清单与兜底骨架，再跑确定性全记录筛查管线（解析/去重/筛查/署名核验），最后用独立门禁脚本逐项核验 result.json（case_id、契约字段全覆盖、空字段必有说明、状态诚实、来源可回溯），不过门禁不交付。适用于有限快照文献筛查、检索结果可复核交付、诚实 partial 状态管理。不适用：全网实时检索、单篇精读、替冲突证据做学术裁决。
---

# rq-contract-sentinel — 契约驱动的检索过程质量控制

**核心立场：交付物是否合格不由自我感觉决定，而由一道可复算的独立门禁决定。**

本技能的重心在**过程质量控制**：检索筛查管线保持轻量确定，重器放在"先知道要交什么、
最后证明交齐了"。三条命令完成一个案例，模型判断集中在唯一一处（复核 uncertain 记录）。

## 运行契约（平台环境）

- 输入：`/input/case.json`（含 `case_id`、`research_question`、`output_contract`）、
  `/input/task.md`、快照导出文件（JSON/JSONL/CSV/TSV/RIS，以实际内容为准）。
- 中间产物：`/app/work`；最终交付：`/app/output`（含 `result.json`）。
- `result.json` 必含 `case_id` 与 `output_contract` 列出的**每一个**字段；
  填不了的字段留空容器并在 `uncertainty`/`field_notes` 说明原因（诚实 partial）。
- 本技能目录记为 `SKILL_DIR`（通常 `/skills/weekly-skill`）；非平台环境换成实际路径。
- 仅 Python 3 标准库（≥3.8），零网络。**预算纪律**：三条命令约 1 分钟跑完；
  先把 `status=blocked` 的骨架保住，再逐步改善，任何中断都有可交付的诚实结果。

## 标准流程（三条命令 + 一次可选复核）

```bash
# 1) 契约探针：读 case.json → 契约清单 + 输入清点（sha256）+ result.json 兜底骨架
python3 SKILL_DIR/scripts/probe.py \
    --case /input/case.json --input-dir /input --work /app/work

# 2) 确定性管线：解析全部快照记录 → 去重（夹具标记原样登记）→ 逐条筛查
#    （年份窗/文献类型/术语命中，含内置跨语词表扩展）→ 署名清单逐篇核验
#    → 按 output_contract 装配 result.json（空字段自动写 field_notes）
python3 SKILL_DIR/scripts/pipeline.py \
    --case /input/case.json --input-dir /input --work /app/work --out /app/output

# 3) 独立门禁：不过不交付（gate=pass  exit 0；gate=fail  exit 1 并指明失败项）
python3 SKILL_DIR/scripts/validate.py \
    --case /input/case.json --work /app/work --out /app/output
```

**可选复核（唯一需要模型判断的环节）**：打开 `/app/output/ledger.jsonl`，把
`disposition=uncertain` 的少数记录逐条判定，写 `/app/work/overrides.json`
（格式：`[{"rid":"...","disposition":"include|exclude","reason":"..."}]`），然后
带 `--overrides /app/work/overrides.json` 重跑第 2、3 步。判不准就保持 uncertain
并在 uncertainty 中说明——**不确定是合法结果，臆造不是**。

## 门禁检查项（validate.py，详见 references/contract-rules.md）

C1 result.json 合法；C2 case_id 与输入一致；C3 契约字段全覆盖（null 即缺失）；
C4 空字段必须在 uncertainty 或 field_notes 中有说明；C5 status 三值且 complete 时
uncertainty 必空；C6 sources 中的文件引用真实存在；C7 candidates 字段齐全且每条
rid 可回溯到筛查台账；C8 uncertainty 为非空字符串列表。

## 产物清单

| 路径 | 内容 |
|-|-|
| `/app/output/result.json` | 按契约装配的最终结果（含 status/sources/uncertainty/field_notes） |
| `/app/output/ledger.jsonl` | 逐条筛查台账：rid、处置、理由码、命中词、来源文件 |
| `/app/output/candidates.json` | 纳入集（含命中词证据） |
| `/app/output/screening_summary.json` | PRISMA 式计数 + 派生条款（年份窗/术语/阈值） |
| `/app/output/attribution.json` | 署名清单逐篇核验（matched/ambiguous/missing + 元数据差异） |
| `/app/output/validate-report.json` | 门禁逐项判定（第三方可复算） |
| `/app/work/` | records/deduped/duplicates/ingest_report、契约清单与兜底骨架 |

## 异常处理（诚实状态机，见 references/status-machine.md）

- case.json 缺失/损坏：probe 写出 `status=blocked` 骨架并 exit=2，指明缺什么。
- 某文件解析失败：记入 `ingest_report.json` 的 failures，其余文件继续；不静默丢弃。
- 快照零记录：`status=blocked`，`summary` 说明空快照，不补造文献。
- 无署名清单：attribution 标 `no_reference_list` 并写入 uncertainty。
- 夹具标记（synthetic_duplicate / conflict_opinion 等）：原样登记，冲突意见只登记
  为争议证据并提示人工，**不做学术裁决**。

## 最小调用示例（合成示例，非正式案例结果）

`examples/minimal/` 内含合成的 case.json（8 契约字段）、8 条合成快照记录
（含 1 条夹具标注合成重复、1 条冲突意见夹具）与 3 篇合成署名清单。实测输出：

```
probe.py    → {"ok": true, "contract_fields": 8, "input_files": 3}
pipeline.py → {"records": 8, "kept": 7, "candidates": 4, "status": "partial"}
validate.py → {"gate": "pass"}   （exit 0）
```

partial 的原因（如实写入 uncertainty）：1 篇清单文献不在快照中、1 条冲突意见夹具
已登记待人工、1 条弱命中记录待复核。完整输出见 `examples/minimal/expected/`。

## 复用与维护

- 换领域：pipeline.py 顶部 `LEXICON` 是声明式词表，按领域增删即可；筛查阈值与
  文献类型排除表也在同文件顶部区域，单一事实来源。
- 换契约：无需改代码——契约字段全部从 case.json 动态读取。
- 版本：v1.0（2026-11，Python ≥3.8，stdlib only）。
