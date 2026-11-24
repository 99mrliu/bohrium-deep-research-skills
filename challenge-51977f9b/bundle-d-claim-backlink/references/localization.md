# span 定位规范（localization）

论断回链的最小单位是 span：`{source, locator, text}`，span_id 必须能被
人和脚本双方唯一解析。

## 定位粒度

| 形式 | 适用 | 示例 | 说明 |
|---|---|---|---|
| 行区间 `#L<起>-<止>` | pdftotext/OCR 后的行文本（默认） | `R001.txt#L10-15` | index_sources.py 按 6 行窗、3 行步长滑窗，窗口有重叠，跨行 quote 可整体命中 |
| 段落 `#S<n>` | 结构清晰的 md/txt（--mode paragraphs） | `R001.txt#S3` | 按空行分段，跳过空段 |
| 题录记录 `#<record_id>` | records.json / JSONL 题录 | `records.json#R001` | 每条记录一个 span，text 为排序键后的 JSON 串 |
| 页码 `#P<n>` | 只能按页引用的扫描件 | `paper.pdf#P5` | 手工登记时使用；脚本不自动生成，须在 extractions/claims 中与文本 span 配套 |

## PDF 文本提取与行定位的配合

1. 优先 `pdftotext -layout in.pdf out.txt`：保留版式，行号稳定、可复跑；
   不加 `-layout` 时多栏论文会出现行内串栏，quote 匹配率下降。
2. 扫描件走 OCR 工具，输出 UTF-8 文本后再建索引；OCR 噪声（形近字、
   断词）会导致 C2 失败，此时应**回到提取文本重取 quote**，禁止凭记忆改写。
3. 建索引后不要手工改动材料文件；材料一旦变更必须重跑 index_sources.py
   并全量重审 claims（span_id 以行号定位，行号漂移会使旧引用悬空→C3）。
4. index_sources.py 完全确定（无时间戳、无随机）：同输入重跑逐字节一致，
   selfcheck 对此有断言；团队内可用 spans.json 的字节比对确认索引未漂移。

## 粒度选择建议

- 数字、效应量、P 值等短 quote：行滑窗粒度足够，quote 尽量取自单行。
- 方法学描述等长 quote：允许跨行（窗口重叠保证命中），但 quote 不宜超过
  一个窗口（默认 6 行）；更长论述应拆成多条证据。
- 题录级论断（如"该研究为 RCT"）直接引用 `records.json#<record_id>` span。
- 粒度过粗（整页一个 span）会使"回链"失去定位意义；粒度过细（单行无重叠）
  会让跨行 quote 无法命中。默认滑窗参数是两者的折中。
