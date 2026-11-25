---
name: paragraph-alignment-ledger-translation
description: >-
  当科研翻译案例的核心风险是"长文跨页、跨栏、跨章节时漏段、重复、错位，段号无法与原文一一对应"时使用本 Skill。
  Use when a scientific-translation case (/input/case.json + task.md + source) requires paragraph-completeness-governed translation: deterministic semantic segmentation into headed paragraphs/captions/formulas/list items with stable IDs (p001…), column-wrap and page-break repair with an explicit repair report (never silent), a coverage ledger that binds every translation to its source block by content hash (stale/duplicate/missing/out-of-order detection), paragraph-wise translation with previous-tail context carry, paragraph-level bilingual alignment output (id ↔ source ↔ target ↔ kind ↔ anchor) and contract-driven result.json with case_id and every output_contract field plus honest partial status.
  不做的事：不把视觉块当语义段、不静默连接连字符、不漏段重段后不报告、不用文件路径代替译文内容。
---

# paragraph-alignment-ledger-translation（段落级双语对齐与覆盖台账，Bundle B）

本 Skill 的重心是**段落完整性**：源文被切成带稳定 ID 的语义块，译文必须逐块回填到台账，
由脚本证明"不漏、不重、不错位"，并输出段号一一对应的双语对照。翻译由 Agent 完成；
脚本负责分段、修复记录、覆盖核验与对齐组装——完整性的证据是机器可验的。

## 何时使用 / 边界

**适用**：全文或长区间翻译、跨页/跨栏/跨章节材料、评分关注段落覆盖与段号对应的案例。
**不适用**：只译单句或术语卡的微任务（杀鸡用牛刀但仍可用）；扫描件无文字层时只能对可抽取
部分建台账，残缺部分必须显式标注。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md` + 源文件。
- 中间产物（`/app/work/alignjob/`）：`segments.json`（带 ID 与修复记录）、`ledger.json`、`translations.json`、`coverage_report.json`。
- 交付（`/app/output/`）：`result.json`（`case_id` + 合同全部必填字段）、`bilingual.md`（逐段对照）、`coverage_report.json`。
- 诚实 partial：缺失段写入 `status=partial` 与 exceptions，绝不用摘要补齐未译段。

## 精确命令工作流

```bash
# 0. 定向
cat /input/case.json /input/task.md; ls -la /input
export SKILL_DIR=$(dirname $(find /skills -maxdepth 3 -name SKILL.md -path '*paragraph-alignment*' 2>/dev/null | head -1))
S=$SKILL_DIR/scripts; W=/app/work/alignjob; O=/app/output; mkdir -p $W $O

# 1. 取源文并分段（页分隔 \f、空行分段、Figure/Table 题注、独立公式行、列表项分别成块）
python3 $S/segment_docs.py --input /input --out $W/segments.json
#    跨栏换行修复（行尾连字符断词、段中单换行）逐条记入 repair_report，不静默改。
python3 $S/segment_docs.py repair-report --segments $W/segments.json --out $W/repair_report.md

# 2. 初始化覆盖台账（每块 status=pending + source_sha256）
python3 $S/coverage.py init --segments $W/segments.json --out $W/ledger.json

# 3. Agent 逐段翻译（携带上一段已译尾部作上下文），写入 translations.json：
#    [{"id":"p003","source":"<与 segments.json 完全一致>","translation":"…"}]
#    回填时脚本校验 id 存在且 source 与台账哈希一致（防错位/防陈旧）。
python3 $S/coverage.py list-pending --ledger $W/ledger.json        # 每批前看剩余
python3 $S/coverage.py apply --ledger $W/ledger.json --translations $W/translations.json

# 4. 覆盖核验 + 对齐导出（缺段/重段/乱序 → exit 1，诚实 partial 也不得跳过）
python3 $S/coverage.py report --ledger $W/ledger.json --out $W/coverage_report.json
python3 $S/align_export.py --case /input/case.json --ledger $W/ledger.json \
    --translations $W/translations.json --out $O
```

`result.json` 按合同字段填充：完整译文为全部已译块按段序拼接；`bilingual` 为
`[{id, kind, source, target, anchor}]`；`uncertainties` 含缺失段与修复说明；
`status` 规则：全部块已译且无缺失 → `success`，否则 `partial`。

## 分段与修复纪律

- 段 ID 全任务稳定：`p001…` 按源文顺序编号；追加内容用新 ID，不重排旧 ID。
- 修复只处理两类跨栏伪影：行尾硬连字符断词（`bounda-\nry` → `boundary`，记录）、
  段内单换行（合并为空格，记录）。语义分段（真段落边界）不因排版改变而合并。
- 题注（Figure/Table 开头块）、公式块、列表项是独立块类型，不并入正文段。
- `apply` 拒绝：未知 ID、source 哈希与台账不符（错位/陈旧）、同一 translations.json 中重复 ID。

## 最小调用示例（合成示例，非正式案例结果）

`examples/source_paged.txt` 是一段**合成的**两栏论文摘录（含 `\f` 分页、行尾断词、
段中单换行、Figure/Table 题注与一行公式）。`run_example.sh` 跑通 分段→台账→回填→核验→导出，
并断言：(a) 断词与单换行被修复且逐条留痕；(b) 缺段/重复回填被拒绝或检出；(c) 完整回填后
覆盖报告全绿、`result.json` 合同字段齐全。示意输出见 `examples/example_output/`。

## 预算、可靠性与限制

- 官方包线 64 请求 / 900 秒：分段与核验为脚本零请求；翻译按段批处理，每批携带上一段尾部。
- 稳定性：全部脚本幂等；`coverage.py apply` 可重复导入（哈希相同则跳过），中断后从
  `list-pending` 续跑。
- 异常处理：无文字层/乱码段 → 该块标 `unreadable` 进 uncertainties；源文残缺 → partial。
- 限制：启发式分段对代码块与复杂表格可能切分不理想，须人工目检首末段；覆盖核验证明
  "块级不漏不重"，不证明句级语义正确。
