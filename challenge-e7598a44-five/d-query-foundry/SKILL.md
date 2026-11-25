---
name: d-query-foundry
description: 科研问题驱动检索的"查询锻造炉"——以术语与查询工程为重心的检索技能。从 research_question 机械派生查询族（拉丁词/CJK 整词与二元组/内置跨语词表扩展/连字符·单复数·缩写变体，变体生成设双重预算上限防发散），在有限快照上执行布尔/短语查询并输出逐查询×记录的命中位置证据；再把署名清单当作 known items 做召回审计（每篇：被哪些查询命中、排第几、missing 时诊断快照缺席/年份出窗/术语缺口），产出逐查询精准·噪声画像并按 output_contract 装配 result.json。适用于有限快照的可复核检索、查询质量诊断、known-item 召回验证。不适用：全网实时检索、单篇精读、替冲突证据做学术裁决。
---

# d-query-foundry — 术语与查询工程驱动的检索锻造

**核心立场：检索质量不靠换更大的词表，而靠把"RQ→查询族→命中证据→召回诊断"
做成一条每一步都可复算的流水线。**

本技能的重心在**术语与查询工程**：查询构造是重器（术语基座、变体规则、预算
上限、命中位置证据），筛查条款保持轻量；署名清单不当答案抄，而当 known items
用来审计查询族的召回，missing 必须诊断出具体缺口。两条命令完成一个案例，
全程确定性、零模型判断。

## 运行契约（平台环境）

- 输入：`/input/case.json`（含 `case_id`、`research_question`、`output_contract`）、
  `/input/task.md`、快照导出文件（JSON/JSONL/CSV/TSV/RIS，以实际内容为准）。
- 中间产物：`/app/work`；最终交付：`/app/output`（含 `result.json`）。
- `result.json` 必含 `case_id` 与 `output_contract` 列出的**每一个**字段
  （动态读取契约，禁止硬编码）；填不了的字段留空容器并在 `field_notes`/
  `uncertainty` 说明原因（诚实 partial）。
- 本技能目录记为 `SKILL_DIR`（通常 `/skills/weekly-skill`）；非平台环境换成实际路径。
- 仅 Python 3 标准库（≥3.8），零网络。**预算纪律**：两条命令约数秒跑完；
  变体生成受 `--max-variants-per-term`/`--max-variant-total` 双重上限，
  查询总数受 `--max-queries` 上限，截断量如实落盘；输入级故障立即写
  `status=blocked` 骨架退出，任何中断都有可交付的诚实结果。

## 标准流程（两条命令）

```bash
# 1) 查询族锻造：RQ → 术语基座（拉丁词/CJK 整词·二元组/跨语词表/缩写扩展）
#    → 变体（连字符·单复数·缩写，预算上限内）→ 查询族（phrase/and2/term）
#    → 快照执行（逐命中带 field/offset/snippet 证据）→ 轻量筛查台账与候选集
python3 SKILL_DIR/scripts/foundry.py \
    --case /input/case.json --input-dir /input --work /app/work --out /app/output

# 2) known-item 召回审计 + 契约装配：署名清单逐篇审计（命中查询/排名/missing 诊断），
#    逐查询画像（命中数/known 命中/噪声估计），按 output_contract 装配 result.json
python3 SKILL_DIR/scripts/known_item_audit.py \
    --case /input/case.json --input-dir /input --work /app/work --out /app/output --finalize
```

可选调参：变体/查询预算用 `--max-variants-per-term`、`--max-variant-total`、
`--max-queries`；审计不加 `--finalize` 时只产出审计文件、不写 result.json。
查询语法与筛查条款见 `references/query-syntax.md`；变体规则表与诊断码见
`references/variant-rules.md`。

## 产物清单

| 路径 | 内容 |
|-|-|
| `/app/output/result.json` | 按契约装配的最终结果（含 status/sources/uncertainty/field_notes） |
| `/app/output/query-report.json` | 逐查询画像：命中数、known-item 命中、噪声估计、各族汇总 |
| `/app/output/known-item-audit.json` | 每篇清单文献：匹配记录、命中查询与排名、missing 诊断码 |
| `/app/output/candidates.json` | 纳入集（含命中 qids）与年份窗/计数 |
| `/app/output/query-execution.json` | 逐查询命中 rid 清单 |
| `/app/output/screening-ledger.jsonl` | 逐条处置台账（理由码 + 命中 qids + 夹具登记） |
| `/app/work/` | records/ingest-report/term-base/query-families/hits（逐步可复算） |

## 异常处理（诚实降级）

- case.json 缺失/损坏：写 `status=blocked` 骨架并 exit=2，指明缺什么。
- 快照零记录或全部解析失败：blocked 骨架 exit=2，不补造文献。
- **RQ 无可用术语**（拉丁词/CJK 切词/词表扩展均为空）：无法锻造查询族，
  blocked 骨架 exit=2——宁可 blocked 也不臆造查询词。
- 署名清单缺失：审计标 `no_reference_list`，写入 uncertainty，照常 finalize（partial）。
- 审计前置产物缺失（未先跑 foundry）：exit=2 并写 blocked 骨架。
- 清单文献 missing：**不是错误而是发现**——exit=0，诊断码逐项给出
  （snapshot_absent/year_gap/doctype_gap/term_gap 等），修复入口见
  references/variant-rules.md 第 4 节。
- 夹具标记：合成重复登记不入候选；冲突意见登记为争议证据并写入
  uncertainty，**不做学术裁决**。

## 最小调用示例（合成示例，非正式案例结果）

`examples/minimal/` 内含合成 case.json（9 契约字段、3 篇清单文献）与 9 条
合成快照记录（含中文标题记录、合成重复夹具、冲突意见夹具、2019 年出窗文献）。
实测输出：

```
foundry.py          → {"records": 9, "terms": 30, "variants": 22,
                       "queries": 40, "queries_truncated": 5,
                       "hits": 130, "candidates": 6}          （exit 0）
known_item_audit.py → {"known_items": 3, "recalled": 2, "missing": 1,
                       "candidates": 6, "status": "partial"}  （exit 0）
```

审计显示 known-item 召回 **2/3**：K1/K2 recalled（各被 20 个查询命中）；
K3 missing，诊断出双重缺口——`year_gap`（2019 年在 RQ 年份窗 [2021,2024] 之外，
查询虽已召回但被年份条款排除）与 `term_gap`（pore/engineered 等标题术语未被
查询族覆盖）。`status=partial` 的原因（K3 missing + 冲突意见夹具 R009 已登记）
如实写入 uncertainty。完整输出见 `examples/minimal/expected/`。

异常路径已演练：RQ 仅含停用字（"的 了 和 或 与"）时 foundry exit=2 并写
blocked 骨架；清单删除后审计标 `no_reference_list` 照常交付 partial；
未跑 foundry 直接审计 exit=2。三者均诚实降级、不臆造。

## 复用与维护

- 换领域：`foundry.py` 顶部 `XLEX`（跨语词表）与 `ABBR`（缩写表）是声明式
  词表，按领域增删即可；领域外 RQ 自动退化为拉丁词 + CJK 切词。
- 换契约：无需改代码——契约字段全部从 case.json 动态读取，空字段自动写
  field_notes。
- 修缺口：按 known-item 审计的 `term_gap` 清单补词表或改写 RQ 后整体重跑，
  确定性保证同输入同输出。
- 版本：v1.0（2026-11，Python ≥3.8，stdlib only）。
