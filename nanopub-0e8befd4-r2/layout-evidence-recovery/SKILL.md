---
name: layout-evidence-recovery
description: >-
  当任务需要从 PDF 或其文本提取中恢复物理版面与可审计证据时触发，尤其是双栏交错、跨栏/跨页阅读顺序、跨行断词、页眉页脚隔离、图中文字与正文混排、TXT/MD 分页行索引、逐字或保真引文定位，以及扫描件无文本层的诚实 partial。仅做通用 lint、引用格式检查、来源指纹/判重、论文内容评价、语义蕴含或答案正确性判断、纯知识问答且没有 PDF/文本证据定位需求时不要触发。本 Skill 不直接保证 PDF 解析或 OCR 成功，也不从字符串匹配推断语义。
---

# Layout Evidence Recovery

面向 `product-arena-09-0e8befd4`。唯一目标是把上游 PDF 物理版面转成**页/块/行/offset 可复核的证据**，或明确保留无法恢复的 partial。不是通用 lint，不是来源指纹管线，不判断 claim 是否被语义支持。

## 必读规则

- 版面恢复：[`references/layout-recovery-rules.md`](references/layout-recovery-rules.md)
- 输入、证据、offset 与最终字段：[`references/evidence-schema.md`](references/evidence-schema.md)
- 工具：`scripts/layout_evidence.py`，Python 3.9+，仅用标准库。
- 资源：[`environment/resources.yaml`](environment/resources.yaml)。

## 1. 合同、输入、预算优先

1. **先读 `/input/task.md`**，找到本次实际 `output_contract`，其字段名、类型和必需字段优先于本 Skill 的所有示例。再读 `/input/case.json`，将原 `case_id` 原样带入 `/app/output/result.json`。
2. 查看 `environment/resources.yaml` 及实际可用资源。工作文件放 `/app/work`，最终结果放 `/app/output`；不污染 `/input`，不把中间文件冒充最终结果。
3. 全部过程最多 **64 requests / 900 秒**。初始记录 request 计数和单调时钟，预留结果检查时间。可选 PDF/OCR 工具不可用时不强行安装重依赖。
4. 启动后立即创建诚实 partial：包含原 `case_id`、实际合同的全部字段（尚未恢复则用合同允许的 `null`/空容器）、`sources`、`uncertainty`、`change_records`，以及合同认可的 partial 状态。每完成一个阶段就原子更新，不能等超时后才保存。
5. `sources` 记录 PDF/提取器/块/查询来源；`uncertainty` 记录未确认顺序、断词、OCR、扫描与歧义；`change_records` 记录 LF 规范化、块角色与顺序选择、定位尝试和结果更新。禁止把未运行写成成功。
6. 最终 `/app/output/result.json` 必须出现实际 `output_contract` 的**全部字段**。若合同限制附加字段，严格按合同组织 sources/uncertainty/change_records，并把详细机器报告留 `/app/work`。完成状态只用于已满足合同的产物。

### 最小 partial 形成方式（不是固定合同模板）

不要照抄字段名覆盖真实合同。先枚举本次合同字段，再形成类似对象：

```json
{
  "case_id": "<从 case.json 原样复制>",
  "status": "partial",
  "<actual_output_contract_field>": null,
  "sources": [],
  "uncertainty": [{"code": "PROCESSING_STARTED", "message": "证据尚未恢复"}],
  "change_records": [{"operation": "initialize_partial", "source_modified": false}]
}
```

未知字段保持未知，不编造引文或 offset。输出合同若已规定状态/错误结构，则使用合同结构而不是示例键。

## 2. 恢复流程

### A. 取得物理块，不假定依赖存在

原始 PDF 已有文本层时，可使用环境中已有的 `pdftotext -bbox` / `pdftotext -bbox-layout` 或 PyMuPDF 提取带坐标行/块，再按 references 的输入 schema 写成 `/app/work/layout.json`。脚本不直接读取 PDF，不要求安装上述软件。

必须保留：物理页、块 ID、bbox、原始行、块角色和 `block_order`。常规双栏只有在视觉/提取证据支持时才声明左栏从上到下再右栏；不要按所有 `y0` 全局排序。页眉、页脚、图内文字标成 `header`、`footer`、`figure_text`，默认排除正文但仍留在索引中。多处正文块无声明顺序时只保存带 `ORDER_NOT_DECLARED` 的 partial。

### B. 扫描与畸变

扫描无文本层必须标为 `extraction_status: no_text_layer`，保持空块并报告 `NO_TEXT_LAYER`。未运行 OCR 就没找到时仍是未知，不是“不含引文”。实际运行 OCR 后标 `ocr`、记录来源，未逐字核准保留 `OCR_UNVERIFIED`。未决乱码、旋转文字、ligature 等进入 `uncertainty`，不得悄悄规范化成成功文本。

### C. 索引与定位

对每一个 claim/query，按需要分别尝试：

- `exact`：逐字定位，不折叠空白或断词；找不到是 `not_found`。
- `fidelity`：折叠空白，并为物理行尾连字符分别尝试“去连字符合并”和“保留连字符合并”两个投影（`fidelity_variant`），映射回同一 raw range 时去重；可恢复 `cross-column` 和 `dehyphenation`，不做大小写、同义词或语义变换。
- 重复短语多处命中一定为 `ambiguous`，列出全部位置，不擅自选一个。
- 图中文字确属目标时用 `--include-figure-text` 另行生成索引，并披露该变更；不要混入正文索引。
- 任何匹配都不代表 semantic entailment；脚本输出固定 `semantic_entailment: not_evaluated`。

机器定位至少需要首段 `page/block_id/line/line_offset_start/end`、全引文 document offsets、逐行 `segments` 和原文 `source_excerpt`。offset 是零基 Unicode code-point 半开区间；LF 规范化后不是磁盘字节 offset。

### D. 完成或诚实 partial

完成前检查：

1. `case_id` 未改变，合同字段一个不缺且类型正确。
2. 引文能回查每段页/块/行/offset；跨块/跨页看 `spans_*`，不只看首位置。
3. `sources`、`uncertainty`、`change_records` 反映实际过程。
4. `no_text_layer`、OCR 未核、未定栏序、匹配歧义、找不到和异常字符均未被隐藏。
5. 退出码 2 时读取已生成 JSON，保存 usable partial；退出码 1 修复输入/运行错误，不声称测试通过。

## 3. 完整可运行示例（从 Skill 根目录执行）

下列路径均相对本 Skill 根目录，除了竞赛约定的 `/app/work` 和 `/app/output`，不依赖个人目录。

### 3.1 语法检查与 33 条 SYNTHETIC 合成断言

```bash
python3 -c 'from pathlib import Path; p=Path("scripts/layout_evidence.py"); compile(p.read_text(encoding="utf-8"), str(p), "exec"); print("syntax OK")'
python3 scripts/layout_evidence.py verify \
  --suite examples/synthetic/suite.json \
  --output examples/expected/verification-report.json
```

预期：输出 `status=passed assertions=33 passed=33 failed=0`，退出码 0。验证器从 JSON/TXT/MD 原始输入重新索引、查询并逐字段核对，不是仅检查快照存在。

### 3.2 双栏索引和唯一定位

```bash
python3 scripts/layout_evidence.py index \
  --input examples/synthetic/layout.json \
  --output examples/expected/layout-index.json
python3 scripts/layout_evidence.py locate \
  --index examples/expected/layout-index.json \
  --queries examples/synthetic/queries.json \
  --output examples/expected/location-report.json
```

预期：两条命令均退出码 0。产物：

- `examples/expected/layout-index.json`：两页显式块序、原始行、页/块/document offsets；header/footer/figure_text 可见但 `included: false`。
- `examples/expected/location-report.json`：三条唯一定位，分别覆盖逐字、跨行断词、左栏末到右栏始；含逐段 offset 和原文，不是语义判断。

### 3.3 TXT/MD 单独运行

```bash
mkdir -p /app/work /app/output
python3 scripts/layout_evidence.py index \
  --input examples/synthetic/text.txt --synthetic \
  --output /app/work/text-index.json
python3 scripts/layout_evidence.py index \
  --input examples/synthetic/markdown.md --synthetic \
  --output /app/work/markdown-index.json
```

TXT form-feed 和 MD 独占行 `<!-- page: N -->` 会形成一基页索引；页标记不进入正文。空页可被保留，但不会自动标记为扫描无文本层。

### 3.4 预期失败/歧义例（真实退出码 2）

```bash
python3 scripts/layout_evidence.py index \
  --input examples/expected-failure/layout.json \
  --output examples/expected-failure/index.json
index_status=$?
python3 scripts/layout_evidence.py locate \
  --index examples/expected-failure/index.json \
  --queries examples/expected-failure/queries.json \
  --output examples/expected-failure/report.json
locate_status=$?
printf 'index_status=%s locate_status=%s\n' "$index_status" "$locate_status"
test "$index_status" -eq 2
test "$locate_status"  -eq 2
```

预期是两个 JSON 都已写出、两个状态均为 2：重复短语为 `ambiguous`，扫描页有 `NO_TEXT_LAYER` / `SCAN_REQUIRES_OCR`，扫描可见词查询为 `not_found`。**这些 not_found 不证明扫描图像没有这些词。**

### 3.5 正式 case 的工具调用位置

Agent 根据真实 PDF 和合同先准备 `/app/work/layout.json` 与 `/app/work/queries.json` 后：

```bash
mkdir -p /app/work /app/output
python3 scripts/layout_evidence.py index \
  --input /app/work/layout.json --output /app/work/layout-index.json
python3 scripts/layout_evidence.py locate \
  --index /app/work/layout-index.json \
  --queries /app/work/queries.json \
  --output /app/work/location-report.json
```

脚本产物不是自动的最终答案。必须再按 `/input/task.md` 的真实 `output_contract` 组装 `/app/output/result.json`，保留原 case_id 和全部合同字段；如有未决项就维持 partial。

## 4. 样例性质与限制

`examples/` 的所有输入、断言、expected 输出均是 **SYNTHETIC 合成回归材料，不是正式竞赛结果**。双栏坐标与扫描都是手工构造；它们不能证明真实 PDF 解析率、OCR 准确率或语义蕴含。

脚本不直接处理 PDF 对象、字体、图像、OCR、旋转、自动栏序或 glyph offsets。该局部分别由上游提取器和 Agent 审计；无法取得即保留 uncertainty。当前 fidelity 规则故意有限，遇到非 ASCII 行尾断词、Unicode 兼容字符等变化可能不命中，应报告而不是扩大假匹配。
