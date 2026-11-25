---
name: snapshot-forensics
description: 科研问题驱动检索的"快照取证"技能——重心在上游数据真实性。信任任何记录之前先做取证：对每个输入文件算 sha256 指纹、逐文件出解析取证报告（记录数/键分布/异常行）；建立隔离登记册，凡带夹具标记（synthetic_duplicate/duplicate_of/conflict_opinion 等）或结构残缺的记录进 quarantine，不参与筛查但逐条登记去向并嵌入 result.json；对署名文献清单做逐字段元数据法证（DOI/年份/第一作者/期刊，判 authentic/mismatch/absent）。信任门放行的记录才进入轻量筛查（年份窗+术语命中），integrity_report 作为一等公民字段按 output_contract 装配 result.json。适用于有限快照文献筛查前的数据验真、夹具登记、清单核验。不适用：全网实时检索、替冲突证据做学术裁决。
---

# snapshot-forensics — 上游数据真实性取证

**核心立场：在信任任何一条记录之前先做取证——筛查的可靠性上限，就是输入数据的可靠性上限。**

本技能的重心在**取证**：文件指纹、解析取证、隔离登记册、署名清单元数据法证
是最厚的环节；筛查刻意保持轻量（年份窗 + 术语命中），且只对信任门放行的记录
执行。两条命令完成一个案例，模型判断可以为零。

## 运行契约（平台环境）

- 输入：`/input/case.json`（含 `case_id`、`research_question`、`output_contract`，
  可能内嵌 `attributed_papers`/`references`/`refs` 署名清单）、`/input/task.md`、
  快照导出文件（JSON/JSONL/CSV/TSV/RIS）。
- 中间产物：`/app/work`（取证报告、隔离登记册、可信记录）；最终交付：
  `/app/output`（含 `result.json`）。
- `result.json` 必含 `case_id` 与 `output_contract` 列出的**每一个**字段
  （动态读取契约，禁止硬编码字段名），外加 `status`（complete/partial/blocked）、
  `sources`、`uncertainty`；填不了的字段留空容器并在 `field_notes`/`uncertainty`
  写明原因——**"没有"与"漏了"必须有书面区分**。
- 本技能目录记为 `SKILL_DIR`（通常 `/skills/weekly-skill`）；非平台环境换成实际路径。
- 仅 Python 3 标准库（≥3.8），零网络。**预算纪律**：两条命令约 1 分钟跑完；
  先把取证产物落盘，再装配结果，任何中断都留下可复核的取证证据。

## 标准流程（两条命令）

```bash
# 1) 取证：逐文件 sha256 指纹 + 解析取证（记录数/键分布/异常行）
#    → 信任门：夹具标记/结构残缺记录进隔离登记册（登记去向，不筛查）
#    → 署名清单逐字段元数据法证（authentic/mismatch/absent + 差异明细）
python3 SKILL_DIR/scripts/forensics.py \
    --case /input/case.json --input-dir /input --work /app/work

# 2) 信任门后筛查（年份窗 + 术语命中，轻量自写实现）
#    → 按 output_contract 动态装配 result.json，integrity_report 为一等公民字段
python3 SKILL_DIR/scripts/gated_screen.py \
    --case /input/case.json --work /app/work --out /app/output
```

判据细节见 `references/trust-model.md`（信任门三判据、三集合语义）与
`references/metadata-forensics.md`（逐字段比对规则、夹具处理纪律、已知局限）。

## 产物清单

| 路径 | 内容 |
|-|-|
| `/app/work/forensics_report.json` | 逐文件取证：sha256/字节/格式/记录数/键分布/异常行/解析失败 + 总计数 |
| `/app/work/quarantine.jsonl` | 隔离登记册：qid、类别、夹具标记、去向（disposition）、一句人话理由 |
| `/app/work/trusted_records.jsonl` | 信任门放行的记录（含 metadata_warnings） |
| `/app/work/metadata_forensics.json` | 清单逐篇法证：authentic/mismatch/absent + 逐字段比对明细 |
| `/app/output/result.json` | 按契约装配：integrity_report 与 quarantine_register 原样嵌入 |
| `/app/output/ledger.jsonl` | 逐条筛查台账（仅可信记录）：rid、处置、理由码、命中词 |
| `/app/output/candidates.json` | 纳入集 + 派生条款（年份窗/术语/命中阈值） |

## 异常处理（诚实降级，退出码诚实）

- case.json 缺失/损坏或输入目录不存在：forensics 落盘报告并 `exit=2`，
  指明缺什么；gated_screen 交付 `status=blocked` 骨架 `exit=1`。
- 某文件整体解析失败：记入 forensics_report 的 `parse_error`，其余文件继续；
  单行损坏（JSONL 坏行等）记为异常行，均进入 uncertainty——不静默丢弃。
- 快照零记录：`status=blocked`（gated_screen `exit=2`），如实说明
  "有限快照之外的世界不存在"，不补造文献。
- 无署名清单：`no_reference_list` 事实声明，写入 uncertainty，不阻塞筛查。
- 夹具标记（synthetic_duplicate / conflict_opinion 等）：隔离登记并嵌入
  `quarantine_register`；冲突意见只登记为争议证据，**不做学术裁决**。
- 清单与快照元数据不一致：`mismatch` 逐项列出"清单值 vs 快照值"，
  不替用户裁决哪边对，状态降为 partial。

## 最小调用示例（合成示例，非正式案例结果）

`examples/minimal/` 内含合成 case.json（10 个契约字段、3 篇合成清单）与两个
合成快照文件共 9+1 条记录，刻意包含：夹具合成重复、冲突意见夹具、一条年份与
清单不一致的记录（AP-2：清单 2023 vs 快照 2022）、一条不在快照中的清单文献
（AP-3）、一条缺标题的结构残缺记录、一条 JSONL 坏行、正常可纳入记录。实测输出：

```
forensics.py    → {"records_parsed": 9, "trusted": 6, "quarantined": 3,
                   "metadata_verdicts": {"authentic": 1, "mismatch": 1, "absent": 1}}  (exit 0)
gated_screen.py → {"status": "partial", "candidates": 3, "quarantined": 3,
                   "uncertainty_items": 5}  (exit 0)
```

partial 的原因（全部如实写入 uncertainty）：AP-2 年份不一致、AP-3 快照中缺失、
1 条冲突意见夹具已登记待人工、1 条 JSONL 坏行、1 条弱命中记录待复核。
完整输出见 `examples/minimal/expected/`（由上述命令真实生成）。

## 复用与维护

- 换领域：gated_screen.py 顶部 `LEXICON` 是声明式小词表，按领域增删即可；
  取证逻辑（本技能的重器）与领域无关，无需改动。
- 换契约：无需改代码——契约字段全部从 case.json 动态读取，未知字段自动留空
  并写 field_notes。
- 换夹具标记：forensics.py 顶部 `FIXTURE_MARKERS` 单一事实来源。
- 版本：v1.0（2026-11，Python ≥3.8，stdlib only）。
