# render-qa 参考：五门各查什么、抓到后怎么修

`scripts/render_qa.py` 对"导出的 PDF"做取证。输入是 PDF + expectations.json，
输出 render_report.json + stdout 逐行 `CODE: detail`，退出码 0/1/2。

## expectations.json 字段

| 字段 | 默认 | 含义 |
|---|---|---|
| `page_count` | （必填） | 期望页数，R1 的基准 |
| `footer_zone_fraction` | 0.08 | 页脚区 = 页面底部该比例高度；词框下缘进入即 R3 |
| `min_text_height_pt` | 10.0 | 页内词框高度中位数的下限（pt），R4 的阈值 |
| `expected_figure_pages` | [] | 应含实质图形的页码（1-based），R5 的检查对象 |
| `blank_ink_threshold` | 0.001 | 整页墨水覆盖率低于此值视为"无墨迹"，R2 用 |
| `figure_ink_threshold` | 0.02 | 图页内容区墨水覆盖率下限，R5 用 |
| `content_margin_fraction` | 0.05 | R5 内容区的四边留白比例（页眉页脚页边不计入内容区） |
| `ink_pixel_threshold` | 240 | 像素 RGB 均值低于此值计为墨水 |
| `render_dpi` | 72 | pdftoppm 渲染分辨率（72dpi 下 1pt=1px，够用且快） |
| `eps_pt` | 0.5 | R3 页缘判定的几何容差 |
| `min_words_for_height_check` | 3 | 词数少于此值的页跳过 R4（避免个别词误报） |

词框几何来自 `pdftotext -bbox`（页面坐标，pt，原点在左上）；墨水覆盖率由
`pdftoppm` 渲染的 PPM 用纯 Python 解析计算。pdftotext/pdftoppm 任一缺失 →
exit 2 并打印缺失工具名，此时按 Skill 的降级规则如实记录，不得伪造渲染结论。

## 逐门说明与修复 playbook

### R1 页数一致
- **查什么**：实际导出页数 ≠ `page_count`。
- **典型成因**：导出中途失败截断；某版式溢出被拆成两页；隐藏页/空白页被一并导出。
- **修法**：对照 storyboard 找出多出/缺失的页；检查文本框是否溢出导致分页；
  重导出后重跑。若契约页数本身变了，先改 expectations 再改 deck——两者必须同源。

### R2 空白页
- **查什么**：某页零词 **且** 整页墨水覆盖率 < `blank_ink_threshold`。两个条件同时成立才报，
  纯装饰页（有墨迹）或纯文本页（有词）都不会误报。
- **典型成因**：占位版式忘了填内容；图片链接断裂且本页只有图；导出时整页对象丢失。
- **修法**：回 deck 补内容或删除该页；若该页本该是图页，同时会命中 R5，优先修图。

### R3 文字越界 / 页脚侵入
- **查什么**：任一词框超出页面矩形（容差 `eps_pt`），或词框下缘 yMax 越过页脚区上缘。
- **典型成因**：文本框设了"不自动缩小"而内容变长，溢出页缘被裁；母版页脚被正文压盖；
  从别的模板拷来的形状带绝对定位。
- **修法**：定位违例词（detail 里给了词文本与 bbox），回对应页缩短文字/缩小字号/
  重排文本框；若是合理的页脚文字（页码、机密标注），把 `footer_zone_fraction` 调小
  或把页脚做进母版的页脚占位符并在 expectations 中豁免——但必须是有意决定，不是放行事故。

### R4 过小文字
- **查什么**：页内词框高度中位数 < `min_text_height_pt`。中位数口径保证个别上标/脚注不背锅，
  整页字缩水才报。
- **典型成因**：导出时"缩放到一页"/整页缩放链把字号压小；字体替换后实际渲染变小；
  从截图/大纲误生成的小字页。
- **修法**：回 deck 恢复正常字号（正文 ≥18pt 量级是汇报常识）；检查导出配置里有没有
  "fit to page" 类选项。注意：词框高度是渲染后的物理高度，pt 阈值按导出后实际量。

### R5 缺图 / 图页空壳
- **查什么**：`expected_figure_pages` 列出的页，内容区（去页边距与页脚区）墨水覆盖率 <
  `figure_ink_threshold`；页不存在也报。
- **典型成因**：图片未嵌入（链接图在导出机上断链）；图被裁出可视区；图页只剩一行图题。
- **修法**：回 deck 重新嵌入图片（嵌入而非链接）；检查裁剪框；导出后对照 PNG 预览目检。
  线图类内容墨水占比本来就不高，若误报可把 `figure_ink_threshold` 降到 0.01 量级，
  但调参理由写进 change_log。

## 修复回路纪律

完整"修 deck → 重导出 → 重跑 render_qa"为一轮，**至多两轮**。第二轮仍 exit 1：
保留当轮 render_report.json，result.json 标 partial，把残留违例逐条写进
limitations 与 change_log。违例清单是交付物的一部分，不是需要藏起来的失败。

## render_report.json 结构

```
{
  "pdf": "...", "expectations_file": "...", "expectations": {...},
  "page_count": 4,
  "gates": {"R1": {"pass": true, "detail": "..."}, ... "R5": {...}},
  "pages": [{"page": 1, "width_pt": 612, "height_pt": 792,
             "word_count": 12, "median_word_height_pt": 20.8,
             "ink_coverage": 0.004, "content_ink_coverage": 0.005}, ...],
  "violations": [{"code": "R3", "page": 3, "detail": "..."}],
  "status": "pass" | "fail"
}
```
