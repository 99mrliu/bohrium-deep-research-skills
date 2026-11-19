---
name: kbqa-anchor-verifier
description: 科研知识库问答的"逐句锚定 + 引文机器核验"工作流——先对输入资料库建哈希索引与行号化文本，再把答案中每个关键论断绑定到库内原文的逐字引文与可定位坐标（文件、SHA-256 版本、行/页区间），最后用确定性脚本逐条机器核验引用真实性：核验不通过的论断必须改写、降级为推测并明示、或标记为"库中无依据"，绝不允许带着失效引用交付。Use when a task asks to answer questions over a local scientific document library with verifiable source citations (带来源引用的问答, 证据回链, 逐句对应, 引用核验, 多文件检索, /input/case.json, result.json).
---

# 逐句锚定问答与引文机器核验（kbqa-anchor-verifier）

## 何时使用

平台给出 `/input/case.json` + `/input/task.md`，其中包含一个本地科研资料库（跨目录、多格式、可能含重复副本与历史版本）和若干检索/问答任务，要求交付带来源定位、可复核的答案时，使用本 Skill。结果写入 `/app/output`，其中 `result.json` 必须包含 `case_id`、`case.json` 的 `output_contract` 要求的全部字段，以及诚实的 `status` / `sources` / `uncertainty` / `change_log`。

本 Skill 的增益在答案侧：回答中的**每一个关键论断**都携带逐字引文与机器可核验坐标，且全部引用已经过确定性脚本核验。目录整理、版本辨识只做取证的必要前置，不作为交付中心。

## 运行方式（五步）

```bash
SKILL=/skills/weekly-skill

# 1) 盘点输入并建索引：哈希 + 行号化文本抽取（先落 partial result.json 做检查点）
python3 $SKILL/scripts/kb_build_index.py \
    --input /input --work /app/work --out /app/output

# 2) 读 /input/case.json，取出问题列表与 output_contract；立即把骨架结果写入
#    /app/output/result.json（status="partial"，所有 contract 字段先填空值或占位说明）。

# 3) 逐题检索候选证据（BM25-lite 行级命中）
python3 $SKILL/scripts/kb_retrieve.py --index /app/output/artifacts/kb_index.json \
    --query "<问题或子论断>" --top 5

# 4) 作答：每个论断写成 claim + evidence 列表。证据对象格式见
#    resources/citation_contract.md，坐标为 [Fxx|哈希8位|L起-L止]"逐字引文"。

# 5) 机器核验全部引用，再据核验报告修订答案并收尾
python3 $SKILL/scripts/kb_verify.py \
    --index /app/output/artifacts/kb_index.json \
    --citations /app/work/citations.jsonl \
    --report /app/output/artifacts/citation_verification.json
python3 $SKILL/scripts/kb_finalize.py \
    --case /input/case.json --work /app/work --out /app/output
```

## 引用语法与锚定规则

引用写在论断之后、句读之前：`…结论。[F07|a3f2c1d9|L14-L17]"原文逐字片段"`。

- `F07`：索引中的 `file_id`，对应 `kb_index.json` 里的一条真实文件记录（含路径、SHA-256）。
- `a3f2c1d9`：该文件内容的 SHA-256 前 8 位，即版本坐标；引文必须出自这个版本的内容。
- `L14-L17`：行号区间（自抽取文本第 1 行起算）；PDF 先经 pdftotext 转文本，行号即转换文本行号，报告中同时保留页码线索。
- 引文必须是从文件内容中**逐字截取**的片段（空白归一化后完全一致），禁止转述、禁止凭记忆改写。转述只能作为无引文的概述句，且必须单独标注 `"paraphrase": true` 并给出 confidence。

## 核验不通过时的处置（硬性规则）

`kb_verify.py` 的输出 `citation_verification.json` 中，凡 `pass=false` 的引用：

1. 若 `reason=quote_not_found` 但给出 `best_match`（difflib 相似度 ≥0.85）：按 best_match 的真实坐标与原文改写引文，重新核验。
2. 若相似度不足：该论断删除或改写为"本工作未能从库内原文证实"，并写入 `uncertainty`。
3. 若 `reason=file_unreadable` / `extraction_unavailable`：不得引用该文件；把该文件写入 `skipped_files`，说明缺什么工具或权限。
4. 最终 `result.json` 中不允许残留任何 `pass=false` 的引用；核验摘要在 `citation_verification.json` 中如实保留。

## output_contract 与检查点纪律

- 第 2 步先把 `result.json` 骨架落盘（`status="partial"`），随后每完成一项更新一次；最终 `status` 只取 `"completed"`（全部问题完成且引用全过）或 `"partial"`（说明哪些项未完成、为什么）。
- `result.json` 必须逐字段对齐 `case.json.output_contract`；contract 未要求的额外字段可以放在 `artifacts/` 下，不混入主结果。
- 每题答案结构：`{question_id, answer, claims:[{claim, evidence:[...], verification:"passed"|"revised"|"unsupported"}]}`。无法回答的问题，`answer` 明确写"库中无依据"，`uncertainty` 写明缺什么（缺哪类文件、哪个版本或哪类字段），不得留空、不得编造。

## 预算与异常处理

执行预算约 64 次模型请求、900 秒。索引与核验是确定性脚本，不占模型预算；模型预算只花在读题、检索后选段、作答与修订上。预算过半时立即收尾：核验通过的部分照常交付，未完成的问题标 `partial` 并注明原因。

异常情况处置：文件不可读→记 `skipped_files` 并继续；PDF 无文本层→记录 `extraction_unavailable`（可注明可用 OCR 工具补救）；目录为空→`status="partial"` 并在 `uncertainty` 说明；同一内容多版本→引用时注明所引版本哈希，不同版本内容不一致时在答案中并列说明；输入与 case.json 标注冲突→以实际文件内容为准并记录到 `change_log`。

## 自查清单

1. `result.json` 含 `case_id` 与 output_contract 全部字段？
2. 每个论断都有逐字引文与坐标？核验报告全为 `pass=true`？
3. 无依据的问题是否明确说"没有"并写明缺什么？
4. `sources`（引用清单）、`uncertainty`、`change_log`、`skipped_files` 是否齐全且与 artifacts 一致？
5. 换一个人只凭 `result.json` + `artifacts/` 能否回到原文逐条核对？（抽样 2 条手工复核）

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)（内容为虚构示意，非正式案例结果）。
