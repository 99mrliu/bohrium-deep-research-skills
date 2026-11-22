# 最小调用示例（示意，非正式案例结果）

> 本示例仅说明接口与流程；输入为合成案例，输出为示意，不冒充正式案例结果。

## 输入（/input）

```
case.json                      {"case_id":"DEMO","mode":"create","slide_count":10,"audience":"评审","time_minutes":12}
material.json                  {"title":"示例论文","files":["paper.pdf"]}
artifacts/slide-workorder.json {"total_slides":10,"required_roles":["title","background","method","result","conclusion"]}
paper.pdf                      论文原文
target-template.pptx           组织方模板
```

## 调用

```bash
export CASE_INPUT_DIR=/input CASE_WORK_DIR=/app/work CASE_OUTPUT_DIR=/app/output
S=/skills/weekly-skill/scripts
python3 $S/survey.py          # -> case_brief.json + requirements.json（12 条门禁）
python3 $S/mine_paper.py      # -> paper_digest.md + assets/figures/fig*.png
python3 $S/plan_scaffold.py   # -> plan.json 骨架（10 页角色已分配）
#   …模型编辑 plan.json（读 paper_digest.md）…
python3 $S/gate.py plan       # -> {"pass": true, "hard": 0, "warn": 1}
python3 $S/build_deck.py      # -> presentation.pptx
python3 $S/render.py          # -> presentation.pdf + previews/slide-01..10.png
python3 $S/gate.py deck       # -> {"pass": true, ...}
python3 $S/result.py          # -> result.json  {"status":"completed","fails":[]}
```

## 示意输出（节选，标注为示例）

```json
{
  "case_id": "DEMO",
  "status": "completed",
  "editable_source": {"path": "presentation.pptx", "slides": 10, "mode": "create"},
  "export_artifact": {"pdf": "presentation.pdf", "preview_pages": 10},
  "content_map": [{"slide": 4, "role": "result", "title": "…", "anchors": ["p5", "fig2"], "figure": "fig2"}],
  "compliance_checks": {"G06-anchor-numbers": {"status": "pass", "evidence": "0 处数字未命中锚点"}},
  "exceptions": []
}
```

门禁失败示例：`[hard] S5: 数字 3.14 未命中锚点 p4（论文中不存在，疑似编造）` → 修正 bullet 或锚点后重跑 `gate.py plan`。
