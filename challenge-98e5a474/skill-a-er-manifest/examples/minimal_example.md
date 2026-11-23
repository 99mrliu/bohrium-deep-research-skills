# 最小调用示例（示例，非正式案例结果）

以下输入与输出均为演示接口用的**示意样例**，不来自正式测试案例。

## 示意输入（来源材料摘录）

> "Upon ligand binding, EGFR activates RAS, which in turn activates RAF.
>  The RAF inhibitor vemurafenib blocks RAF kinase activity. Phosphorylated
>  ERK translocates into the nucleus, where it induces MYC expression."
> ——（示意引句，假设出自 example.pdf 第 2 页）

## 调用方式

```bash
# 1. 按 schema 将上述文字编译为清单（Agent 完成，带引句定位）
$EDITOR /app/work/manifest.json
# 2. 渲染
python3 /skills/weekly-skill/scripts/render_manifest.py \
  --manifest /app/work/manifest.json --svg /app/output/figure.svg \
  --report /app/work/render_report.json
# 3. 对账
python3 /skills/weekly-skill/scripts/verify_figure.py \
  --manifest /app/work/manifest.json --svg /app/output/figure.svg \
  --out /app/output/verification_report.json
# 4. 导出与预览
python3 /skills/weekly-skill/scripts/export_preview.py \
  --svg /app/output/figure.svg --outdir /app/output --basename figure \
  --dpi 300 --report /app/output/export_report.json
```

## 示意 manifest.json（节选）

```json
{
  "manifest_version": 1,
  "figure": {"title": "EGFR-RAF-ERK signaling (example)",
             "source": {"file": "example.pdf", "locator": "p.2"}},
  "entities": [
    {"id": "egfr", "label": "EGFR", "class": "receptor",
     "grid": {"col": 0, "row": 0},
     "evidence": {"locator": "p.2", "quote": "EGFR activates RAS"}},
    {"id": "ras", "label": "RAS", "class": "kinase",
     "grid": {"col": 1, "row": 0},
     "evidence": {"locator": "p.2", "quote": "EGFR activates RAS"}},
    {"id": "raf", "label": "RAF", "class": "kinase",
     "grid": {"col": 2, "row": 0},
     "evidence": {"locator": "p.2", "quote": "activates RAF"}},
    {"id": "vem", "label": "vemurafenib", "class": "compound",
     "grid": {"col": 2, "row": 1},
     "evidence": {"locator": "p.2", "quote": "vemurafenib blocks RAF kinase activity"}},
    {"id": "erk", "label": "p-ERK", "class": "kinase",
     "grid": {"col": 3, "row": 0},
     "evidence": {"locator": "p.2", "quote": "Phosphorylated ERK translocates into the nucleus"}},
    {"id": "myc", "label": "MYC", "class": "tf",
     "grid": {"col": 4, "row": 0},
     "evidence": {"locator": "p.2", "quote": "induces MYC expression"}}
  ],
  "groups": [
    {"id": "nucleus", "label": "Nucleus", "members": ["myc"],
     "evidence": {"locator": "p.2", "quote": "translocates into the nucleus"}}
  ],
  "relations": [
    {"id": "r1", "from": "egfr", "to": "ras", "type": "activates",
     "evidence": {"locator": "p.2", "quote": "EGFR activates RAS"}},
    {"id": "r2", "from": "ras", "to": "raf", "type": "activates",
     "evidence": {"locator": "p.2", "quote": "which in turn activates RAF"}},
    {"id": "r3", "from": "vem", "to": "raf", "type": "inhibits",
     "evidence": {"locator": "p.2", "quote": "blocks RAF kinase activity"}},
    {"id": "r4", "from": "erk", "to": "nucleus", "type": "translocates",
     "evidence": {"locator": "p.2", "quote": "translocates into the nucleus"}},
    {"id": "r5", "from": "erk", "to": "myc", "type": "activates",
     "evidence": {"locator": "p.2", "quote": "induces MYC expression"}}
  ],
  "uncertainty": ["示例中 RAS→ERK 的间接链条按原文省略中间体，未补造 RAF→MEK→ERK"]
}
```

## 示意输出

- `figure.svg`：分层源文件（background/groups/relations/entities/labels/
  legend 六层，Inkscape 可逐层开关；文字为可选中的 `<text>`）。
- `figure.png`（300 dpi）与 `figure.pdf`：导出件，可直接作为预览检查。
- `verification_report.json`：`status: pass`（若把 r3 的 type 误写为
  activates，校验会以 "relation r3 data-type mismatch" 判 fail；
  若 SVG 里手工加入清单外的文字，反幻觉门禁判 fail）。
- `export_report.json`：导出后端、字节数、像素尺寸与失败项。
- `result.json`：`case_id` + `output_contract` 各键 + status/sources/
  uncertainty/change_log。
