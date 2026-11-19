# 完整工作流程（kbqa-anchor-verifier）

## 阶段 0：读题与契约（模型，≤3 次请求）

1. 读 `/input/case.json` 与 `/input/task.md`。
2. 记录：`case_id`、问题列表（`questions` / `search_tasks`）、材料目录、输入约束、`output_contract` 的每个字段与要求。
3. 立即可写 `/app/work/case_brief.json`，把上述内容结构化，后续步骤只引用它，避免重复读题。

## 阶段 1：盘点与索引（脚本，0 次请求）

```bash
python3 /skills/weekly-skill/scripts/kb_build_index.py --input /input --work /app/work --out /app/output
```

确认输出尾部 `indexed/…/skipped/…`；被跳过文件进入 `skipped_files`，逐个写明原因。

## 阶段 2：检查点（模型，1 次写盘）

读回 `artifacts/kb_index.json`，把 `result.json` 骨架写为 `status="partial"`：`answers` 按问题逐条占位，`uncertainty` 先记录 skipped 文件。此后每完成一题更新一次 `result.json`。

## 阶段 3：逐题检索与选段（模型 + 脚本）

每题执行：

```bash
python3 /skills/weekly-skill/scripts/kb_retrieve.py \
    --index /app/output/artifacts/kb_index.json --query "<子论断1>" --top 5
```

1. 把问题拆成可独立核验的子论断（每题 1–4 个）。
2. 对每个子论断跑检索，从 `top_hits` 中人工选定覆盖度最高的原文行。
3. 从抽取文本中逐字复制引文（用 `sed -n 'X,Yp' work/extracted/<Fxx>.txt` 或读取文件），记下 file_id 与行区间。

## 阶段 4：写答案草稿（模型）

按 `resources/citation_contract.md` 组织答案。同时写两份中间件：

- `/app/work/citations.jsonl`：每条引文一行，含全局唯一 `id`（C1、C2…）、`file_id`、`locator`、`quote`。
- `/app/work/answers_draft.json`：问题—论断—引文 id 的映射。

## 阶段 5：机器核验与修订（脚本 + 模型）

```bash
python3 /skills/weekly-skill/scripts/kb_verify.py \
    --index /app/output/artifacts/kb_index.json \
    --citations /app/work/citations.jsonl \
    --report /app/output/artifacts/citation_verification.json
```

按 SKILL.md "核验不通过时的处置" 逐条修订：能修的修，修不了的删论断或标无依据。修订后若引文变了，重跑一次核验。

## 阶段 6：收尾（脚本 + 校验）

```bash
python3 /skills/weekly-skill/scripts/kb_finalize.py --case /input/case.json --work /app/work --out /app/output
```

然后按 SKILL.md 自查清单逐条确认。预算过半立即跳到本阶段交付 partial 结果。

## 失败与恢复速查

| 情况 | 处置 |
|-|-|
| PDF 抽取失败 | 记 `extraction_unavailable`；若平台提供 OCR 工具，先 OCR 再索引 |
| 文件无读权限 | 记 `skipped_files`，不引用该文件，答案中说明证据缺口 |
| 引文核验大面积失败 | 优先检查是否从抽取文本逐字复制；相似度 ≥0.85 的按 best_match 修 |
| 两个问题争用同一证据 | 允许共享；两处都写明同一坐标 |
| case.json 与实际文件冲突 | 以实际文件为准，冲突写入 `change_log` |
| 预算将尽 | 立即 finalize，交付 partial 并注明未完成项 |
