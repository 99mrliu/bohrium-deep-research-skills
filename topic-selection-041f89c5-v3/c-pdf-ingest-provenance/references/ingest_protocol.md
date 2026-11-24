# 摄入协议（ingest protocol）

## 登记项

每个输入文件在 source_registry.json 中登记：

| 字段 | 含义 |
|-|-|
| file | 相对 /input 的路径 |
| bytes / sha256 | 原始字节数与哈希（事后可证明文件未被改动） |
| kind | 扩展名推定的类型 |
| status | ok / empty_extraction / tool_missing / extract_failed / registered / skipped |
| text_layer | 提取文本层路径（sources/ 下，页间以 \f 分隔） |
| pages | 逐页字符数与乱码率（仅已建文本层的来源） |

## 处理规则

1. **PDF**：用系统 pdftotext（`-layout`）真实解析；缺失时按 resources.yaml 换用
   运行环境的 pdf-text-tool，并在 registry 补登记实际工具名。禁止假设存在
   预提取文本层，禁止凭文件名推断内容。
2. **TXT/MD**：直接登记为单页文本源（page=1）。
3. **JSON/JSONL/CSV**：记录型材料，按结构读取，不建文本层、不作引文来源；
   其中的事实在证据表标注 `[来源:文件名(记录)]`。
4. **其他类型**：标 skipped 并写明"如任务需要请人工确认处理方式"，不静默丢弃。

## 质检分级（extraction_qc.py qc）

| 判定 | 条件 | 处置 |
|-|-|-|
| ok | 全部页 ≥20 字符且乱码率 ≤0.02 | 可引用 |
| ok_with_notes | 存在空页或低文字页 | 可引用，避开这些页 |
| suspect | 存在乱码页（乱码率 >0.02） | 引用前人工目检对应页 |
| unreadable | 提取失败/全文无字 | OCR 重试一次；仍失败则来源不可用，相关结论降级 partial |

## 与预算的关系

摄入与质检是确定性脚本，不消耗模型请求；应一次性对所有材料跑完，
把模型请求留给判读与综合。OCR 重试最多一次——第二次重试的边际收益
通常低于其预算成本。
