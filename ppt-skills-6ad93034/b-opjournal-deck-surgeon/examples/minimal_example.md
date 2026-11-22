# 最小调用示例（示意，非正式案例结果）

> 仅说明接口与流程；输入为合成案例，输出为示意。

## 输入（/input）

`case.json`（10 页/评审/12 分钟）、`material.json`、`artifacts/slide-workorder.json`、`paper.pdf`、`target-template.pptx`；edit 模式另有 `starting-deck.pptx`。

## 调用

```bash
export CASE_INPUT_DIR=/input CASE_WORK_DIR=/app/work CASE_OUTPUT_DIR=/app/output
S=/skills/weekly-skill/scripts
python3 $S/intake.py            # v000 快照 + 论文简报 + 图裁剪
python3 $S/op.py init           # 开册
#   …模型读 paper_brief.md，写 work/ops_round1.json …
python3 $S/op.py add work/ops_round1.json   # -> {"accepted": 38, "rejected": 2}
python3 $S/apply.py             # 重放 -> presentation.pptx + change_journal.md
python3 $S/verify.py            # 独立审计 -> {"pass": true}
python3 $S/render_export.py     # PDF + previews
python3 $S/finalize.py          # result.json
```

## 示意输出（节选，标注为示例）

`change_journal.md`：

```
| # | 操作 | 页 | 理由 |
|-|-|-|-|
| 5 | set_bullets | 4 | 补充 p8 主结果数据（大模型英德翻译 28.4 BLEU…） |
| 7 | insert_figure | 3 | 架构图支撑方法页（fig1） |
```

`result.json` 节选：

```json
{"status":"completed",
 "editable_source":{"built_by":"op-journal replay (41 ops onto v000)"},
 "change_records":{"journal_ops":41,"snapshots":["v000_base.pptx","v001.pptx"],
                   "rollback":"python3 op.py rollback N && python3 apply.py"},
 "compliance_checks":{"V-slide_count":{"status":"pass","evidence":"10/10"}}}
```

回退示意：`python3 $S/op.py rollback 3 && python3 $S/apply.py` → 成稿精确回到三条操作之前，被回退操作留档 `journal.rejected.jsonl`。
