# render-proof-deck：像素级渲染 QA 与自动修复语义

本文件是 `scripts/render_pipeline.py` 与 `scripts/fix_loop.py` 的方法文档：
检查算法、阈值、字号阶梯、修复循环语义，以及**已知误报边界（诚实不确定性）**。

## 0. 核心立场

pptx 只是中间态；观众看到的是导出的 PDF/PNG。构建期“成功”不证明渲染正确——
字体替换、文本裁切、图片丢失只在导出后发生。因此本 Skill 把**渲染件当作唯一
事实来源**：每一页都栅格化后逐像素检查，任何修复都以重渲染结果裁决。

## 1. 导出链路

```
deck.pptx ──soffice --headless --convert-to pdf──> deck.pdf
deck.pdf  ──pdftoppm -png -r 120（缺则 pymupdf 栅格化兜底）──> preview/slide-N.png
```

- soffice 查找顺序：PATH → `/opt/homebrew/bin/soffice` → `/usr/bin/soffice`
  → `/Applications/LibreOffice.app/...`。全部缺失 → `renderer.degraded=true`，
  像素 QA 跳过，result.json 如实记 degraded，**不伪造检查结果**。
- soffice 使用独立 `-env:UserInstallation` 临时 profile，避免并发/锁冲突。
- 栅格分辨率 120 dpi（10"×7.5" 页 → 1200×900 px），是速度与检测灵敏度的折中。

## 2. 逐页检查算法与阈值

所有阈值集中在 `render_pipeline.py` 顶部常量，并随 `render_proof.json.thresholds`
导出，第三方可按同一阈值复算。

| 常量 | 值 | 含义 |
|-|-|-|
| `FRAME_BAND_FRAC` | 0.02 | 页面外圈 2% 边框带（四边） |
| `INK_TOL` | 30 | 像素与背景色差（0–255 任一通道）超过此值记为“墨迹” |
| `OVERFLOW_WARN` | 0.0005 | 带内墨迹面积占带面积 ≥0.05% → warn |
| `OVERFLOW_FAIL` | 0.001 | 带内墨迹 ≥0.1% → fail（内容被页面边缘裁切） |
| `EMPTY_COVERAGE` | 0.0005 | 整页墨迹 <0.05% → 空渲染页 fail |
| `IMAGE_REGION_FLOOR` | 0.02 | 图期望区域内墨迹 <2% → 疑似丢图 |
| `PAGE_INK_FLOOR_WITH_IMAGE` | 0.02 | 放图页整页墨迹兜底下限 |

### (a) 页数一致性
python-pptx 读取 pptx 页数 vs PyMuPDF 读取 PDF 页数；不等即 fail。
LibreOffice 偶尔会把溢出文本框拆出额外页，此检查专抓这类漂移。

### (b) OVERFLOW（文本溢出/裁切）
背景色取四角 3×3 均值（对白底模板即纯白）。墨迹掩膜 = 与背景色差 > `INK_TOL`。
统计外圈 2% 边框带内的墨迹面积占比：
- ≥0.1% → **fail**：正常内容不会进入页面最外 2%（LibreOffice 对超出占位符的
  文本沿页面边缘裁切，被裁行必然在带内留墨迹）；
- ≥0.05% → warn（贴边但未确认裁切，留档不自动改）。

### (c) IMAGE-LOSS（丢图/白图）
`build_deck` 在 `build_log.json` 记录每张图期望的页面分数坐标 bbox。
QA 在渲染页裁出该区域算墨迹占比：<2% 且整页墨迹也低于下限 → **fail**；
区域偏白但整页有墨迹 → **warn**（白底图可能如此，见 §4 误报）。
构建期图片文件缺失未嵌入 → 直接 fail（不必等渲染）。

### (d) FONT-SUBSTITUTION
解包 pptx，正则提取全部 `typeface="..."`（跳过 `+mj-lt` 等主题槽位），
与 `fc-list : family` 的字体族比对；缺失列为 **warn**（渲染器会替换字体，
可能改变换行与版式）。fc-list 缺失 → 降级为只列请求字体。

### (e) 空渲染页
整页墨迹覆盖率 <0.05% → fail。捕获“导出成功但页面全白”的渲染器故障。

## 3. 字号阶梯与修复循环语义

阶梯：`20 → 18 → 16 → 14 → 12`，**硬下限 10pt，绝不更低**（低于 10pt 的
正文在投影上不可读，等于把问题藏起来）。

`fix_loop.py` 每轮（≤3 轮）：
1. 读 `render_proof.json.failures`；
2. **overflow** → 该页正文沿阶梯降一级，重建重渲；
3. 已在下限仍溢出 → **拆分续页**：后半要点移到同名「（续）」页
   （原页与续页均用 10pt，证据锚点随要点保留）；每页最多拆一次，防振荡；
4. **image_loss** → 按 basename 在 `work/paper/figs/` 重新定位重嵌；
   找不到 → 记 `unfixable`；
5. 无可应用的修复 → 停（不因 warn 无限迭代）；
6. 每轮修复后**完整重导出、重栅格、重 QA**，由渲染结果裁决是否继续。

终态：
- 全部 fail 消除 → status=success（overall 可能因字体 warn，不影响）；
- 仍有 unfixable → **status=partial 并指名页码**，不硬塞、不隐瞒。

硬规则（写死在代码里）：
- 字号永不低于 10pt；
- 图片永不拉伸（构建期等比缩放，修复只改路径/尺寸框不改宽高比）；
- 修复循环有界（默认 ≤3 轮），每步写入 `fix_log`（render_proof.json）
  并汇总进 result.json 的 `change_log`；
- **幂等**：fix_log 持久化在 render_proof.json；再次运行 finish 时，
  若 QA 已无 fail 则不产生任何新修复，历史修复记录保留。

## 4. 已知误报与限制（诚实声明）

1. **全出血（full-bleed）装饰**：模板若有延伸到页面边缘的色块/横幅，会触发
   OVERFLOW。当前无模板白名单机制 → 这类页会误判 fail 并尝试降字号（无害但
   无效，三轮后记 unfixable/partial）。限制已写入 result.json uncertainty。
2. **白底为主的图**（稀疏折线、白底热图）：图区域墨迹可能 <2%，被判 warn。
   这是刻意降级为 warn 而非 fail 的原因。
3. **背景色估计**：取四角均值；四角有装饰的模板会污染背景估计，进而影响
   墨迹掩膜。对四角干净的学术模板可靠。
4. **占位符内的溢出**：文本溢出占位符但仍在页面内（压到图片区）不会被
   边框带规则捕获——本检查只保证“不被页面边缘裁切”，不保证页内布局美观。
5. **字体核对是请求级**：fc-list 存在同名字体不代表字形度量一致，
   换行差异仍可能发生；PDF/PNG 才是最终裁决。
6. soffice 不可用时整链降级：render_proof.json 仍有结构与诚实状态，
   但像素检查为空——此时 pptx 与 PDF 一致性**未验证**，不得声称已核。

## 5. 复跑方法

```bash
python3 scripts/render_pipeline.py --work /app/work --output /app/output
```
对同一 deck.pptx 重跑将得到相同的逐页指标（渲染确定性），
`render_proof.json` 自带阈值与渲染器版本信息，可交给第三方独立复核。
