---
name: corpus-forensics-registry
description: 当输入含 comparison-workorder.json / case.json 与多篇论文语料时使用。先做多文档语料取证（文档身份鉴定、PDF 解析保真审计、段落锚定注册表、相关性门控），再在注册段落之上构建带 source_document_id + paragraph_id + content_hash + quote 的比较矩阵与六维可比性检验；所有引用可机检、可查回，绝不编造取值。
---

# corpus-forensics-registry：先取证语料，再比较多文档

## 设计立场（贯穿全流程）

**比较表的质量上限由语料本身决定。** 同一论文多版本、重复上传、PDF 文本层损坏、
段落编号漂移，会让下游所有引用静默失效——矩阵填得再满也是错的。因此本 Skill
的顺序是强制的：**先对语料做取证（corpus forensics），拿到段落级锚定注册表之后，
才允许做任何字段抽取与比较。**

四条取证主线（对应 scripts/ 四个脚本）：

1. **文档身份鉴定**：规范化文本指纹（sha256）+ 8-gram shingle Jaccard，
   判定 `unique / exact_duplicate / near_duplicate / probable_version_pair`；
   下游比较只能以 canonical（unique）文档为单位。
2. **解析保真审计**：PDF 用 `pdftotext` 提取并与 `-layout` 模式交叉比对；
   统计 �、空页、短行；`parse_fidelity ∈ {good, degraded, failed}`，
   `failed/tool_missing` 不得抽取，记 `unreadable`。
3. **段落锚定注册表**：`paragraph_id = <DOCID>-P<序号>`，每段记
   `content_hash = sha256(规范化段落)[:12]`；所有引用必须同时给
   `paragraph_id` + `content_hash` + 逐字 `quote`，机检可查回、可发现语料换版。
4. **相关性门控**：工单维度词打分，`out_of_scope` 文档不进入矩阵但保留记录与证据。

判据与阈值见 `references/forensics-rules.md`；数据结构见 `references/registry-schema.json`。

## 第 0 步：输入识别

评测输入（组织方 v2 接口）位于 `/input`：

- `/input/case.json`：读取 `case_id` 与 `output_contract`（**逐字段原样照搬**）。
- `/input/task.md`：自然语言任务描述，抽取共同字段候选。
- `/input/comparison-workorder.json`：维度词与文档清单（对未知 schema 保持健壮，
  relevance_gate.py 会递归提取字符串词）。
- 语料文档：可能是**真实 PDF，无预提取答案层**。先 `pdftotext`；失败再
  `pdftoppm` 渲染 + OCR（OCR 文本一律按 `degraded` 标注）。
- 中间产物放 `/app/work`，最终交付放 `/app/output`。

**预算约束：64 次模型请求、900 秒。** 因此：先跑完全部机检脚本（零模型请求），
拿到取证报告后，尽早写出诚实的 partial result.json（取证结论 + 骨架矩阵 +
未填字段标 `not_reported`），再按字段优先级逐格加深。模型请求只花在
读段落、填格子、写结论上；不要把预算消耗在重复扫描原文上。

## 工作流程（分阶段，给出确切命令行）

以下命令假设语料在 `/input/corpus`（按实际路径替换），python3 仅用标准库。

### 阶段 1：语料取证（零模型请求）

```bash
mkdir -p /app/work/registry /app/output
# 1a. 注册表：指纹 + 近重复/多版本检测 + 段落锚定（PDF 自动调 pdftotext）
python3 scripts/build_registry.py /input/corpus --out /app/work/registry
# 1b. 独立保真审计（与注册表内嵌审计互为印证；可单独运行）
python3 scripts/parse_audit.py /input/corpus -o /app/work/registry/parse-audit.json
# 1c. 相关性门控（读 comparison-workorder.json；无工单则省略 --workorder）
python3 scripts/relevance_gate.py --registry /app/work/registry \
    --workorder /input/comparison-workorder.json --out /app/work/registry/relevance.json
```

阅读 `/app/work/registry/registry.json`，形成取证结论：

- 每篇文档的 `identity_verdict`：非 `unique` 的（exact_duplicate / near_duplicate /
  probable_version_pair）**只在取证报告中记录，绝不进入矩阵**；版本对存在数值冲突时
  保留冲突并在 uncertainty 说明。
- `parse_fidelity`：`failed/tool_missing` → 记 `unreadable`，不抽取；`degraded` →
  可抽取但逐格注明。
- `relevance.json` 中 `out_of_scope` 文档不进入矩阵，保留命中词证据。

### 阶段 2：在注册段落上构建比较矩阵

- 共同字段来自 task.md / workorder 的 dimensions × **全部 canonical 且 in_scope 论文**。
- 每个单元格写入 `/app/work/cells.jsonl`（每行一格）：

```json
{"field": "removal_efficiency", "value": "96 %", "status": "reported",
 "source_document_id": "DOC-A", "paragraph_id": "DOC-A-P006",
 "content_hash": "1b6ce233dabc",
 "quote": "the g-C3N4 catalyst achieved 96% removal of RhB within 90 min"}
```

- `quote` 必须是所引段落的**逐字子串**；`content_hash` 从
  `<DOCID>.paragraphs.jsonl` 原样抄取；`status ∈ {reported, not_reported, unclear, conflict}`；
  找不到的字段如实写 `not_reported`（不得携带 value）。
- **不得合并不同数据集或不同染料**；单篇摘要不满足多文档比较，矩阵必须覆盖
  全部 in_scope 论文的共同字段。

### 阶段 3：机检 + 六维可比性检验

```bash
# 3a. 机检锚点（任一失败非零退出并打印失败清单）
python3 scripts/verify_anchors.py --registry /app/work/registry \
    --cells /app/work/cells.jsonl --relevance /app/work/registry/relevance.json
# 3b. 渲染人类可读矩阵视图（渲染 ≠ 定量合成）
python3 scripts/render_matrix.py --registry /app/work/registry \
    --cells /app/work/cells.jsonl --out /app/output/comparison-matrix.md
```

在**任何定量合成之前**，逐格检验六个维度的可比性，并写入 result.json：

| 维度 | 检验内容 | 不可比时 |
|---|---|---|
| task | 是否为同一类实验任务（如均为光催化降解而非吸附） | 标 incomparable，不合成 |
| metric | 指标定义是否一致（removal% vs 矿化率 vs 脱色率） | 分列展示，注明定义差异 |
| units | 单位是否一致（%、min^-1、mg/L、g/L） | 只做显式换算，否则保留原单位 |
| material | 催化剂是否相同/同类（g-C3N4 vs N-TiO2 属不同材料） | 按材料分行，不跨材料平均 |
| pollutant | 污染物是否相同（RhB vs 亚甲基蓝，**不得合并不同染料**） | 按染料分组，各自成列 |
| budget | 条件预算是否可比（剂量、时间、初始浓度、光源功率） | 在 uncertainty 中声明 |

不可比与未报告项**保留**在矩阵中（status 标注），不得丢弃或臆造补齐。

### 阶段 4：写 /app/output/result.json

必须包含：

- `case_id`：从 `/input/case.json` **原样复制**。
- `output_contract` 中列出的**全部字段**：字段名原样照搬，逐字段填写；
  无法填写的诚实标注 `not_reported` 或 `unavailable`，不得省略字段。
- `status ∈ {success, partial, failed}`：`partial` 必须写明缺失边界
  （哪些文档 unreadable、哪些字段未覆盖、哪些维度不可比）。
- `sources`：每个结论对应 `{source_document_id, paragraph_id, content_hash, quote}`。
- `uncertainty`：解析降级、版本冲突、不可比维度、预算截断等。

若 case.json 无 `output_contract`，退化为
`{case_id, status, 主结果（取证结论+比较矩阵）, sources, uncertainty}`。

## 异常处理

| 异常 | 处理 |
|---|---|
| PDF 解析失败 / 无 pdftotext | 记 `tool_missing` 或 `failed` → 该文档 `unreadable`，不抽取；result.json 标 partial 并说明；可尝试 pdftoppm+OCR，产出按 degraded 标注 |
| 同一论文多版本（version pair） | 仅 canonical 版本进矩阵；数值冲突保留，写 uncertainty；机检 R2 会拦截对非规范版本的引用 |
| 精确/近似重复 | 只保留首份为 canonical；重复份记录在 registry，不进矩阵 |
| 主题无关文档 | relevance 判 `out_of_scope`，保留命中词证据，不进矩阵；机检 R4 拦截 |
| 语料被换版 / hash 不匹配 | verify_anchors R6 报错；停止引用该段，重新跑 build_registry |
| 预算不足（请求/时间将尽） | 立即落盘诚实 partial：已完成的取证报告 + 骨架矩阵 + 未覆盖字段列明缺失边界 |
| 工单 schema 未知 | relevance_gate 递归提取字符串词 + 内置词表，仍可用；无工单时全部 in_scope 并注明 |

## 诚实性

不得编造取值、段落、hash 或 quote；解析失败如实标注；多版本冲突保留不合并；
不可比维度不合成；本 bundle 不包含任何官方正式案例的答案
（examples/ 全部为合成示例）。

## 最小调用示例

见 `examples/`（**合成示例，非正式案例**）：

```bash
cd examples && bash run_example.sh
```

端到端演示：DOC-C 被识别为 DOC-A 的 `probable_version_pair`、
DOC-D 被门控为 `out_of_scope`、16/16 示例单元格通过机检、
渲染出带锚点的 comparison-matrix.md。触发机检失败的方法见 `examples/README.md`。
