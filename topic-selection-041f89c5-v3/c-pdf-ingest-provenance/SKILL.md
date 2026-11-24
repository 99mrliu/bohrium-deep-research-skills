---
name: pdf-ingest-provenance
description: 上游摄入取证取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与一批科研材料（含原始 PDF，无预提取文本层），要求完成文献综述、证据提取、选题或创新性评估并在 /app/output 交付结构化 result.json 时使用。核心立场：下游一切结论的可信度不超过上游文本层的可信度——先用 scripts/ingest_register.py 把材料变成带 SHA-256 登记、逐页字符统计的文本层（PDF 用系统工具真实解析，不假设有预提取层），extraction_qc.py 对文本层分级（ok/ok_with_notes/suspect/unreadable）并把每条引文定位到 文件+页码+字符偏移；unreadable 来源上的结论一律降级。不适用：输入已是结构化记录且无 PDF/扫描件的任务。
---

# pdf-ingest-provenance：文本层不立，结论不立

## 核心主张

评测环境明说"PDF 无预提取答案层"——基础 Agent 的典型失败是：**凭文件名和摘要想当然地引用 PDF 内容**，或解析失败后静默改用"常识"补写。本技能把摄入变成取证：每个来源先登记哈希、再真实解析、再逐页质检，每条进入综述的引文必须能被 `locate` 机器定位到页；解析不了的来源，其上的结论必须降级，不许用想象填坑。

## 运行时契约（必须先读）

1. 输入在 `/input`：`task.md`、`case.json`（含 `case_id`、`output_contract`）、材料文件。逐文件读真实内容，不依据文件名或标签猜测。
2. 若存在 `/input/environment/resources.yaml`，先读它确认可用的 PDF 解析/OCR 工具。
3. 中间产物写入 `/app/work`，最终交付写入 `/app/output`。
4. `/app/output/result.json` 必须含 `case_id`（与 case.json 逐字一致）与 `output_contract` 声明的**全部原始字段**，字段名逐字照抄。
5. 预算：约 64 次模型请求、900 秒、单次响应 16384 token。第一时间写 result.json 骨架（契约字段置 null、status=in_progress），逐阶段回填。
6. 诚实状态：`status` 只能是 `success` / `partial` / `failed`；partial 写明缺什么、为什么。
7. 禁止伪造：解析不出就登记解析不出；不依据错误的领域标签补造数据。

## 工作流程

### 阶段 1：摄入登记（最先做，先于一切阅读）

```
python3 /skills/weekly-skill/scripts/ingest_register.py \
    --input /input --work /app/work
```

产出 `source_registry.json`（每来源：SHA-256、类型、页数、逐页字符统计、提取状态）与 `ingest_report.md`。规则细节见 `references/ingest_protocol.md`。

### 阶段 2：文本层质检

```
python3 /skills/weekly-skill/scripts/extraction_qc.py qc \
    --registry /app/work/source_registry.json --out /app/work/qc
```

- `unreadable`（exit 1 时列出）：扫描件/解析失败——按 resources.yaml 换 OCR 或 pdf-text-tool 重试一次；仍失败的来源登记为不可用，**其支撑的结论全部降级 partial 并在不确定性中说明**。
- `suspect`：乱码页——引用前必须人工目检对应页文本。
- `ok_with_notes`：空页/低文字页已记录，引用避开这些页。

### 阶段 3：研究问题结构化与筛选

同常规：问题五要素（对象、变量、基线、预期方向、可证伪条件）；纳排决策留痕；覆盖边界声明落盘。筛选对象是**通过质检的文本层**，不是文件名列表。

### 阶段 4：证据提取（页级锚点强制）

每条打算进入综述的证据：从 `/app/work/sources/*.txt` **复制**逐字引文（凭记忆转述的一律不算），然后机器定位：

```
python3 /skills/weekly-skill/scripts/extraction_qc.py locate \
    --registry /app/work/source_registry.json --quote "逐字引文"
```

- 命中 → 证据表登记 `locator = 文件 第N页`（格式见 `references/locator_format.md`）；
- 未命中（exit 1）→ 回文本层重新复制；常见原因是转述冒充引文或跨页拼接（跨页引文须拆成两段分别定位）。修复不了就放弃该证据。

### 阶段 5：综合与交付

1. 四项交付（已有工作比较、创新点判定、可行性前提、不确定性）只引用带页级锚点的证据；冲突证据双方均列出。
2. 回填 result.json；把 `source_registry.json`、`ingest_report.md`、`qc_report.json/md` 复制到 `/app/output` 作可复核附件。
3. 终检：result.json 中每条文献相关陈述都能指出其 locate 命中记录；指不出的删除或降级。

## 异常处理

| 情形 | 处置 |
|-|-|
| pdftotext 缺失 | 按 resources.yaml 用运行环境的 pdf-text-tool 提取为同名 .txt 放入 sources/，在 registry 手工补登记提取工具名；不静默跳过 |
| 扫描件（empty_extraction） | 用 OCR 工具重试一次；仍空 → unreadable，相关结论降级 |
| 引文 locate 未命中 | 回原文重复制；两次失败则弃用该证据并登记 |
| 记录型材料（JSON/CSV） | 按结构读取，不作为引文来源；其中事实在证据表标 `[来源:文件名(记录)]` |
| 预算危急 | 已质检来源上的结论优先回填（partial）；未摄入材料在不确定性中列明 |

## 红线

- 不许引用未经 locate 命中的"引文"；不许把解析失败的材料当作已读；不许在 unreadable 来源上给出非 partial 结论；不许用模型记忆替代文本层。

## 最小示例

`examples/` 内有**合成示例**：`make_fixtures.py` 生成两份纯 ASCII 最小 PDF（虚构论文；beta 故意含一个空白页），随后 ingest → qc → locate 全流程真实执行。命令与预期输出见 `examples/minimal_example.md`，实跑产物在 `examples/output/`。
