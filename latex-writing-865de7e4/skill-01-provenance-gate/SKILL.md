---
name: latex-source-provenance-gate
description: 面向 LaTeX 写作与改稿任务的"事实来源闸门"。当任务要求依据 /input 提供的科研材料（原稿、PDF 论文、数据文件、参考文献库、笔记）撰写、修订或校对 LaTeX 稿件时触发。核心能力是 provenance（来源可回溯）：脚本先做确定性的机械取证——matscan.py 清点材料并把每个数字+单位、百分比、样本量、术语、引用键、图表标题抽取为带"文件:行号"锚点的事实条目；texaudit.py 扫描稿件，把正文中每一处事实性内容与事实库比对，逐条给出 matched（附材料 file:line）/ unmatched（附最接近候选条目作复核线索，显式标注弱匹配）/ conflict（材料之间口径不一致）；Agent 阅读审计报告后亲自做语义判断与修改——脚本只报告、绝不自动改稿；finalize.py 最后装配 /app/output：稿件拷贝、source_map.md、coverage 报告、change_log.md、result.json（含 case_id 原样复制与 output_contract 逐字段镜像，四方言归一化，缺材料给诚实 null）。红线：任何材料外的事实不得默默写入稿件，必须显式标注来源缺口或冲突；脚本不做自动改写、不做低置信度重指向。不适用于无外部材料依据的纯创作任务、纯格式排版任务（无事实性内容核对需求），以及材料全部为无法提取文本的扫描件且无降级余地的场景。
---

# LaTeX 事实来源闸门（latex-source-provenance-gate）

一句话定位：在 LaTeX 写作/改稿任务中，确保稿件里每个数字、单位、术语、引用键都能回溯到材料的 `文件:行号`，材料外事实与材料间冲突一律显式标注，绝不默默写入。

## 环境与预算

- 平台输入：`/input/case.json`（含 case_id 与 output_contract）、`/input/task.md`、case.json 指向的材料；case.json 缺失时遍历 /input 并如实降级。
- 工作目录 `/app/work`；最终交付 `/app/output`。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens。**尽早交付一版 result.json，再增量改进**。

建议时刻表：

| 阶段 | 内容 | 预算占比 |
| --- | --- | --- |
| 1 | matscan 取证 + 读 materials_index.md 与 task.md | 前 15% |
| 2 | texaudit 审计初稿 + 读 coverage 报告 | 15%–30% |
| 3 | Agent 语义判断与修改（主体工作） | 30%–70% |
| 4 | 对改后稿复检 + finalize 装配（含 result.json 首版） | 70%–85% |
| 5 | 目检 result.json、补 change_log/source_map、增量改进 | 85%–100% |

## 运行流程

以下命令可直接复制，`SKILL_DIR` 为本 Skill 的安装目录（平台为 `/skills/weekly-skill`）。

```bash
# 0. 可选增强：pdftotext 在 PATH 中即可用于 PDF 材料；缺失时 matscan 自动降级并记录 gaps
# 1. 材料取证：清点材料、抽取带锚点的事实条目
python3 "$SKILL_DIR/scripts/matscan.py" --input /input --work /app/work
# 2. 审计稿件（--draft 换成实际稿件路径）
python3 "$SKILL_DIR/scripts/texaudit.py" --draft /input/main.tex --work /app/work
# 3. Agent 阅读 /app/work/audit/coverage.md，按下方判断规则改稿（改好的稿放入 /app/output）
# 4. 对改后稿复检，确认问题已处置
python3 "$SKILL_DIR/scripts/texaudit.py" --draft /app/output/main.tex --work /app/work
# 5. 装配交付（缺少 --case/--task 时 finalize 如实降级，result.json 仍落盘）
python3 "$SKILL_DIR/scripts/finalize.py" --case /input/case.json --task /input/task.md --work /app/work --output /app/output
```

## Agent 判断规则（脚本不替你做的部分）

1. **先读 task.md 与 coverage.md，再动笔。** coverage 报告里每条稿件事实已分类：
   - `matched`：材料中有完全一致（或单位换算后等价）的条目，报告给出材料 `file:line`，可直接采信。
   - `unmatched`：材料中找不到。脚本会附最接近的候选条目作复核线索，并显式标注"弱匹配"。Agent 必须逐条判断：是保留并在文中/change_log 显式标注"材料外事实"，还是删改。弱匹配不等于 matched，禁止当作已证实。
   - `conflict`：同一事实在材料间口径不一致。按 references/conflict-policy.md 处置：以 task.md 指定口径或更高优先级材料为准，并在文中或注释里显式说明存在另一口径。
2. **引用键**：`\cite` 的键必须存在于材料提供的 .bib；未知键按 unmatched 处理，禁止脚本式批量重指向，改键须 Agent 人工确认语义对应。
3. **修改留痕**：每处事实性修改写入 /app/output/change_log.md（finalize 保留该文件；没有则生成待填模板）。
4. **source_map.md 是 Agent 写的**：finalize 只生成骨架，事实↔来源对应关系由 Agent 根据 coverage 与改动逐条补全。
5. **诚实优先**：契约字段缺材料时在 result.json 给 null 并在 uncertainty 说明；不得编造数值填充。

## 脚本产出说明

| 脚本 | 产出 | 说明 |
| --- | --- | --- |
| matscan.py | `/app/work/facts/facts.jsonl`、`/app/work/facts/materials_index.md`、`extraction_report.json` | 材料清单（含 gaps）、事实条目（type/value/unit/锚点/来源行文本）、降级记录 |
| texaudit.py | `/app/work/audit/coverage.json`、`coverage.md` | 稿件事实逐条分类 matched/unmatched/conflict，只报告不改稿 |
| finalize.py | `/app/output/` 下的 result.json、source_map.md、coverage 拷贝、change_log.md、draft 拷贝 | result.json 镜像 output_contract 全字段（四方言归一化），artifacts 只列真实存在文件 |

output_contract 四方言归一化规则（finalize 内置）：`{字段: {type, required}}` 取字段名；自然语言描述逐行解析编号/破折号列表；JSON Schema 取 properties 键；字段名列表直接用。缺材料字段给 null，绝不把 `{type, required}` 元数据当值输出。

## 异常处置（识别 → 降级 → 记录）

- **case.json 缺失/不可解析**：finalize 记 `case_id: null`、status 置 `partial`，matscan 直接遍历 /input，结果照常落盘。
- **材料路径缺失**：matscan 记入 materials_index.md 的 gaps 段与 extraction_report.json，不中断。
- **pdftotext 缺失**：PDF 材料记入 gaps（"无法提取文本"），其余材料照常处理。
- **无 .bib / 稿件无事实性内容**：coverage 相应分类为空列表，属正常结果而非失败。
- **任何阶段出错**：先尽力落盘已有产物与 result.json（partial/failed），再改进。

## 红线

1. 脚本只报告与装配，**绝不自动改写稿件**；所有事实性改动由 Agent 决定并执行。
2. 材料外事实不得默默写入；冲突不得悄悄取一边，必须显式标注。
3. result.json 的契约字段缺材料时给诚实 null + uncertainty 说明，禁止填充编造值。
4. 不预生成针对正式案例的答案；示例仅为自造合成示例。
