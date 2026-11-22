# 最小调用示例（示意，非正式案例结果）

> 仅说明接口与流程；输入为合成案例，输出为示意。

## 输入（/input）

`case.json`（评审受众 / 15 分钟 / 12 页）、`material.json`、`artifacts/slide-workorder.json`、`paper.pdf`、`target-template.pptx`。

## 调用

```bash
export CASE_INPUT_DIR=/input CASE_WORK_DIR=/app/work CASE_OUTPUT_DIR=/app/output
S=/skills/weekly-skill/scripts
python3 $S/brief.py        # 逐页秒数预算 + 论文摘要 + 术语表 + 图裁剪
#   …模型读 paper_notes.md 与 time_budget.json，撰写 work/talktrack.md …
python3 $S/lint_track.py   # -> {"pass": true, "total_seconds": 880}
python3 $S/compile_deck.py # 讲稿派生 presentation.pptx
python3 $S/export_deck.py  # PDF + previews + 空白页检测
python3 $S/wrap_up.py      # 终检 + result.json + talktrack.md 交付
```

## talktrack.md 片段（示意）

```
[S6 | 90s | 主结果：英德翻译新 SOTA]
这一页是全文最重要的数字：大模型在 WMT 2014 英德任务上达到 28.4 BLEU，
比此前包括集成模型在内的最好结果高出 2.0 以上，而训练成本显著更低。
- 大模型英德翻译 28.4 BLEU，超前作 2.0 以上 (anchor p8)
- 训练成本远低于同期模型 (anchor p8)
```

## 示意输出（节选，标注为示例）

```json
{"status":"completed",
 "editable_source":{"built_by":"talktrack compile（讲稿派生幻灯片）"},
 "content_map":[{"slide":6,"seconds":90,"budget_seconds":95,"role":"result",
                 "anchors":["p8"],"figure":null,"notes_chars":78}],
 "time_summary":{"budget_total_s":900,"planned_total_s":880},
 "compliance_checks":{"T01-talktrack-lint":{"status":"pass"}}}
```
