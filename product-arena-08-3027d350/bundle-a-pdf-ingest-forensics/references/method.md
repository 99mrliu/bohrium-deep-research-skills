# 方法说明：阈值、探针存在的理由与失效模式

本文件解释 pdf-ingest-forensics 三个脚本背后的工程判断。所有阈值都是
保守的经验值：宁可多派 OCR（partial），不可把垃圾当内容（fabrication）。

## 探针与阈值

### 1. 加密检测（pdf_probe.py）

- **信号**：原始字节中出现 `/Encrypt` 标记（trailer 字典的加密入口）。
- **动作**：立即 exit 3，route=`refuse_with_handoff`。
- **为什么**：加密 PDF 的流要么读不出、要么读出来是密文碎片。任何
  "试着解析一下"都会产生看似文本的垃圾，这是最典型的上游不真实输入。
  我们不解密、不绕过时——只如实上报。
- **失效模式**：极少数制作工具会把字符串 `/Encrypt` 写进元数据文本，
  造成误报；此时人工看一眼 trailer 即可澄清，代价远低于漏报。

### 2. 逐页文本层覆盖率 / 扫描页判定

- **信号**：`image_count >= 1 且 char_count < 20` ⇒ `scanned_candidate`。
- **为什么是 20**：扫描页偶尔也会漏出页眉页脚、水印或 OCR 残留的几个
  字符（< 20）；真正的数字排版页极少低于几百字符。阈值取 20 把
  "有几个杂字符的扫描页"和"短文本数字页"分开。
- **char_count 来源**（按优先级）：PyMuPDF（`page.get_text`）→ poppler
  `pdftotext -f N -l N` → manifest 字段（合成示例）。三者都没有时
  `text_layer_measured=false`，路由只能是临时性的。
- **失效模式**：① 整页矢量化（文字转曲）的科学图版页会被误判为扫描页——
  其实路由到 OCR 也是正确动作，只是理由措辞不同；② 纯文本页被误判的
  情况几乎没有；③ 字符数正常但内容全错的情况由 glyph_audit 兜底。

### 3. 字形/乱码审计（glyph_audit.py）

| 指标 | 阈值 | 严重度 | 含义 |
|---|---|---|---|
| U+FFFD 连续段 | > 2 | high | 解码彻底失败的区段 |
| U+FFFD 任意出现 | ≥ 1 | medium | 有解码失败点 |
| PUA 字符比率 | > 0.5%（占字母类字符） | high | CID 字体 ToUnicode 缺失，典型"自定义编码垃圾" |
| PUA 任意出现 | ≥ 1 | medium | 局部符号字体也可能用 PUA，需人工判断 |
| mojibake 字符占比 | > 3% / > 1% | high / medium | UTF-8 字节被按 Latin-1 解码（`â€`、`ç±»` 形态） |
| 杂散控制字符 | ≥ 1 | medium | 抽取管线污染的副产品 |

- **为什么查 PUA**：大量中文期刊 PDF 用子集化 CID 字体且不带 ToUnicode
  CMap，抽出来的"文字"全部落在 U+E000–U+F8FF 私用区。它看起来像文字、
  字符数也正常，但语义为零——这是"字符数正常但内容全错"的主力形态，
  也是为什么只靠字符覆盖率不够、必须有第二道审计。
- **mojibake 签名**：正则 `(?:[\u00c0-\u00ff][\u0080-\u00bf])+` 匹配
  "Latin-1 高位字符 + 续字节"对，即 UTF-8 被当作 Latin-1 解码后的经典
  形态（`â€`、`ç±»`、`Ã©` 等）。
- **CJK↔Latin 翻转计数**：作为编码打乱的辅助启发指标（当前不计分，只
  记录，供人工复核时参考）。

### 4. 旋转页

- **信号**：`/Rotate` 值 % 360 ≠ 0。
- **动作**：文本层仍可直接用，但理由中强制注明"版面/表格分析前先按
  声明角度回正"。
- **为什么**：旋转页的文本抽取通常正常，但任何按坐标干活的下游
  （表格结构、图注配对）会静默错位——这属于"读得出来但理解错"的
  隐性不真实。

### 5. 重复页

- **信号**：规范化文本指纹（空白压缩后的 MD5；manifest 模式下为
  manifest 自带指纹）相同。
- **动作**：只解析一次，记录 `duplicate_of` 映射。
- **为什么**：拼版错误、勘误页重复插入在期刊 PDF 中并不少见；不
  去重会让下游把重复证据当作独立证据（例如把样本量数两遍）。
- **失效模式**：指纹基于文本层，两个都空白的页不会互相指认（指纹为
  None 即跳过）——空白页另有 `empty_page` 标记。

## 路由语义（route_decision.py）

- `direct_text_layer`：全部页面文本层可信。
- `ocr_handoff`：没有任何一页可用文本层，整本移交 OCR。
- `mixed_pagelevel`：部分页 direct、部分页 OCR——科学 PDF 最常见的形态。
- `refuse_with_handoff`：输入根本不可读（加密/零页）。停止，如实上报。
- **诚实规则**：存在任何 scanned / 乱码(medium+) / 旋转 / 重复 / 覆盖率
  未测量 ⇒ result.json status=`partial`；refuse ⇒ `failed`。本 Skill
  不产出 `full_text`，该字段恒为空并在 uncertainty 中解释。

## 与平台工具的关系（真实运行环境）

本 Skill 只做分诊与路由，重活在真实环境中由平台工具执行：

- `pdf-text-tool`：对 direct 页面执行正式文本层抽取；
- `pdf-render-tool`：把 OCR 页/扫描页渲染成位图；
- `ocr-tool`：对渲染位图做 OCR，其结果回填 page_map；
- 表格类需求在 OCR 之后再接表格工具；本 Skill 不编造任何表格数值。

最小示例用 `--manifest pages.json` 替代真实 PDF，使全部判定逻辑在没有
poppler / PyMuPDF / 平台工具的裸 Python 3 环境里也能端到端跑通。

## 已知限制

1. 纯 stdlib 的容器探针按正则统计 `/Type /Page`、`/Rotate`、MediaBox，
   不做完整对象图解析：对极度病态的 PDF（对象流压缩的 xref、线性化
   重写）可能数不准页数——此时以外部工具（pymupdf/poppler）为准，
   报告中的 `raw_container` 只作旁证。
2. 无外部工具时逐页覆盖率不可知，路由标记为临时（provisional）。
3. manifest 模式信任清单字段；它是测试/演示通道，不是真实性来源。
