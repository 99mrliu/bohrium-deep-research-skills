---
name: snapshot-veritas-audit
description: Audit the authenticity and provenance of an authorized scientific data snapshot (SQLite) before any analysis. Use when a case provides database files whose identity, dataset version, or integrity must be established — fingerprint the snapshot, match it against reference cards of known public datasets (UCI Concrete 1030 / Iris 150 including the bezdek variant / Wine 178), discriminate variants, and gate downstream analysis on an honest VERIFIED / DRIFT / NO_CARD verdict. 上游数据真实性：快照指纹、参考卡比对、变体识别、漂移报告。
---

# Snapshot Veritas Audit：上游数据真实性与溯源审计

本 Skill 的重心是**输入数据本身是否可信**——在写出任何查询之前，先回答三个问题：收到的是什么数据集、是哪个版本/变体、是否被增删改。下游一切数字都建立在这次审计的 verdict 上；verdict 为 DRIFT 时，先报告差异再分析，绝不静默修复数据。

## 运行约定（先读）

先读 `/input/case.json` 与 `/input/task.md`（若有 `environment/resources.yaml` 也读）。`case.json` 的 `output_contract` 决定 `/app/output/result.json` 必须包含的字段：**按其原样填写，含原始 `case_id`，不改名、不遗漏**。在 `/app/work` 下工作，交付物写入 `/app/output`。预算约 900 s / 64 次模型请求：**第一步就先写一个 `status: "partial"` 的合法 result.json**（含 output_contract 全部字段、当前进度与限制说明），之后就地改进为 `complete`。只读真实文件，不从文件名或领域标签臆测数据内容。技能目录解析顺序：`/skills/weekly-skill` → `$WEEKLY_SKILL` → 本 `SKILL.md` 所在目录。

## 输入

- 授权数据快照：`/input` 下的 SQLite 文件（`*.db/*.sqlite*`）。**一律只读打开**（`mode=ro`），本 Skill 从不写入源库。
- 任务说明与（可选的）任务方数据字典。任务方提供的字典优先级高于本 Skill 的参考卡。

## 工作流

1. **契约兜底。** 读 case.json，立即写 `/app/output/result.json`（partial）：填入 case_id、output_contract 全部字段（未知值先给 `unable_to_determine` 并注明待补）、本 Skill 名、计划步骤。
2. **快照指纹。** 运行 `python <skill>/scripts/fingerprint.py --input /input --out /app/work/fingerprint.json`。得到每个库文件的 sha256、每表行数、每列类型/空值/取值/数值统计。指纹是一切后续结论的"收到时的原状"记录。
3. **真实性核验。** 运行 `python <skill>/scripts/verify_snapshot.py --fingerprint /app/work/fingerprint.json --cards <skill>/references/reference_cards.json --out /app/work/verdict.json --md /app/work/verdict.md`。每张表得到 VERIFIED / DRIFT / NO_CARD 判定、命中卡片及其来源、逐列漂移清单、同族变体列表（如 iris 两个变体）。判定口径见 `references/authenticity_rules.md`。
4. **按 verdict 分派后续分析。** VERIFIED：正常分析，报告引用指纹 sha256 与 verdict。DRIFT：把 drift 清单写入 `analysis_notes.md` 与 result.json 的异常/不确定性字段，在漂移快照上分析并声明口径，**不修复数据**。NO_CARD：正常分析，但声明无外部金标准、以指纹为唯一溯源记录；若任务方声称这是某已知数据集而核验不符，按 DRIFT 如实报告矛盾。
5. **完成案例要求的分析。** 真实性审计不代替题目本身的查询/统计/可视化任务——用题目要求的方法完成它（可用任意 SQL/脚本），但报告中每个涉及数据身份的表述都必须能回指 verdict.json。
6. **交付。** `/app/output/` 至少含：按 output_contract 填好的 result.json（status 改 `complete`，注明 verdict、快照 sha256、不确定性）、fingerprint.json、verdict.json/verdict.md、分析产物与 `analysis_notes.md`（含异常清单与未覆盖部分）。

## 异常处理

| 情况 | 处置 |
|-|-|
| /input 无任何数据库文件 | 列出实际文件清单；result.json 报 `unable_to_determine` 并说明缺失；不虚构数据。 |
| 库文件打不开/损坏 | verdict 记 UNREADABLE，附错误信息；尝试其余文件。 |
| 任务声明的数据集与核验矛盾 | 以快照为准，报告矛盾双方证据；不迎合声明。 |
| 两个候选卡分数接近 | 报告候选列表与分差，标 `uncertain`，不强行二选一。 |
| 列名全部改写过 | 依赖按列序的统计匹配，证据中注明 `matched_by: position`，置信度降级说明。 |

## 附带脚本与资源

- `scripts/fingerprint.py` — 只读快照指纹（文件哈希、行数、列画像、数值统计、低基列 top 值）。纯标准库。
- `scripts/verify_snapshot.py` — 指纹 × 参考卡 → 判定报告（JSON+Markdown），含变体区分与漂移清单。纯标准库。
- `references/reference_cards.json` — UCI Concrete(1030)、Iris 两个变体(150)、Wine(178) 的参考卡；统计量由 2026-11-24 下载的 UCI 原始文件直接计算，卡内附文件 sha256 与来源。
- `references/authenticity_rules.md` — 判定口径、容差、禁止事项。

## 最小调用示例（合成示例，非正式案例结果）

合成输入：脚本自建一个 150 行的 iris 形态 SQLite 库，但把 sepal_width 一列整体乘以 1.1（模拟上游被改动）。执行：

```
python /skills/weekly-skill/scripts/fingerprint.py --db /tmp/demo/lab.db --out /tmp/demo/fingerprint.json
python /skills/weekly-skill/scripts/verify_snapshot.py --fingerprint /tmp/demo/fingerprint.json \
  --cards /skills/weekly-skill/references/reference_cards.json \
  --out /tmp/demo/verdict.json --md /tmp/demo/verdict.md
```

示意输出（示例，非正式结果）：verdict 命中 `iris-uci-corrected` 或 `iris-bezdek-original` 卡（分数最高），但总体判定为 **DRIFT**，drift 清单列出 `sepal_width_cm` 的 min/max/mean/std 相对偏差约 10%；报告建议"在报告中声明该列与参考卡不符，分析按漂移快照口径进行"。完整可跑脚本见 `examples/run_example.sh`，说明见 `examples/minimal_example.md`。

## 边界与限制

面向单文件 SQLite 快照与≤百万行级表；参考卡只覆盖收录的公开数据集，其余数据集输出 NO_CARD 与完整指纹（仍具溯源价值）；不连接远程库、不做写操作；真实性审计是分析的前置门禁，不替代领域统计判断。
