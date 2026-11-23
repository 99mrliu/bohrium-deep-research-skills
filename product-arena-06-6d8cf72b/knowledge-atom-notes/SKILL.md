---
name: knowledge-atom-notes
description: Turn a paper into a governed knowledge base — typed knowledge atoms (concept/method/finding/limitation/variable) with terminology normalization, acronym expansion, duplicate and conflict detection, paragraph-level anchors and a greppable index — so notes from many papers stay searchable, comparable and contradiction-free. Use for structured literature notes, knowledge-point extraction and reusable paper cards.
---

# Knowledge-Atom Notes

重心在中段知识工程：笔记不是“写短一点”，而是拆成类型化知识点（atom），统一术语、归并同义、查出重复与矛盾，最后生成可检索索引。下游（问答、综述、写作）直接消费 atoms 与 index，而不是重新读摘要。

## 运行契约

- 输入：`/input/case.json`（`case_id` + `output_contract`）、`/input/task.md`、真实论文材料。工作区 `/app/work`，交付区 `/app/output`。
- 最终交付 `/app/output/result.json`：含 `case_id` 与 output_contract 全部必需字段；同时交付 `atoms.json`、`index.jsonl`、`terms.md`、`kb-lint.json`。
- 诚实状态：`success` 仅当合同校验与 lint 均通过；任何硬违例 → `partial` 并在 `limits` 命名；文本不可得 → `failed` + 接管指引。预算 64 请求 / 900 秒，前两步内先落盘骨架 result.json，再增量充实。

## 流程（K 为本 SKILL.md 所在目录）

### 1. 章节化

```sh
python3 "$K/scripts/sectionize.py" --pdf /input/<paper>.pdf --case-id "$CASE_ID" --out /app/work/sec
# 扫描件/加密件：用平台 OCR/文本工具导出后 --text-file
```

得到 `sections.json`：章节标题 + 段落锚点 `s{章节}¶{段落}`（从 1 起）。先看章节清单是否覆盖论文主干；缺章、标题误检时以实际文本为准并记入 limits。

### 2. 撰写 atoms.json（Agent 的核心工作）

按 [references/atom-schema.md](references/atom-schema.md) 逐条撰写知识点：

- 五类：`concept`（概念：term+definition）、`method`（方法：term+purpose）、`finding`（发现：claim+条件）、`limitation`（局限：claim+scope）、`variable`（变量：symbol+meaning+unit/value）。
- 每条必须带 `evidence: [{anchor, quote}]`，quote 为该段逐字片段；`not_reported` 可豁免证据但要写明查过的范围。
- `aliases` 收录同义表述与缩写对（如 "CBS" ↔ "Counting Bloom Sketch"）；归一化规则见 [references/terminology-rules.md](references/terminology-rules.md)。
- `contract_fields`：与 case output_contract 对应的最终交付字段（笔记/卡片/清单等），引用 atom id 或直接作答。

### 3. 术语治理与校验

```sh
python3 "$K/scripts/kb_lint.py" --atoms /app/work/atoms.json \
  --sections /app/work/sec/sections.json --out /app/work/kb-lint.json
```

硬违例（缺字段、锚点不可解析、引文不逐字、无证据未声明）必须修复；重复/冲突候选是警告——是否归并由你判断，归并动作写进 atoms.json 的 `merges` 字段留痕。

### 4. 生成索引并交付

```sh
python3 "$K/scripts/kb_index.py" --atoms /app/work/atoms.json --out /app/output
python3 "$K/scripts/assemble_result.py" --case /input/case.json \
  --atoms /app/work/atoms.json --lint /app/work/kb-lint.json --out /app/output
cp /app/work/atoms.json /app/work/kb-lint.json /app/output/
```

`index.jsonl`（每行一条，可 grep 可 diff）与 `terms.md`（人读术语表）是派生视图，atoms.json 是唯一事实源。

## 异常处理

- 提取失败：sections.json 返回 `unreadable` 与接管指引；不要凭记忆补论文内容。
- 跨栏/表格段落破碎：段落锚点以文本层为准，表格数值回渲染页核对后标注 uncertainty。
- 术语冲突：同一归一化词形的不同定义不会自动合并，lint 只给候选；禁止为消冲突而改写原文含义。

## 最小示例（合成）

```sh
sh "$K/examples/synthetic-case/run_example.sh /tmp/kan-demo"
```

`examples/synthetic-case/` 内为虚构论文与演示填写器，输出标注为合成示例，非正式案例结果。

## 依赖

Python 3.9+ 标准库；PDF 经 `pdftotext` 或平台文本工具导出。不联网、不装包。
