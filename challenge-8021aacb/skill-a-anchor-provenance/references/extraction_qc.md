# 抽取质量控制与失败处置（上游数据真实性）

## 1. 抽取 QC 信号（manifest.json 自动产出）

| 信号 | 阈值 | 含义与处置 |
|---|---|---|
| `garble_ratio` | > 0.01 标 `garble_suspect` | 替换符 �、控制字符比例过高，多为 PDF 字体映射失败。该来源的 finding 必须在 uncertainty 中注明「抽取质量差，引文可信度受限」；可尝试 OCR 工具（environment 提供 ocr-tool）后重抽 |
| `truncation_suspect` | 末段不像结尾 | 稿件可能被截断。在 uncertainty 写明「疑似截断于 Sx-Pyyy」，结论边界类诊断降级为 partial 判断 |
| `unreadable[]` | 任何解包/解码失败 | 逐条记入 uncertainty 与 sources；绝不凭文件名猜内容 |

## 2. 输入类型处置顺序

1. `.md/.txt/.tex`：直接 UTF-8 读取；解码失败入 `unreadable`。
2. `.pdf`：`pdftotext -layout`；缺二进制、超时、非零返回码均如实记录，不切换成猜测。
3. `.docx`：按 zip+xml 容错解包 `word/document.xml`；任何异常入 `unreadable` 并附异常类型。
4. 图表文件（若有）：不解析像素内容；只引用正文/图注中对该图表的文字描述。

## 3. 严重度判据（供 finding.severity 使用）

- **high**：导致论证闭环断裂的缺陷——结论无对应结果、方法缺关键步骤致结果不可复核、研究问题全文未回收。
- **medium**：局部断裂——单条论断缺论据、跨章节重复一段以上、结论个别句子超界。
- **low**：衔接与冗余——过渡缺失、同义复述、铺垫位置欠佳。

判 high 必须同时满足：锚点引文成立 + 缺陷影响「问题—方法—结果—结论」闭环；只影响阅读流畅度的一律 ≤ medium。

## 4. 诚实性红线

- 引文只许来自 anchor_map 文本；模型凭记忆补写的句子不得作为 quote。
- 材料不足以下结论时，finding 写 `status: needs_human_confirmation` 并在 uncertainty 说明缺什么材料。
- 重复运行同一输入必须得到同一锚点集；任何手工改过的抽取文本都要在 change_record 记一笔。
