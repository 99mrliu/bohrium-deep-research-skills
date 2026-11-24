---
name: version-relation-graph
description: 科研资料库整理的"版本关系图谱"技能。当任务要求识别重复下载、区分预印本/正式版/补充材料/修订版并保留版本关系时使用；重心在关系语义：用六类独立信号（SHA-256、标题相似度、arXiv 号、DOI、正文版本自述、管理员说明）构建带类型与证据的有向关系图（duplicate_of/same_work/version_of/supplement_of），canonical 裁决按显式策略执行且每步留仲裁日志，证据不足时 canonical 诚实为 null。输入只读、不删除、同题异版全部保留。不负责单篇精读、全文翻译与文献检索发现。
---

# version-relation-graph：去重与版本是图问题，每条边都要有证据

## 1. 核心思想

"同名不同版本"和"同内容不同名"是资料库去重的两大陷阱。本 Skill 把重复与版本
识别做成**带证据的有向关系图**，而不是凭文件名拍脑袋：

1. **六类独立信号**（`graph_build.py` 机械提取，见
   `references/graph_semantics.md`）：SHA-256 相等、归一化标题 token 相似度、
   arXiv 号一致、DOI 一致、正文版本自述（"Published version of …"）、
   管理员说明中的文件互指。
2. **typed edges**：`duplicate_of`（字节级）、`same_work`（同一工作）、
   `version_of`（预印本↔正式版，带方向与角色）、`supplement_of`（补充材料）。
   每条边携带 `signals`（命中的信号列表）与 `evidence`（可回查的原文短引或哈希）。
3. **canonical 显式裁决**：簇内按策略打分（正式版 DOI+期刊 > 管理员指定 >
   其他），每一步写入 `arbitration_log.json`；证据不足时 `canonical: null`，
   绝不硬选一个。
4. **关系图谱可交付**：`version_graph.json`（机读 nodes/edges/clusters）与
   `graph.md`（人读邻接表 + 边证据表 + canonical 表）同源渲染；归档时同题异版
   **全部保留**，只在图谱与 `version_relations` 中登记关系。

## 2. 适用边界

- 适用：含重复下载、预印本/正式版并存、补充材料、修订版的资料库去重与版本
  梳理任务。
- 不适用：无文本层扫描件/损坏/无权限文件的内容级关系判定（它们只能凭哈希与
  文件名参与图谱，能力边界如实标注）；OCR；语义级"同一工作"的深度判读超出
  信号范围时标 `same_work_candidate` 交模型确认。

## 3. 运行时契约（Harbor）

- 安装路径 `/skills/weekly-skill`；脚本 `python3 /skills/weekly-skill/scripts/xxx.py`。
- 输入 `/input/case.json`、`/input/task.md` 与材料目录；防御式解析见
  `references/case_contract.md`。
- 工作目录 `/app/work`；交付 `/app/output/`：`result.json`（含原 `case_id` 与
  `output_contract` 全部字段、诚实 status）、`library/`、`version_graph.json`、
  `graph.md`、`arbitration_log.json`、`operations.jsonl`。
- status：`complete` / `partial`（有跳过或存疑 canonical，列限度）/ `blocked`。
- 依赖：Python 3 标准库；`pdftotext` 缺失时降级登记。
- 预算：脚本零模型请求；模型 0–2 次（确认候选边/回答检索问题）。第一步永远是 init。

## 4. 工作流程

设 `S=/skills/weekly-skill/scripts`。

### 第 1 步：盘点 + 图谱构建（脚本，0 次模型请求）

```bash
python3 $S/run_case.py init  --input /input --work /app/work --out /app/output
python3 $S/run_case.py graph --work /app/work --out /app/output
```

`graph` 产出 `/app/work/version_graph.json`（nodes/edges/clusters/canonical）、
`arbitration_log.json` 与保底 partial result.json。`same_work_candidate` 边
（只有弱信号）单列待模型确认。

### 第 2 步：模型裁决确认（0–1 次模型请求）

模型读 graph 与仲裁日志，写 `/app/work/adjudication.json`（可空）：

```json
{"confirm": [{"edge": ["F004", "F002"], "type": "version_of", "note": "……"}],
 "reject": [{"edge": ["F00x", "F00y"], "reason": "标题相似但实属不同工作"}],
 "canonical_overrides": [{"cluster": "C1", "canonical": "F002", "reason": "……"}],
 "answers": [{"qid": "Q1", "answer": "……", "evidence": "……"}]}
```

### 第 3 步：归档 + 图谱渲染 + 交付（脚本，0 次模型请求）

```bash
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

合并裁决 → 归档（duplicate_of 仅一份 `keep` 其余 `_archive_dups/`；同题异版全部
keep；冲突加序号不覆盖；幂等）→ 渲染 `version_graph.json` 终版与 `graph.md` →
终版 `result.json`（`version_relations` 由图谱簇直接导出）。

## 5. 异常处理

| 情况 | 处置 |
|---|---|
| 只有弱信号的相似标题 | `same_work_candidate` 边，canonical 不参与，交模型确认 |
| 簇内无 DOI/期刊/管理员指示 | `canonical: null` + uncertainties 注明 |
| 模型 reject 某条边 | 边删除并留痕（`rejected_edges`），簇重算 |
| 扫描件/损坏/无权限 | 仅以哈希/文件名节点入图，标注 `content_unavailable`，进 skipped |
| 同名不同内容目标 | `-n` 后缀，不覆盖 |

## 6. 最小调用示例（合成示例）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```

图谱应自动发现：两个字节级 duplicate 簇、一个"预印本+正式版+SI"三节点 version
簇（canonical=正式版）、学位论文单节点簇。输出摘录见 `sample_output.md`。
**合成示例，非正式案例结果。**

## 7. 自查清单

- [ ] 每条边的 evidence 可回查（哈希、标题、正文短引或管理员说明行号）。
- [ ] 每个簇的 canonical 裁决在 arbitration_log.json 中有完整打分轨迹。
- [ ] `canonical: null` 的簇已写入 uncertainties。
- [ ] result.json 的 version_relations 与 version_graph.json 簇一一对应。
