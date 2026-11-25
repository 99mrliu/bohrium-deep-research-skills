# 最小示例（minimal example）

> **合成示例声明**：本目录中的 `pages.json`、`case.json`、所有
> `extracted/pageNN.txt` 以及全部输出，都是**手工编造的合成数据**
> （synthetic demo）。它们不是正式 case，不来自任何真实论文，仅用于在
> 没有真实 PDF 的环境里端到端验证三个脚本的判定逻辑。

## 这个示例展示什么

一份 10 页的"合成文档"，每一类检测器都至少被触发一次：

| 页 | 设计 | 期望检测器 |
|---|---|---|
| 1, 2, 4, 6 | 正常数字文本页 | 无异常，路由 direct |
| 3 | 有 1 个图像、0 字符 | 扫描页候选 → ocr_handoff |
| 5 | 文本层存在但含 40 个 PUA 字符 + 3 连 U+FFFD + 1 处 `â€` mojibake | glyph_audit 判 high → 改派 ocr_handoff |
| 7 | `/Rotate = 90`，文本层完好 | 旋转页标记 → direct 但注明先回正 |
| 8, 9 | 完全相同的文本指纹 | 重复页 → 9 标记 duplicate_of=8 |
| 10 | 有 2 个图像、仅 3 字符 | 扫描页候选 → ocr_handoff |

## 精确运行命令

```bash
cd skill
EX=examples/minimal
python3 scripts/pdf_probe.py --manifest $EX/inputs/pages.json --out $EX/outputs
python3 scripts/glyph_audit.py $EX/inputs/extracted --out $EX/outputs
python3 scripts/route_decision.py --intake $EX/outputs/intake_report.json \
  --glyph $EX/outputs/glyph_audit.json --case $EX/inputs/case.json \
  --out $EX/outputs
```

退出码依次为 2 / 2 / 2（partial / corrupt / partial route），全部为预期值。

## outputs/ 的来源声明

`outputs/` 下的四份 JSON（intake_report.json、glyph_audit.json、
route_decision.json、result.json）是用上面三条命令**真实运行产生**的，
不是手写或伪造的；产出后逐字段人工核对过：

- `intake_report.json`：status=partial；scanned_pages=[3,10]；
  rotated_pages=[7]；duplicate_pairs=[[8,9]]。
- `glyph_audit.json`：8 个文本文件中仅 page05.txt 被标记，severity=high
  （PUA 比率 15.75% > 0.5%；U+FFFD 连续段 3 > 2）。
- `route_decision.json`：route=mixed_pagelevel；OCR 页=[3,5,10]；
  页 7 注明旋转回正；页 9 注明 duplicate of page 8。
- `result.json`：case_id=SYNTH-DEMO-0001，status=partial（存在扫描页、
  乱码页、旋转页、重复页）；page_map 与 intake_notes 已填充，full_text
  留空并在 uncertainty 中解释（内容抽取不属于本分诊 Skill）。

另做过一次从零复现验证：在全新临时目录中对 committed inputs 重跑三条
命令，关键字段（route、status、scanned/rotated/duplicate 清单、OCR 页
清单、page05 严重度）与 committed outputs 完全一致。
