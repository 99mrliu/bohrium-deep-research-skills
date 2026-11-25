---
name: uspto-facsimile-forensics-lab
description: 当任务要求对 USPTO 传真版专利 PDF 或纯文本专利记录进行源文档取证与版面锚定时触发本技能：清点输入材料并计算 SHA-256、以 poppler 或标准库回退提取 PDF 文本层、将每一项书目事实锚定到具体文件＋页＋行/字节区间并附逐字引文、声明并保留 OCR 合并边界、并生成传真件与数据库式记录之间的差异台账；未声明的模糊匹配一律拒绝，绝不猜测内容。
---

# USPTO 传真取证与版面锚定实验室（uspto-facsimile-forensics-lab）

## 一、用途与适用条件

本技能的重心是**源文档取证与版面锚定（document forensics & facsimile fidelity）**，即证据层工作，且仅覆盖证据层：

1. 对输入材料目录（如评测环境的 `/input`）逐文件清点，记录路径、SHA-256、字节数与类型（按魔数与扩展名判定，**读取真实文件内容，绝不从文件名推断**）。
2. 从 USPTO 传真版 PDF 中提取逐页文本层：优先使用 PATH 上的 `pdftotext`（poppler）；缺失时回退到本技能自带的纯标准库提取器（解析未压缩或 FlateDecode 内容流中的 `Tj`/`TJ` 字符串）；两者皆不可用时标记 `extraction_degraded: true` 并记录原因，**绝不猜测内容**。纯文本专利记录直接作为单页文本层处理。
3. 将每一项提取出的书目事实（公开号、申请人、发明人、申请日等）锚定到具体来源：文件 SHA-256 ＋ 页码 ＋ 行区间或字节区间 ＋ 逐字引文。多个候选位置全部列出，绝不静默择一。
4. 对 OCR/空白容差实行**事先声明**制度：凡需跨行空白折叠或跨 OCR 页边界合并才能命中的匹配，必须在策略 JSON 中显式声明（`allow_whitespace_collapse` / `allow_page_boundary_merge`），否则拒绝并退出码 1。WO 记录跨 OCR 页边界合并之类的边界事实必须保留并在输出中声明，不得静默重拆。
5. 生成传真件与数据库式记录之间的差异台账：逐字段给出传真值＋锚点、记录值＋锚点与严重级别（`none`/`minor`/`major`）；完全一致记为 `consistent`。

**本技能明确不做以下事项**（属于其他 bundle，遇到时应路由出去，不得在结果中伪造）：

- 专利号格式归一化、同族合并（number normalization / family merging）；
- 检索式设计与执行（retrieval query design）；
- 法律状态、许可或权利有效性判断（legal-status / license judgements）——官方法律状态未知时必须如实写明"未知"；
- 交付契约（output contract）完备性校验（delivery-contract validation）。

## 二、运行时契约

评测方将本技能安装于 `/skills/weekly-skill`，并以官方 DeepSeek Harness 在 3 个固定隐藏案例上运行。输入为 `/input/case.json`＋`/input/task.md`＋材料文件（6 份专利记录文本、3 份 USPTO 传真原件 PDF、对比论文；号码/主题查询；带来源定位的声明版本；官方法律状态未知——必须如实声明；观察到的链接不构成穷尽同族；WO 合并 OCR 边界必须保留）。工作目录为 `/app/work`，交付物为 `/app/output/result.json`。

本技能在结果层遵守如下契约：

1. `/app/output/result.json` 必须包含：逐字复制的 `case_id`；诚实的 `status`（`ok`/`partial`/`failed`）；`sources`（路径＋SHA-256 列表，与清点结果一致）；`uncertainty`；`change_records`；以及**镜像该案例 `output_contract` 的全部字段**（无法填写的字段置 `null` 并在 `uncertainty` 中说明原因）。
2. 预算约束：64 次模型请求 / 900 秒 / 每次响应 16384 token。因此**必须先把诚实的部分骨架写入 `/app/output/result.json`**，再增量改进；每次改进重写 `result.json` 并向 `change_records` 追加一条记录。
3. 绝不伪造：任何书目事实必须能回溯到本技能产生的锚点；部分结果必须点名其局限（哪些文件降级、哪些字段未锚定、法律状态未知等）。
4. 所有材料文件必须先读真实内容再处理；文件名仅用于定位，不用于推断事实。

## 三、调用方式（有序流水线）

以下命令均假定在技能根目录（如 `/skills/weekly-skill`）下执行，产物写入工作目录（示例为 `/app/work`，评测时按实际工作目录替换）：

```bash
# 第 1 步：清点输入材料并提取文本层（PDF 自动选择 poppler 或标准库回退）
python3 scripts/facsimile_register.py --input-dir /input --out-dir /app/work/register

# 第 2 步：为每一项书目事实定位锚点（策略文件须事先声明容差；无容差需求可省略 --policy）
python3 scripts/page_anchor.py locate \
  --pages /app/work/register/extracted/<sha256>.pages.json \
  --field publication_number --value "US 2099/0123456 A1" \
  --policy /input/anchor_policy.json \
  --out /app/work/anchors/publication_number.json

# 第 2b 步（可选）：核验既有锚点记录的真实性（防伪造/防陈旧）
python3 scripts/page_anchor.py verify \
  --pages /app/work/register/extracted/<sha256>.pages.json \
  --anchor /app/work/anchors/publication_number.json

# 第 3 步：传真件字段与数据库式记录逐字段比对，生成差异台账
python3 scripts/facsimile_discrepancy.py \
  --spec /app/work/fields_spec.json \
  --facsimile-pages /app/work/register/extracted/<facsimile_sha256>.pages.json \
  --record-pages   /app/work/register/extracted/<record_sha256>.pages.json \
  --policy /input/anchor_policy.json \
  --out /app/work/discrepancy_ledger.json

# 第 4 步：将清单、锚点、边界声明与差异台账汇总进 /app/output/result.json（先骨架后增量）
```

其中 `<sha256>.pages.json` 的具体文件名从第 1 步产物 `facsimile_inventory.json` 的 `extraction.pages_file` 字段读取，不得猜测。`fields_spec.json` 的格式为 `{"fields": [{"name": ..., "facsimile_value": ..., "record_value": ...}, ...]}`。

## 四、输入输出解释

- **`facsimile_register.py`**：输入 `--input-dir`（材料目录）、`--out-dir`、`--no-poppler`（可选，强制标准库回退）。输出 `facsimile_inventory.json`（每文件：path、sha256、size_bytes、kind、extraction{method, degraded, reason, pages[逐页字符数], pages_file}）与 `extracted/<sha256>.pages.json`（逐页全文）。
- **`page_anchor.py locate`**：输入 pages JSON、字段名、字段值、可选策略 JSON。输出锚点记录数组：`{field, file, file_sha256, page, line_span, byte_span, byte_span_basis, quote, match_type}`；`match_type ∈ {exact, whitespace_collapsed, page_boundary_merged, page_boundary_merged+whitespace_collapsed}`。多候选全部列出（`candidate_count` 给出数量）。
- **`page_anchor.py verify`**：输入 pages JSON 与锚点 JSON，核验 file_sha256、逐字引文与字节区间是否真实成立。
- **`facsimile_discrepancy.py`**：输入字段比对规格、传真侧 pages JSON、记录侧 pages JSON、可选策略。输出差异台账：汇总计数与逐字段 `{field, status, severity, facsimile{value, anchors}, record{value, anchors}, notes}`。差异是数据而非失败：存在 `major` 差异时仍退出 0；只有当某个值无法锚定时才退出 1。
- **退出码统一约定**：`0` 正常；`1` 检查/违例（值不存在、容差未声明、锚点核验失败、字段不可锚定）；`2` 用法错误（参数缺失、JSON 无法解析等）。

## 五、异常处理

1. **缺少 PDF 工具（poppler 不在 PATH）**：自动回退到标准库提取器，清单中记 `method: stdlib-fallback`；也可用 `--no-poppler` 显式强制。
2. **加密或不可提取的 PDF**：检测到 `/Encrypt` 或对象结构无法解析时，标记 `extraction_degraded: true` 并写明原因，继续处理其余文件，绝不猜测内容。
3. **零长度文本层**（扫描影像或纯矢量 PDF）：标记降级，原因注明"zero-length text layer"；OCR 超出本技能范围，必须在 `uncertainty` 中声明该文件无可用文本层。
4. **OCR 歧义与容差**：只有策略 JSON 事先声明的容差才被允许；未声明的空白折叠或跨页匹配置退出码 1 并给出明确拒绝信息。已声明的容差匹配在锚点中以 `match_type` 与策略快照留痕。
5. **多候选位置**：全部列出，由上层流程裁决；脚本绝不静默择一。

## 六、限制

- 标准库回退提取器仅支持未压缩与 FlateDecode 内容流，且按对象结构线性解析；对加密流、对象流（ObjStm）、CID 字体映射、复杂排版还原能力有限。遇到此类文件如实降级，不做内容臆测。
- 本技能不做 OCR；扫描件无文本层时只能声明降级。
- 本技能不做号码归一化、同族合并、检索式设计、法律状态判断与交付契约校验；这些子任务应路由至相应 bundle。观察到的链接不构成穷尽同族；官方法律状态未知时一律如实写"未知"。
- 锚点的 `line_span`/`byte_span` 以提取文本层为准，而非传真影像的像素坐标。

## 七、自查方法

在技能根目录运行：

```bash
python3 scripts/selfcheck.py
```

自查基于 `examples/fixtures/` 下的全合成夹具，端到端断言：对真实最小 PDF 的注册（含强制标准库回退路径）、精确锚点命中、伪造/不存在引文以退出码 1 拒绝、未声明容差以退出码 1 拒绝、已声明容差生效、跨页边界合并策略生效、锚点核验通过/拒绝、差异被检出且一致字段判为 consistent。全部通过时打印汇总并退出 0。
