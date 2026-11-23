---
name: src-fidelity-item-forge
description: 文献/材料阅读任务的上游材料保真与可判性门禁技能：建立源锚点索引、机器逐字核验引文、阻断页码漂移与幻觉，并支持 T1 阅读问答解析翻译抽取及 T2 benchmark-DRAFT 题卡起草。Use when a task requires source-grounded answers or benchmark item drafting with quote-level verification, anchor fidelity, and machine-enforced judgeability.
---

# src-fidelity-item-forge

## 用途与适用条件

适用于必须“判得动”的材料任务：每条证据引文都要能在其声称锚点中被机器逐字找回；每道 T2 题卡都必须通过可判性清单。支持 PDF 及段落/表格文本，不依赖图片像素金标。机器只验证逐字锚定，不验证科学语义，因此禁止把 `pass` 解释为内容必然正确。

## 运行时契约

1. 平台将本技能装在 `/skills/weekly-skill`；官方 DeepSeek Harness 在 3 个隐藏固定案例上各跑 3 次。
2. 每案输入为 `/input/case.json`、`/input/task.md` 及 `/input` 源材料。`case.json` 含 `case_id` 与 `output_contract`；契约字段集必须运行时动态读取，不得假设固定字段名。
3. 源材料可为真实 PDF，或 txt/md/json 段落、表格、记录文本；revision2 可能只提供段落/表格文本。
4. 工作目录为 `/app/work`；最终交付 `/app/output/result.json`。它必须保留原始 `case_id`，含 `output_contract` 全部字段；无法填充处置 `null` 并记入 `uncertainty`，绝不编造。
5. `result.json` 还须含诚实 `status`（成功/部分完成/无法判断/拒答）、`status_reason`、`sources`、`uncertainty`、`change_records`。`部分完成` 必须明确局限；有未处理 `fail/degraded` 不得交付为成功。
6. 预算为 64 次模型请求、900 秒、每响应 16384 tokens。先尽早写合法部分结果，再增量完善。
7. 本技能的可编辑预览产物是文本核对报告与结构化清单：`source_index.json`、`verdicts.json`、`failure_analysis.md`、`scoring_record.json`；不要求图片。
8. Python 仅使用标准库（3.8+）；可选调用平台预装 `pdftotext/pdfinfo`。缺失时必须优雅降级，绝不崩溃。
9. 技能包为 UTF-8 文本，无符号链接，不依赖网络。本技能不含任何隐藏案例预制答案；`examples/` 全部是合成示例。

## 依赖与产物

- `scripts/source_index.py`：材料哈希、稳定锚点、归一化与偏移映射。
- `scripts/quote_gate.py`：逐条核验 `(locator, quote)`。
- `scripts/item_forge.py`：T1 结构校验或 T2 题卡可判性门禁。
- `scripts/export_result.py`：契约驱动汇总导出。
- 规范：`references/anchor_spec.md`、`references/judgeability_checklist.md`。

## 工单识别

第 1 步读取 `/input/task.md`：若文本含“出题 / 题卡 / benchmark / DRAFT / 草拟 / 4道 / 四道”任一关键词，判为 T2；否则判 T1。T2 正式题数固定 4，不得因材料短而少交；本技能的合成示例仅通过 `--expected-count 2` 演示机制。

- **T1 阅读问答/解析/翻译/抽取**：逐题作答；关键论断给 locator 与逐字 quote；未报告或无法判断必须显式标记，标记 claim 不得含具体数值。
- **T2 benchmark-DRAFT**：从段落/表格文本起草 4 张题卡。每卡含任务、材料范围、参考答案、0/1/2 评分规则、证据锚点、难度、数据授权说明、答案唯一可辩护说明。

## 工作流程

### 第 0 步：尽早锁定部分结果

立即执行：

```bash
python3 /skills/weekly-skill/scripts/export_result.py --case /input/case.json --work-dir /app/work --output-dir /app/output --init
```

无论材料是否可读，都生成合法 `result.json`，状态为“无法判断”，占位字段置 `null`。

### 第 1 步：建立源索引

```bash
python3 /skills/weekly-skill/scripts/source_index.py --input-dir /input --output /app/work/source_index.json
```

PDF 按页锚定；txt/md 按空行分段；json 按记录编号。输出含 sha256、字节数、degraded 标志、notes、归一化串与原文偏移映射。

### 第 2 步：起草工作文件

T1 在 `/app/work/answers.json` 中给每题 `id/answer/claims/evidence`；T2 在 `/app/work/items.json` 中给 `item_bank`。引文从原文复制，不写出处不明的概括。随后运行 `item_forge.py` 做结构门禁（尚无 verdict 时可处于 `pending_verification`）。

### 第 3 步：机器核验引文

```bash
python3 /skills/weekly-skill/scripts/quote_gate.py --work-file /app/work/items.json --index /app/work/source_index.json --output /app/work/verdicts.json
```

T1 把工作文件路径换成 `answers.json`。机器仅在声称锚点命中才 `pass`；只在别处命中是 `fail`（锚点漂移）；全库不命中先运行抽取缺陷分类器，可判 `degraded`，否则 `fail`。

### 第 4 步：修正或争议迭代

依据 `verdicts.json` 修 locator、回源复制 quote，或删除不受支持的论断/题卡。疑似抽取缺陷时重建索引并复跑；不能恢复原文时保留 degraded 与争议建议，不得人工宣布 pass。

### 第 5 步：终检与导出

```bash
python3 /skills/weekly-skill/scripts/item_forge.py --task /input/task.md --work-plan /app/work/items.json --verdicts /app/work/verdicts.json --output /app/work/items_validated.json
python3 /skills/weekly-skill/scripts/export_result.py --case /input/case.json --work-dir /app/work --output-dir /app/output
```

T1 使用 `--answers /app/work/answers.json`。`export_result.py` 会写 `result.json`、`failure_analysis.md`、`scoring_record.json`；评分中证据锚定维度完全由机器 verdict 决定。

## 异常处理

| 异常 | 行为 |
|---|---|
| `pdftotext` 缺失 | 文档和总索引置 `degraded:true`；notes 给出人工粘贴页文本指引；继续索引其他材料。 |
| `pdfinfo` 缺失 | 用整篇 `pdftotext` 输出并按换页符分页，notes 记录降级。 |
| PDF 加密/口令 | 不猜测内容；该文档 degraded，记录原因与人工粘贴指引。 |
| JSON 畸形 | 写缺陷记录并继续；对应材料或工作文件不得产出成功状态。 |
| 输入目录缺失 | 立即保留 `--init` 的部分结果；索引 degraded，状态不谎称成功。 |
| 超时风险 | 限制 PDF 子进程时间；失败页记录缺陷，继续后续可判工作。 |
| 契约字段缺失/冲突 | 字段置 `null` 或保留核心运行字段，并记录 uncertainty。 |

## 交付前自查清单

- [ ] 已先执行 `--init`，最终 `result.json` 仍含原始 `case_id`。
- [ ] 每个动态契约字段均已从工作文件同名键填充；缺失为 `null` 且列入 uncertainty。
- [ ] 所有交付论断/题卡的证据 verdict 均为 `pass`，无未处理 `fail/degraded`。
- [ ] T2 恰好 4 张 `fit` 题卡；unfit 未计入正式题集。
- [ ] `failure_analysis.md` 为空或逐条说明局限；`scoring_record.json` 与机器裁决一致。
- [ ] 输出无运行时刻、无网络依赖、无符号链接，文本均为 UTF-8。

## 限制

1. 机器门禁只证明归一化后的引文在所称锚点逐字存在，不证明参考答案科学正确。
2. PDF 表格错位、扫描页或编码缺陷可能导致 degraded；修复抽取前不得强行交付。
3. 本 bundle 没有隐藏案例答案；示例材料和题卡均为合成演示。