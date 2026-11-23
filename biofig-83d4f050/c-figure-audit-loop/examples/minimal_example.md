# 端到端最小示例（合成数据，仅演示流程）

> 本示例全部使用 `assets/claims.example.json`（合成玩具通路，5 实体 / 4 条类型化边 /
> 1 个 log2FC 填充编码 / 4 个图例项 / 3 条 color_checks）。所有来源定位均为虚构。

```bash
SKILL=/path/to/skill
W=$(mktemp -d)/work && mkdir -p "$W"

# 1) 主张表 -> SVG
python3 $SKILL/scripts/mini_svg_builder.py \
    --claims $SKILL/assets/claims.example.json --out "$W/figure.svg"

# 2) 导出 PNG (300dpi) + PDF
python3 $SKILL/scripts/export_with_mpl.py \
    --claims $SKILL/assets/claims.example.json \
    --png "$W/figure.png" --pdf "$W/figure.pdf"

# 3) 一键审计 —— 期望 0 errors（skipped 若干：pdffonts/tesseract 若缺失）
python3 $SKILL/scripts/audit_run.py \
    --claims $SKILL/assets/claims.example.json \
    --svg "$W/figure.svg" --png "$W/figure.png" --pdf "$W/figure.pdf" \
    --out "$W/audit1"
echo "exit=$?"   # 0
```

预期输出片段：

```
semantic_diff: 0 errors, 0 warnings
pixels: 0 errors, 0 warnings, 1 skipped      # tesseract 缺失 -> skipped（不算通过）
exports: 0 errors, 0 warnings, 1 skipped     # pdffonts 缺失 -> skipped
summary: 0 errors, 0 warnings, 2 skipped
```

## 故意破坏 → 审计必须逐条抓出

```bash
# （演示用）破坏三件事：
#  a) 把 edge:e2 的 data-from/data-to 互换        -> edge.direction_reversed [error]
#  b) 删除图例项 legend-swatch:uncertain_edge      -> legend.missing_item   [error]
#  c) 把 legend-swatch:log2FC_low 色块改成 #00ff00 -> color.check           [error]
python3 - "$SKILL" "$W/figure.svg" "$W/figure_broken.svg" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import svg_conventions as C
tree = C.parse_svg(sys.argv[2]); root = tree.getroot()
g = C.find_by_id(root, "edge:e2")
g.set("data-from", "ADAPTOR"); g.set("data-to", "RTK")          # a
for p in root.iter():
    for ch in list(p):
        if ch.get("id") == "legend-swatch:uncertain_edge":
            p.remove(ch)                                        # b
sw = C.find_child_by_class(C.find_by_id(root, "legend-swatch:log2FC_low"),
                           "swatch", "rect")
sw.set("fill", "#00ff00")                                       # c
tree.write(sys.argv[3], encoding="utf-8", xml_declaration=True)
PY
python3 $SKILL/scripts/audit_run.py --claims $SKILL/assets/claims.example.json \
    --svg "$W/figure_broken.svg" --png "$W/figure.png" --out "$W/audit2"
echo "exit=$?"   # 1
```

## 写 ops → 修复循环 → 复验清零

```bash
cat > "$W/ops.json" <<'JSON'
[
  {"op": "swap-edge-direction", "edge": "e2"},
  {"op": "add-legend-item", "item": "uncertain_edge",
   "meaning": "dashed edge = uncertain evidence", "color": "#999999"},
  {"op": "set-fill", "target": "legend-swatch:log2FC_low", "color": "#2166ac"}
]
JSON
# 注意：色块修复后需重新导出 PNG 才能让像素审计复验通过
python3 $SKILL/scripts/export_with_mpl.py --claims $SKILL/assets/claims.example.json \
    --png "$W/figure.png"
python3 $SKILL/scripts/fix_loop.py --svg "$W/figure_broken.svg" \
    --claims $SKILL/assets/claims.example.json --ops "$W/ops.json" \
    --png "$W/figure.png" --workdir "$W/fix"
echo "exit=$?"   # 0；journal 在 $W/fix/fix_journal.json
```

## 编辑类 case 的对拍

```bash
# claims 中含 edit_expectations: {"changed_elements": ["entity:TF"],
#                                 "unchanged_sample": ["entity:RTK", "edge:e1"]}
python3 $SKILL/scripts/audit_run.py \
    --claims claims_edit.json --svg after.svg --before-svg before.svg --out "$W/audit3"
# entity:TF 的标签被改了 -> 通过；若 RTK 或 e1 有任何字节级差异 -> error
```

## 组装 result.json

```bash
python3 $SKILL/scripts/build_result.py --case-id demo-synthetic --status partial \
    --editable-source "$W/figure.svg" --editable-source "$SKILL/assets/claims.example.json" \
    --export-artifact "$W/figure.png" --export-artifact "$W/figure.pdf" \
    --out "$W/result.json"
# status=partial 因为演示环境里 pdffonts/tesseract 的 skipped 需要如实声明
```
