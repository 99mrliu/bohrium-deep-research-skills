---
name: delivery-studio
description: Turn authored reading results into review-grade deliverables — a readable notes.md with anchored sections and comparison tables, a self-contained HTML preview (plus PNG strip when matplotlib is available), a greppable notes.jsonl reuse index, a sha256 manifest over all inputs and outputs, and a delivery inspection that catches missing, empty, unparseable or drifted artifacts. Use at the end of any literature-summary or structured-notes task where the result must be inspectable and reusable.
---

# Delivery Studio

重心在下游渲染工程：内容读对了不等于交付合格。本 Skill 负责把已成稿的笔记/答案渲染成人读与机读全套工件，并用清单核验保证交付目录里没有缺失、空文件、坏 JSON 或被后续步骤意外改动的文件。

## 运行契约

- 输入：`/input/case.json`（`case_id` + `output_contract`）、`/input/task.md`、真实论文材料；内容本身由 Agent 阅读后撰写（本 Skill 提供 notes.json 结构约定，不替你做语义判断）。
- 工作区 `/app/work`；交付区 `/app/output`。最终交付：`result.json`（含 `case_id` 与全部合同字段）、`notes.md`、`preview.html`、（可得时）`preview.png`、`notes.jsonl`、`manifest.json`、`change_records.md`、`delivery-report.json`。
- 诚实状态：result.json 的 status 按实际内容填写（success/partial/failed + 理由）；渲染工具缺失时如实降级（HTML 一定产出，PNG 缺依赖时报告 unavailable，不假装渲染成功）。预算 64 请求 / 900 秒。

## 流程（K 为本 SKILL.md 所在目录）

### 1. 撰写 notes.json（Agent 的内容工作）

按 [references/notes-format.md](references/notes-format.md) 在 `/app/work/notes.json` 组织内容：论文卡片（每个字段可带锚点）、按原文章节序的 sections（body + anchors）、可选 comparison 对比表、open_questions、limits、change_records。锚点格式不限（`p2-l7`、章节名、图表号均可），但必须能在原文中定位；格式建议见 [references/artifact-contract.md](references/artifact-contract.md)。

### 2. 渲染人读工件

```sh
python3 "$K/scripts/render_notes.py" --notes /app/work/notes.json --out /app/output/notes.md
python3 "$K/scripts/render_preview.py" --md /app/output/notes.md --notes /app/work/notes.json \
  --out-html /app/output/preview.html --out-png /app/output/preview.png
```

notes.md：目录 + 卡片 + 章节（锚点内联为代码标记）+ 对比表 + 未决问题 + 边界。preview.html：自包含（内嵌 CSS、锚点高亮、打印友好），无需任何外部资源即可打开。PNG 是卡片与章节地图的一页视觉摘要，依赖 matplotlib；不可用时如实报告。

### 3. 复用包与清单

```sh
python3 "$K/scripts/reuse_pack.py" --notes /app/work/notes.json \
  --inputs /input/<paper>.pdf --artifacts /app/output/result.json /app/output/notes.md \
  --out /app/output
```

notes.jsonl 每行一条（卡片字段/章节笔记/未决问题），可直接 grep/diff/入库；manifest.json 记录所有输入与产物的 sha256——复用者可验证笔记对应的原文是哪一份字节、磁盘上的工件是否被改动过。

### 4. 写 result.json 并交付核验

result.json 除合同字段外，附 `artifacts` 清单（每个工件的路径与一句话说明）、`sources`、`uncertainty`、`change_records`。最后：

```sh
python3 "$K/scripts/check_delivery.py" --out /app/output --case /input/case.json
```

核验缺失/空文件/坏 JSON/manifest 漂移/result 状态未定稿；gaps 是修复清单，修不掉就写进 `limits` 再交付。渲染与预览的目检要点见 [references/artifact-contract.md](references/artifact-contract.md)。

## 异常处理

- matplotlib 不可用：PNG 报告 unavailable，HTML 预览不受影响，不视为失败。
- 合同禁止附加字段时：`artifacts` 等辅助信息放入 notes.md 而非 result.json。
- 内容缺口不是渲染能掩盖的：limits 必须随 result.json 一起交付。
- 交付后发现改动：重跑 reuse_pack.py 更新 manifest，并把改动记入 change_records。

## 最小示例（合成）

```sh
sh "$K/examples/synthetic-case/run_example.sh /tmp/dst-demo"
```

材料为虚构论文；示例输出标注为合成示例。

## 依赖

Python 3.9+ 标准库；PNG 条带为可选 matplotlib（缺失时诚实降级）。不联网。
