# 渲染裁决账本（render_verdict）

测量对象：`examples/work/measurements.json`；容差 ±0.2 cm

PASS 6 / FAIL 0 / UNMEASURED 0

| 检查项 | 期望 | 实测 | 判定 | 证据 |
|---|---|---|---|---|
| page.size.width_cm | 21.0 | 21.0 | PASS | /MediaBox 实测 |
| page.size.height_cm | 29.7 | 29.7 | PASS | /MediaBox 实测 |
| page.margin.left_cm | 2.54 | {"min": 2.54, "max": 2.54} | PASS | pdftotext -bbox 字形框逐页实测（容差 ±0.2cm） |
| page.margin.top_cm | 2.4 | {"min": 2.232, "max": 2.232} | PASS | pdftotext -bbox 字形框逐页实测（容差 ±0.2cm） |
| page.columns | 1 | 1 | PASS | 版心间隙检测 |
| fonts.embedded_all | False | False | PASS | /FontFile 流计数启发式（见 references/render-method.md） |
