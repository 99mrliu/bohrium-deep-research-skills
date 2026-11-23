# examples/ — 合成最小示例（SYNTH-EXAMPLE-001）

> **声明**：本目录全部内容为**合成示例**，文档、工单、单元格均为虚构，
> 不构成也不来自任何官方正式案例的结果。示例仅用于演示
> corpus-forensics-registry Skill 的取证流水线如何运行。

## 语料设计（corpus/，均为虚构论文，markdown，空行分段）

| 文档 | 内容 | 演示点 |
|---|---|---|
| DOC-A | g-C3N4 可见光降解 RhB，96%/90 min，k=0.035 min^-1 | 规范（canonical）文档 |
| DOC-B | N-TiO2 可见光降解亚甲基蓝，88%/120 min，k=0.017 min^-1 | 不同材料/污染物 → 六维可比性检验中的不可比维度 |
| DOC-C | DOC-A 的"修订版"：同标题、多数段落相同、动力学数值改动、新增一段 | 多版本检测 → `probable_version_pair`，被机检 R2 拦截 |
| DOC-D | LSM-tree 存储基准（无关主题） | 相关性门控 → `out_of_scope`，被机检 R4 拦截 |

## 运行

```bash
cd examples
bash run_example.sh
```

仅需 python3（标准库）。语料均为 markdown，因此不依赖 pdftotext；
若语料含 PDF 而系统无 pdftotext，对应文档会被标记 `tool_missing`。

## 预期输出（examples/output/）

- `registry.json`：4 篇文档；DOC-A/B/D 为 `unique`，DOC-C 为
  `probable_version_pair`（related_to=DOC-A，shingle Jaccard ≈ 0.61，标题相似度 1.0）。
- `<DOCID>.paragraphs.jsonl`：每段 `paragraph_id` + `content_hash` + 原文。
- `parse-audit.json`：独立保真审计，4 篇均为 `good`。
- `relevance.json`：DOC-A/B/C `in_scope`，DOC-D `out_of_scope`（score=0）。
- `verify-report.txt`：16/16 cells passed，退出码 0。
- `comparison-matrix.md`：字段 × 论文矩阵，单元格带 value 与 `paragraph_id#content_hash` 锚点及出处 quote 清单。

## 如何触发机检失败（不要在 sample_cells.jsonl 上改，复制一份再改）

```bash
cp sample_cells.jsonl /tmp/cells_bad.jsonl
# 用编辑器把任一 quote 改一个词，或把 content_hash 改成别的值，或：
#   - 把某格 source_document_id 改成 DOC-C（非规范版本，触发 R2）
#   - 把某格 source_document_id 改成 DOC-D（主题无关，触发 R4）
#   - 给 status=not_reported 的格子加 value（触发 R9）
#   - 把 reported 格 value 改成 quote 中不存在的数字（触发 R8）
python3 ../scripts/verify_anchors.py --registry output \
    --cells /tmp/cells_bad.jsonl --relevance output/relevance.json
# 预期：非零退出，stdout 打印失败清单（规则编号 R2/R4/R6/R7/R8/R9 ...）
```

实测：上述每类篡改均被正确拦截（见 Skill bundle 交付报告）。
