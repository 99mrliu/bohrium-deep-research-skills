# 最小端到端调用示例（示例 / SYNTHETIC —— 非真实案例结果）

> 本示例演示技能管线的完整走法。所有实体、关系、数据均为**合成玩具内容**，
> 不来自任何真实案例，严禁当作真实案例交付物。真实案例必须从 `/input` 的实际
> 材料派生一切内容。

## 输入速写（synthetic）

- 任务：画一条玩具通路 LIGAND-X → RcptA → KinB →(磷酸化) TFc → *TargetD*，
  RepE ⊣ KinB；并从 `example-data.csv` 画一张散点图。
- 材料：`assets/example-mechanism.tex`（成品参考）、`assets/example-chart.tex`、
  `assets/example-data.csv`。

## 命令序列

```bash
# 0. 准备工作目录，复制图元库与素材
mkdir -p /app/work /app/output
cp assets/biopathway.tex assets/example-mechanism.tex \
   assets/example-chart.tex assets/example-data.csv /app/work/

# 1. 阶段1产物（本例跳过真实提取，直接给 synthetic claims）
cat > /app/work/claims.json <<'EOF'
{"entities":[{"id":"RcptA","type":"receptor","locator":"synthetic"},
             {"id":"KinB","type":"protein","locator":"synthetic"}],
 "edges":[{"from":"KinB","to":"TFc","relation":"phosphorylation","locator":"synthetic"}],
 "values":[],"uncertain":[]}
EOF

# 2. 阶段2：.tex 已就绪（example-mechanism.tex / example-chart.tex）

# 3. 阶段3：编译（本机无 latex 引擎时的诚实输出见下）
python3 scripts/compile_tex.py --tex /app/work/example-mechanism.tex --workdir /app/work
#   无引擎 → exit 3, {"success": false, "error": "no latex engine", ...}
#   有引擎 → {"engine":"pdflatex","success":true,"pdf_path":"/app/work/example-mechanism.pdf",...}

# 4. 阶段4：导出（有 PDF 后）
python3 scripts/export_previews.py --pdf /app/work/example-mechanism.pdf \
    --out-dir /app/output --basename mechanism --dpi 300

# 5. 阶段5：校验
echo '["LIGAND-X","RcptA","KinB","TFc","TargetD","RepE","Legend"]' > /app/work/labels.json
python3 scripts/verify_tex_figure.py --pdf /app/output/mechanism.pdf \
    --png /app/output/mechanism.png --labels-file /app/work/labels.json

# 6. 编辑演示：把 TFc 改名 p-TFc 并把 protein 填充色调深
cat > /app/work/ops.json <<'EOF'
[{"op":"replace-label","old":"TFc","new":"p-TFc"},
 {"op":"set-color","target":"protein","color":"bpblueL!70"}]
EOF
python3 scripts/apply_tex_edit.py --tex /app/work/example-mechanism.tex \
    --ops /app/work/ops.json --edit-record /app/work/edit-record.json

# 7. 组装 result.json（第一份可编译图出现后就应立即先写 partial 版）
python3 scripts/build_result.py --case-id synthetic-demo --status partial \
  --limits "演示环境无 latex 引擎：仅交付 .tex 源与校验脚本输出" \
  --editable-source /app/work/example-mechanism.tex \
  --content-map /app/work/content_map.json \
  --compliance /app/work/compliance.json \
  --exceptions /app/work/exceptions.json \
  --out /app/output/result.json
```

## 预期产物

| 产物 | 说明 |
|---|---|
| `/app/work/example-mechanism.tex`（或改名后的 figure.tex） | 可编辑 TikZ 源（editable_source） |
| `/app/work/versions/example-mechanism.v1.tex` | 编辑前的版本备份（自动） |
| `/app/work/edit-record.json` | 编辑日志（timestamp/op/before/after/result） |
| `example-mechanism.pdf` / `.png`（300 DPI）/ `.svg` | 编译与导出件（有引擎/导出器时） |
| 校验 JSON | fonts_embedded / labels_present / pixel_probe 逐项 pass|fail|skipped |
| `/app/output/result.json` | 合同字段齐备；本例在真实评测环境下应为 partial（合成演示） |
