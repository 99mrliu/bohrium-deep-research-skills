# 发表级导出规格（下游渲染工程）

## 画布与尺寸

| 项 | 规格 | 实现 |
|---|---|---|
| 单栏宽 | 89 mm（3.5 in） | `fig.set_size_inches(mm/25.4)`，保存前显式设置 |
| 双栏宽（必要时） | 183 mm | 仅在面板过多时升级并记录 |
| 高度上限 | ≤ 240 mm | 网格行高 30–45 mm |
| 边距 | constrained_layout | 避免标签被裁切 |

## 三种导出格式与验证方法

| 格式 | 用途 | 生成参数 | 字节级验证 |
|---|---|---|---|
| PNG | 投稿位图/预览 | `savefig(dpi=300)` | 解析 pHYs 块换算 dpi；IHDR 像素 ÷ pHYs 换算物理宽度 |
| PDF | 矢量投稿 | `pdf.fonttype=42`（TrueType 嵌入） | 扫描 FontFile/2/3；MediaBox pt→mm；Type3 风险扫描 |
| SVG | 可编辑源 | `svg.fonttype=none`（活文本） | `<text>` 元素计数 >0；根元素 width→mm；font-family 声明 |

验证由 `scripts/audit_export.py` 自动执行，结果写入
`export_audit.json`，任何一项不过都进入 `uncertainty`。

## 字号与线宽下限（缩放到单栏宽后仍可读）

- 基础字号 6 pt；坐标轴标题 6 pt；刻度 5 pt；图例 5 pt；
  热图格内系数 ≥3 pt（随矩阵规模自适应下限）；
- 坐标轴线宽 0.6 pt；数据线宽 0.8 pt；刻度线宽 0.5 pt；
- 标记直径 2–2.5 pt，离群点 1.5 pt。

## 期刊常见要求对照

| 要求 | 本流水线默认 |
|---|---|
| 300 dpi 以上位图 | 300 dpi PNG（pHYs 验证） |
| 矢量格式 | PDF（嵌入字体）+ SVG（活文本） |
| 栏宽匹配 | 89 mm 单栏（可在约束中改 183 mm 双栏） |
| 字体嵌入 | TrueType 嵌入，禁用 Type3 |
| 色盲友好 | Okabe-Ito 调色板 |
| 灰度可辨 | 亮度差审计 + 位置/形状冗余建议 |
| 中文/特殊符号 | CJK 字体发现 + charmap 字形覆盖检查 |

## 常见失败与处置

- `pip install matplotlib` 不可用 → 交付统计/清洗文本，图件缺失写入
  `uncertainty`，`status=partial`；
- 无 CJK 字体 → 图内英文标注 + 中文图注文本，声明于 `uncertainty`；
- 导出器异常 → 保留 SVG 与再生成脚本路径，记录失败信息，降 partial。
