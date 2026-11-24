# 预览渲染协议（render_preview.py）

## 页面规格

- 页面：A4 比例 8.27in × 11.69in，DPI 110（约 910×1286 px），白底。
- 页眉：左上角「文件名 — 第 n/N 页」+ 细分隔线；正文左边距 7.5%。
- 排版：markdown 逐行折行（CJK 按 1 单位、ASCII 按 0.55 单位估算宽度）；
  `#/##/###` 标题逐级放大加粗（15/13/11.5pt），引用块 9pt，正文 10pt；
  表格分隔行 `|---|` 与代码围栏 ``` 跳过不渲染。
- 输出：`preview/<文件名>-p001.png …` 每页一张 + 合并 `preview/preview.pdf`
  + `render_manifest.json`。

## 字体回退链

依次用 `matplotlib.font_manager` 探测：
PingFang SC → Hiragino Sans GB → STSong → Noto Sans CJK SC → Noto Sans CJK JP →
Noto Sans CJK → WenQuanYi Zen Hei → Microsoft YaHei。
命中即用并记入 manifest 的 `font_used`；全部缺失仍用 DejaVu Sans 真实渲染
（中文呈占位框），manifest 记 `cjk_font_available: false` 并写明原因。

## 降级规则（均 exit 0，不阻断流水线）

| 情况 | 行为 | manifest 记录 |
|---|---|---|
| matplotlib 缺失 | 不生成 PNG/PDF，只写 manifest | `matplotlib_available:false` + 原因 |
| 中文字体缺失 | 照常渲染（占位框） | `cjk_font_available:false` + 原因 |
| 某文件读取失败 | 跳过该文件继续其余 | `files.<名>.error` |
| 长稿件 | 自动分页，页数入 manifest | `files.<名>.pages` |

降级后必须：在 result.json 的 `uncertainty` 中注明「无可视化预览/字体降级」；
manifest 路径仍作为 artifact 交付。

## 目检清单（打开 PNG 看什么）

1. 第 1 页页眉是否为 `revised-manuscript.md — 第 1/N 页`，文字是否清晰无乱码
   （中文呈方框 = 字体降级，核对 manifest）。
2. 修订稿正文中能否看到 `⟦CHG-##-BEGIN⟧` 标记；文末是否出现修改摘要表。
3. 回复信页：信头占位、总述统计句、逐条块五行结构、收口两表是否齐全。
4. 抽一个 CHG 编号，到 review_pack.html 覆盖矩阵点击，确认跳转到同名改动卡片，
   且 before/after 与 change_record.md 一致。
5. 对照 reviewer-comments.md：每条子要求在覆盖矩阵中恰有一行，裁决与证据状态诚实。
