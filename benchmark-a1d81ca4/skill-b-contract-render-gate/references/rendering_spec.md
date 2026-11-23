# 渲染规范（rendering_spec.md）

本文件规定 preview.svg 的版式约定、内置 PNG 编码器的设计理由与实现要点、
外部渲染器探测顺序与降级表。实现见 `scripts/render_preview.py`。

## 1. SVG 面板版式约定

- 画布：宽 760px，高 = 40（标题条）+ 24 × 行数 + 20（底边距）。
- 标题条：高 40px，深蓝 `rgb(31,58,95)`，白色等宽字体 16px，
  文字固定为 `CONTRACT-RENDER-GATE PREVIEW`。
- 文本行：等宽字体 14px，行高 24px，x=12；`CASE:` / `FIELDS:` 摘要行
  用琥珀色 `rgb(210,140,30)`，其余深灰 `rgb(30,30,30)`。
- 字段矩阵行：左侧 14×14 色块（绿 `rgb(46,160,67)`=已填充；
  红 `rgb(200,60,60)`=必填但 null；灰 `rgb(150,150,150)`=选填 null），
  文本 `字段名 : FILLED|NULL(REQUIRED)|NULL(OPTIONAL)`，x=34。
- 题目行：文本 `ID DIFF=难度 EV=证据数`，x=34；右侧蓝色条形
  `rgb(40,110,200)`，x=430，宽 = min(证据数 × 30, 300)，高 12。
- SVG 为纯字符串模板生成，落盘前必须经 `xml.etree.ElementTree.
  fromstring` 校验 well-formed；非 ASCII 文本保留 UTF-8（XML 合法），
  特殊字符经 `xml.sax.saxutils.escape` 转义。
- **确定性**：SVG 不含时间戳、随机数、绝对路径等易变量，重跑字节一致。

## 2. 内置 PNG 编码器（为何 stdlib 手写）

**设计理由：零依赖确定性。** 运行环境只保证 python3 标准库（3.8+），
外部渲染器可能全部缺失。预览必须是一张"真实生成的位图"而非口头声明，
因此用 `zlib`（DEFLATE 压缩）+ `struct`（大端字节序打包）手写 PNG：

- 文件头 `89 50 4E 47 0D 0A 1A 0A`；IHDR：8bit、颜色类型 2（RGB）、
  压缩/过滤/隔行均为 0；
- 每扫描行前缀 filter 字节 0（None），原始数据 `zlib.compress(raw, 9)`
  打入 IDAT；每块 CRC32 由 `zlib.crc32` 计算；IEND 收尾。
- 产物必须能被 `file` 命令识别为 `PNG image data`。

**字体**：内置 5x7 ASCII 点阵字体（A-Z、0-9 及常用符号），以 scale=2
绘制（每字符 10×14px，步进 12px）。**不渲染 CJK**：非 ASCII 字符一律
替换为 `?`。中文内容请查看 SVG 版本；这是刻意取舍——位图预览的目的
是供人工目检"状态面板结构与填充情况"，而非复现正文排版。

SVG 与 PNG 由同一份行描述（`build_lines`）驱动，两产物内容一致。

## 3. 外部渲染器探测顺序与降级表

按以下顺序 `shutil.which` 探测，命中即用，全部失败则降级：

| 顺序 | 工具 | 命令形态 | 备注 |
| --- | --- | --- | --- |
| 1 | rsvg-convert | `rsvg-convert -o preview_hd.png preview.svg` | 最轻量，优先 |
| 2 | inkscape | `inkscape preview.svg -o preview_hd.png` | Inkscape ≥1.0 语法 |
| 3 | magick | `magick preview.svg preview_hd.png` | ImageMagick 7 |
| — | （全部缺失） | 不生成 preview_hd.png | `preview_record.json` 的 `preview_note` 记明"外部渲染器缺失，使用内置 PNG 编码器"，`renderer` 记为 `internal` |

- 外部渲染成功时额外记录 `hd_sha256` 与 `hd_dims`，并与内置 PNG 的
  760×H 尺寸对比写入 `preview_note`。
- 外部命令设 60 秒超时并捕获全部异常；任何失败都静默尝试下一个，
  **绝不崩溃**。
- 预览是目检辅助：无论走哪条路径，`preview.png`（内置编码器）恒生成，
  门禁只强制校验 SVG 与内置 PNG 的存在性与 sha256 一致性。

## 4. 产物清单与校验

`preview_record.json` 记录：case_id、width/height、svg_sha256、
png_sha256、renderer、preview_note、（可选）hd 信息。
`selfcheck_gate.py` 现场重算 sha256 并与 record 比对，不一致即 BLOCK——
防止"记录声称有预览而实际产物缺失或被篡改"。
