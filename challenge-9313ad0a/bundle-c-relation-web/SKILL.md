---
name: relation-web
description: 为科研材料思维导图构建"类型化、证据受控"的横向关系网：仅在材料确有依据时，在因果、依赖、对比、时序、引用等十种关系类型下连边，并以逐字证据校验与形式化检查（无环、非冗余、无自环）保证"连得对"；适用于材料已结构化、需要在主题树之外标注跨分支关系的场景。
---

# relation-web：思维导图的类型化关系语义层

本技能面向科研材料思维导图构建中的"关系语义"环节：主题树（父子层级）只回答"属于"，横向关系边回答"为何相关、如何相关"。本技能规定一套十元关系词表、两套标准化数据文件（nodes 与 relations）、一道证据闸门（relation_gate.py）与一道数值冲突扫描器（conflict_scan.py），确保每一条横向边均有材料依据、方向正确、不构成时间环、不重复层级信息。

## 何时使用

适用场景：
- 输入材料（论文、报告、实验记录等）已可分页/分段定位，需要在其上构建思维导图；
- 导图除主题树外，还需表达跨分支关系，如"方法 A 支撑结论 B""数据 C 与数据 D 冲突""工作 E 引用了工作 F"；
- 交付物要求可审计：每条关系边可追溯至具体文件、页码与原文引句；
- 材料中存在数值冲突（同一指标在不同来源取值不同），需要识别并标注。

不适用场景：
- 材料未经结构化，无法获得稳定的"文件—页码"定位（此时应先行完成分页抽取）；
- 仅需单一主题树、无需跨分支关系的极简导图；
- 材料本身为图像或扫描件且无 OCR 文本层（引句逐字校验无从执行）；
- 材料对某一关系完全没有陈述，而任务又要求必须给出该关系——此时应如实报告 unable_to_determine，而非臆造连边。

## 固定运行方式

运行时契约（不可变更）：

1. 读取 `/input/case.json` 与 `/input/task.md`，取得 `case_id` 与 `output_contract` 所列全部字段；
2. 在 `/app/work` 下进行全部中间工作：抽取材料文本为 `pages.jsonl`（每行 `{"file","page","text"}`，可用 pdftotext 等工具生成），构建 `nodes.json` 与 `relations.json`；
3. 运行 `scripts/relation_gate.py` 对全部关系边执行校验；运行 `scripts/conflict_scan.py` 扫描数值冲突候选；
4. 尽早（首次获得任何可用结果时）将一份如实标注 `status: partial` 的 `result.json` 写入 `/app/output/result.json`，随后在同一文件内就地改进；
5. 最终 `/app/output/result.json` 必须包含原始 `case_id`、`output_contract` 指定的每一个字段、如实的 `status`（success / partial / unable_to_determine / refused）、sources/evidence、uncertainty 列表与变更记录（change records）。

铁律：材料不支持的关系一律不画。证据缺失时宁可删边或降级为 uncertainty 条目，也不得虚构引句。

标准化数据模式：

nodes 文件（`nodes.json`）：
```json
{"nodes": [{"id": "n1", "label": "……", "kind": "……", "parent": "n0 或 null"}]}
```
- `parent` 构成唯一主题树；`id` 全局唯一；`kind` 为节点类别（如 topic/method/result/dataset 等，由任务自定义）。

relations 文件（`relations.json`）：
```json
{"relations": [{"id": "r1", "from": "n2", "to": "n5", "type": "causes",
                "basis": "fact",
                "evidence": {"file": "paper.pdf", "page": 3, "quote": "……逐字原文……"},
                "note": "补充说明，可为空串"}]}
```
- `basis` 取 `"fact"` 或 `"inference"`；`basis=fact` 时 `evidence` 必须非空且引句在指定文件与页中逐字出现；`basis=inference` 时 `evidence` 可为 `null`，但 `note` 必须非空，说明推理依据。

关系类型词表（恰好 10 种）：`causes, depends_on, supports, contrasts_with, conflicts_with, cites, precedes, addresses, measures, mitigates`。词表的定义、方向性与证据模式详见 `references/relation-vocabulary.md`；证据闸门规则详见 `references/edge-evidence-rules.md`。

## 工作流程

1. **材料分页化**：将全部材料抽取为 `pages.jsonl`。PDF 用 `pdftotext -f N -l N` 逐页抽取；纯文本按逻辑页或段落编号。`file` 字段与 `page` 字段须在后续证据引用中原样使用。
2. **主题树构建**：产出 `nodes.json`。先定根与一级分支，再逐级展开；保证 `parent` 指针无环、无悬空。
3. **候选关系发掘**：通读材料，记录一切跨分支关系陈述；同时运行 `conflict_scan.py` 获得数值冲突候选清单。
4. **边构建与定基**：对每个候选，判定关系类型与方向（参照词表）；凡材料有明文陈述者定 `basis=fact` 并摘取逐字引句（含文件与页码）；凡需综合推断者定 `basis=inference` 并撰写非空 `note`。
5. **闸门校验**：运行 `relation_gate.py`。对 fabricated / mislocated / 时间环等错误必须修边或删边后复跑，直至闸门不再报告错误级发现；警告级发现（如非互逆的对比边）可保留但须写入 uncertainty 或 note。
6. **冲突处置**：对每个冲突候选，二选一：若材料本身呈现了两种取值且可定位，则建立 `conflicts_with` 边（basis=fact，双侧引句）；若无法判定，则在 `result.json` 的 uncertainty 列表中登记该键、两个取值及出处。
7. **交付**：按运行时契约写出 `result.json`；中间产物（nodes/relations/报告）置于 `/app/work` 或按 output_contract 要求一并输出。

## 输出物说明

- `/app/output/result.json`：唯一强制交付物。含原始 `case_id`、`output_contract` 全部字段、`status`、sources/evidence、uncertainty 列表、变更记录。
- `/app/work/nodes.json`、`/app/work/relations.json`：思维导图节点与关系边，遵循上述模式。
- `/app/work/gate_report.json`：闸门报告，结构为 `{"summary":{"relations":N,"accepted":a,"rejected":r,"warnings":w},"accepted":[ids],"findings":[{"relation_id","check","verdict","detail"}]}`。
- `/app/work/rejected.json`：被拒边清单，结构为 `{"rejected":[{"relation":…,"reasons":[…]}]}`。
- `/app/work/conflict_candidates.json`：数值冲突候选，结构为 `{"candidates":[{"key","unit","values":[{"value","where":{"kind":"node|material","ref":…}}],"suggestion":"conflicts_with|uncertainty"}]}`。

## 异常处理表

| 异常 | 闸门判定 | 处置 |
| --- | --- | --- |
| 无证据连边（basis=fact 但 evidence 缺失或引句为空） | 拒绝（rejected） | 补齐逐字证据后重提；补不齐则删边或改 basis=inference 并写明 note |
| 方向错误（如把"结果 supports 方法"误向） | 闸门不自动判向；由工作流程第 4 步人工判定 | 对照词表的方向性定义反转或删除该边 |
| 时间环（precedes 子图存在环） | 错误（error，退出码 1） | 核对各 precedes 边的时序依据，删除或反转造成环的边 |
| 层级重复连边（from 与 to 互为祖先/后代） | 拒绝（rejected） | 该内容属于主题树，删除横向边；必要时在树内调整层级 |
| 证据逐字校验失败 | 引句在指定页不存在但在同文件他页存在 → mislocated（拒绝并提示正确页）；全材料均无 → fabricated（拒绝，退出码 1） | mislocated：修正 file/page；fabricated：删除该边，不得保留 |
| 冲突数值对 | conflict_scan 报告候选；闸门不处理 | 按工作流程第 6 步：建 conflicts_with 边或登记 uncertainty |

## 最小合成示例说明（标注合成）

`examples/synthetic-input/` 与 `examples/synthetic-output/` 构成一个端到端最小示例。**全部内容均为合成（synthetic）**，研究对象"催化剂Q"及其全部数据系虚构，仅用于演示工具行为：

- `nodes.json`：10 个合成节点，parent 指针构成一棵小型主题树；
- `relations.json`：9 条关系边——5 条完全合法（含逐字证据）、1 条引句虚构、1 条层级冗余、1 条自环或重复、1 条 inference 缺 note；
- `pages.jsonl`：3–4 行合成材料文本，含全部所需逐字引句，并植入同一指标"产率"的两个冲突取值（第 1 页 87.5%，第 3 页 79.2%）；
- `synthetic-output/`：对上述输入真实运行两个脚本所得的 `gate_report.json`、`rejected.json`、`conflict_candidates.json`；冲突候选中可检出所植入的"产率"冲突。

复现命令（在 bundle 根目录下）：
```
python3 scripts/relation_gate.py --nodes examples/synthetic-input/nodes.json \
  --relations examples/synthetic-input/relations.json \
  --material examples/synthetic-input/pages.jsonl \
  --report gate_report.json --rejected rejected.json   # 退出码 1（含虚构证据）
python3 scripts/conflict_scan.py --nodes examples/synthetic-input/nodes.json \
  --material examples/synthetic-input/pages.jsonl \
  --out conflict_candidates.json                        # 退出码 0
```

## 限制

- 引句校验为逐字匹配（仅折叠空白、统一破折号/引号），无法识别同义改写；材料若经过重新排版导致字符变化，须重新摘句。
- 闸门不判断关系方向与类型选择的语义正确性，仅做形式与证据校验；语义判断依赖工作流程第 3–4 步。
- 冲突扫描基于正则启发式，可能漏检非数字型冲突（文字性结论冲突）并误报语境不同的同键数值；所有候选须经人工裁定。
- 节点标签参与冲突扫描，故标签撰写应避免引入与材料无关的数值。
- 仅使用 Python 3.10+ 标准库；无网络访问；材料体量受运行预算约束时应优先处理核心章节。
