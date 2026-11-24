---
name: journal-export-engineer
description: 下游渲染工程优先的科研数据可视化：把科研数据表做成期刊可直接接收的图件并逐字节证明合规——89mm 单栏物理尺寸、300dpi PNG（pHYs 块解析验证）、PDF 字体嵌入与 MediaBox 审计、SVG 活文本与物理尺寸审计、Okabe-Ito 色盲安全配色的灰度亮度差检验、CJK 字形覆盖检查防豆腐块，同时完成清洗、统计与中文图注。Use when a case requires publication-grade figure export (300dpi PNG + embedded-font PDF + editable SVG, journal column width, CJK labels, colorblind-safe palette) with machine-verifiable export compliance (科研数据可视化, 发表级导出, 期刊栏宽, 字体嵌入, 色盲友好, 中文乱码).
---

# 下游渲染工程：逐字节可审计的发表级导出

## 适用场景

输入科研数据表与出图任务，交付物必须**不经二次修补直接进入投稿或正式
报告**：单栏 89 mm、300 dpi PNG、嵌入字体 PDF、可编辑 SVG、中文标注不
乱码、色盲安全且灰度可辨。典型平台场景：`/input/case.json` +
`/input/task.md` + 数据文件，输出写入 `/app/output`。

## 运行契约（平台环境）

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output
```

- 一条命令跑完；`result.json` 自始以 `partial` 存在、逐阶段原地更新。
- 结束后先读 `/app/output/export_audit.json`（本 Skill 的核心交付：
  逐字节导出审计），再目检 PNG 预览。
- 非平台环境换路径即可。依赖：stdlib + numpy + matplotlib（缺失自动
  pip 安装；失败则交付文本结果并标注，不崩溃）。

## 本 Skill 的重心：导出规格的物理验证，而不是"看起来对"

`scripts/audit_export.py`（流水线自动调用）对每张图的三件套做字节级
审计，输出 `export_audit.json`：

| 审计项 | 方法 | 合格线 |
|---|---|---|
| PNG 分辨率 | 解析 pHYs 块换算 dpi | = 300（容差 1） |
| PNG 物理宽度 | IHDR 像素 ÷ pHYs 换算 mm | 89 mm（容差 2.5） |
| PDF 字体嵌入 | 扫描 FontFile/FontFile2/FontFile3 | 必须嵌入 |
| PDF 物理尺寸 | MediaBox pt 换算 mm | 89 mm |
| PDF Type3 风险 | 扫描字体类型标记 | 无 |
| SVG 活文本 | `<text>` 元素计数 | > 0（未轮廓化） |
| SVG 物理尺寸 | 根元素 width 换算 mm | 89 mm |
| 配色灰度可分性 | Okabe-Ito 各色灰度亮度差 | 前 3 色差 ≥ 15；蓝/绿接近对给出冗余编码建议 |
| CJK 字形 | 所选字体 charmap 覆盖"中/图" | 全覆盖，否则回退英文标注并声明 |

画布工程：mm 精确尺寸（`fig.set_size_inches(mm/25.4)`）、`pdf.fonttype=42`
（TrueType 嵌入）、`svg.fonttype=none`（活文本）、基础字号 6pt/刻度 5pt/
线宽 ≥0.5pt（单栏缩放后仍可读的下限）、Okabe-Ito 调色板、面板字母
(a)(b)…。

## 数据侧（与渲染同链完成）

清洗只留痕（缺失计数不插补、重复标记保留、1.5×IQR 仅标记）、描述统计
（n/均值/SD/SEM/中位数/四分位/极值/偏度）、分组统计（自动识别分组列；
无分组列时按偏斜协变量四分位分箱）、Pearson 相关；四张图：分布、
分组箱线叠加散点、关键变量对散点（分组着色）、相关热图（标注系数，
色标固定 [-1,1]）；右偏正值变量自动对数轴并在轴标注明"对数尺度"。
中文图注含 n、误差/须线含义、来源与清洗口径。

## 输出物（/app/output）

`result.json`（遵守 `output_contract` 全部字段）、`export_audit.json`
（核心交付）、`check_report.json`、`statistics.json/md`、
`cleaning_report.json`、`figures.figdata.json`、`captions.md/json`、
`run_manifest.json`、图件 PNG/PDF/SVG。

## 异常与边界

- 审计不过（如 dpi 不符、字体未嵌入）：写入 `uncertainty`，状态降
  `partial` 并指明哪张图哪一项。
- 无 CJK 字体：回退英文图内标注 + 中文图注文本 + `uncertainty` 声明，
  不出豆腐块。
- 多面板拥挤：变量 >8 的分组图按组间 F 统计量取前 8 并在图注声明
  取舍规则。
- 不做图像后期美化、不做统计推断。

## 最小示例

`examples/` 为**合成示例**（模拟数据），按 `examples/README.md` 一条
命令端到端复现；预期文本输出在 `examples/expected_outputs/`。
