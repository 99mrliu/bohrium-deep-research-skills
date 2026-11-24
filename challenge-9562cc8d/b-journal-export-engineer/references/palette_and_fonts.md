# 调色板与字体工程

## Okabe-Ito 调色板（色盲安全）

```
#0072B2 蓝    #E69F00 橙    #009E73 绿    #D55E00 朱红
#CC79A7 粉紫  #56B4E9 天蓝  #F0E442 黄    #000000 黑
```

- 对 deuteranopia/protanopia/tritanopia 均可区分（调色板设计目标）；
- 相关热图使用发散色 RdBu_r（红正蓝负），色标固定 [-1, 1]，
  格内叠加系数文本补偿颜色通道精度。

## 灰度打印可辨性审计

`audit_export.py` 将各色换算为灰度亮度
`Y = 0.299R + 0.587G + 0.114B` 并计算两两差：

- 前 3 色（实际分组数 ≤3 时使用的色）最小灰度差 ≥15 判为可辨；
- 已知边界对：蓝 #0072B2（Y≈87）与绿 #009E73（Y≈106）差 ≈19，
  纯灰度场景属"勉强可辨"——审计报告给出 advisory：**灰度交付时叠加
  线型/标记形状/填充纹样的冗余编码**，而不是换用非色盲安全配色。

## CJK 字体发现与豆腐块防线

1. 候选名单：PingFang SC → Hiragino Sans GB → Noto Sans CJK SC →
   Source Han Sans SC/CN → WenQuanYi（Zen/Micro Hei）→ 微软雅黑 →
   SimHei → STHeiti → Heiti SC → Songti SC → Arial Unicode MS；
2. 对候选字体用 FreeType charmap 实测 `中`(U+4E2D) 与 `图`(U+56FE)
   字形覆盖——只看字体名不够，必须查字形；
3. 名单皆空则全字库扫描；
4. 仍无覆盖字体：图内标注回退英文变量名，中文图注以纯文本交付，
   写入 `uncertainty`；**绝不允许渲染出豆腐块后静默交付**；
5. 所选字体名写入 `figures.figdata.json` 的 `cjk_font` 字段与
   `run_manifest.json`，供审计追溯；
6. `axes.unicode_minus=False`，避免负号缺字形。

## PDF 字体嵌入

`pdf.fonttype=42`（TrueType 子集嵌入）。审计扫描 PDF 字节流中的
`FontFile`/`FontFile2`/`FontFile3` 标记；发现 Type3 字体（位图字体，
缩放失真）判为风险项。SVG 交付 `svg.fonttype=none` 活文本，保证编辑
软件中可直接改字。
