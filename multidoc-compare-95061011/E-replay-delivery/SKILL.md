---
name: replay-delivery-contract
description: 多文档比较与整合任务的可复跑交付 Skill。当输入含 comparison-workorder.json / case.json 与多篇论文语料时使用。立场为"记录为体、渲染为影"：work/ 下 JSONL 记录是唯一事实来源，全部人读产物由确定性渲染器生成并自校验对账，契约 lint 钉死 result.json，manifest 断点续跑，replay 提供字节级复跑证明。
---

# replay-delivery-contract：可复跑的多文档比较交付

## 设计立场（先读这一段）

比较结果的价值取决于别人能否复跑。大多数 agent 交付的比较矩阵/整合报告是"一次性散文"：矩阵数字与记录对不上、result.json 缺字段、换一台机器就复现不了。本 Skill 的立场：

- **记录为体、渲染为影**：`work/cells.jsonl`（每格一条单元格记录）与 `work/decisions.jsonl`（每条可比性判定）是唯一事实来源。任何人读产物（comparison-matrix.md、integration-report.md、result.json）一律由 `render_all.py` 从记录**确定性生成**：同样的记录永远产出字节一致的产物（排序确定、无时间戳、无随机）。
- **渲染器自校验**：渲染后把生成的 markdown 表格数字回解析，与 JSONL 逐格对账；对不上就非零退出，宁可不交付也不交付对不上账的表。
- **契约优先**：开工第一步读 `case.json` 的 `output_contract`，生成 `result.schema.json` 钉死 result.json 的字段清单（字段名原样照搬），此后所有渲染朝它收口，交付前由 `contract_lint.py` 强校验。
- **复跑证明**：`replay.py` 重跑渲染并与已交付产物逐字节比对，输出 `replay-report.json`，让别人能验证"这些产物确实能从记录复现"。
- **过程质量控制**：`manifest.json` 登记每个阶段的输入 sha256 与输出清单，重跑时已 completed 且输入未变的阶段自动跳过；预算不足时按降级梯（`references/degradation-ladder.md`）随时安全交付，任何降级如实体现在 `result.json` 的 `status` 与 `uncertainty` 中。

**禁止事项**：不得手改任何渲染产物（markdown/result.json）——要改就改 JSONL 记录然后重渲染；不得合并不同数据集或不同染料；不得丢弃不可比项与未报告项；不得伪造来源段落；单篇摘要不满足多文档比较。

## 第 0 步：输入识别

评测时输入位于 `/input/`：

| 文件 | 作用 | 缺失时 |
|---|---|---|
| `/input/case.json` | 含 `case_id` 与 `output_contract`（契约字段清单） | 无 `output_contract` 时退化为 `{case_id, status, result, sources, uncertainty}` 基础契约（init_contract.py 自动处理） |
| `/input/task.md` | 任务陈述 | 以 comparison-workorder.json 的 task_statement 为准 |
| `/input/comparison-workorder.json` | v2 工单：共同字段、六维度判定基准、规则 | 缺失则从 task.md 推断共同字段与基准，并在 uncertainty 中声明 |
| 语料文档 | 可能是真实 PDF，**无预提取答案层** | 先 `pdftotext <pdf> <txt>`；失败再 `pdftoppm` 渲染 + OCR；全程把提取的段落编上 paragraph_id 再入记录 |

中间产物放 `/app/work`，最终交付放 `/app/output`。

`/app/output/result.json` 必须含：`case_id`（原样复制）、`case.json` 的 `output_contract` 全部字段（字段名原样照搬）、`status ∈ {success, partial, failed}`、`sources`、`uncertainty`。`partial` 必须在 `uncertainty` 中写明缺失边界。

## 工作流程（分阶段；每个阶段结束都是可交付状态）

预算：**64 次模型请求 / 900 秒**。时间盒如下，超时立即按降级梯落盘当前状态。

| 阶段 | 内容 | 时间盒 | 请求预算 | 命令 |
|---|---|---|---|---|
| 0 | 契约+骨架：**必须先落盘 /app/output** | ≤60s | 0 | `python3 scripts/init_contract.py --case /input/case.json --workdir /app/work --outdir /app/output` |
| 1 | 语料抽取 → 写 `work/cells.jsonl`（格式见 references/record-format.md） | ≤360s | ≤40 | pdftotext 提取 → 逐格一条 JSONL 记录 |
| 2 | 六维度可比性判定 → 写 `work/decisions.jsonl` | ≤150s | ≤12 | 逐判定一条 JSONL 记录 |
| 3 | 渲染+自校验+契约 lint | ≤90s | 0 | `python3 scripts/render_all.py --workdir /app/work --outdir /app/output && python3 scripts/contract_lint.py --case /input/case.json --workdir /app/work --outdir /app/output` |
| 4 | 复跑证明 | ≤60s | 0 | `python3 scripts/replay.py --workdir /app/work --outdir /app/output` |
| 缓冲 | 降级落盘 | 剩余 ≥180s | 剩余 | 见 references/degradation-ladder.md |

阶段 1/2 中可以随时运行阶段 3：记录写到哪，产物就渲染到哪——这就是降级梯的实现方式。重跑时 `render_all.py` 通过 manifest 判断输入未变则跳过（幂等），`--force` 强制重渲染。

manifest 手工查询：

```bash
python3 scripts/manifest.py status --workdir /app/work
python3 scripts/manifest.py should-skip --workdir /app/work --stage render --inputs /app/work/cells.jsonl   # 退出码 0=跳过, 1=需重跑
```

## v2 强制要求 → 本 bundle 的承载方式

- 覆盖全部语料论文的共同字段比较矩阵，每格带 exact `source_document_id` 与 `paragraph_id` → `cells.jsonl` 每格一条记录，渲染矩阵每格带 `⟦C-xxx⟧` cell_id 可回溯。
- 定量合成前检验 task、metric、units、material、pollutant、budget 六维度可比性 → 每条 cell 记录带六维度判定，渲染出可比性矩阵（C/N/NR/U），合成结论只出自 `decisions.jsonl`。
- 不得合并不同数据集或不同染料；保留不可比与未报告项 → verdict=blocked 的判定禁止合并；`not_reported` 以 `— ⟦NR⟧` 保留在矩阵中并进入 uncertainty。
- 记录格式细则见 `references/record-format.md`；result.json 契约细则与 lint 项清单见 `references/contract-spec.md`。

## 异常处理

| 异常 | 检测手段 | 处置 |
|---|---|---|
| 渲染对账失败 | `render_all.py` 自校验（markdown 数字回解析 ≠ JSONL）非零退出 | 停止交付该表格；检查 cells.jsonl 中 `numeric_value`/`value`/`unit` 一致性，修复后 `render_all.py --force` 重跑。**不得手改 markdown** |
| 契约缺字段 | `contract_lint.py` 报 `output_contract 字段缺失` | 回 `init_contract.py` 核对 case.json 的 output_contract；字段名必须原样照搬；修复记录后重渲染 |
| 预算见底 | 时间盒超时或请求数超限 | 按 `references/degradation-ladder.md` 降级：立即对当前 `work/` 记录运行 render_all + lint 落盘；`status=partial` 并在 uncertainty 写明缺失边界 |
| 记录被手改 | lint 数值交叉校验报错，或 manifest 输入 hash 与阶段登记不符 | 以 JSONL 记录为唯一事实来源重渲染全部产物；若记录本身被污染，回退到最近一致状态并在 uncertainty 声明 |

## 最小调用示例（合成示例，非正式案例）

`examples/` 内含完整可运行的最小**合成**示例（3 篇虚构光催化论文、合成 case.json/工单、示例记录、一键脚本）：

```bash
cd <bundle 根目录>
bash examples/run_example.sh
```

脚本依次执行 init_contract → render_all → contract_lint → render_all 强制重渲染并 diff 演示字节确定性 → replay 复跑证明，产物写入 `examples/output/`（模拟 /app/output）。预期：lint 通过、两次渲染 diff 为空、replay-report.json 全部 `bytes_equal: true`。详见 `examples/README.md`。

本 bundle 不含官方正式案例答案；examples/ 全部为虚构合成数据。
