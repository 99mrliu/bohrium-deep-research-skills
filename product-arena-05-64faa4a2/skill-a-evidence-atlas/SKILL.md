---
name: evidence-atlas
description: 上游材料清点与事实溯源。当需要依据 /input 中的科研材料写作或改写"方法与实验"章节、且要求事实与来源严格一致时触发：先用确定性脚本把全部材料建成参数台账（每个参数带 file:line 坐标），模型只能基于台账写作，写完后用校验脚本核对正文每个数值都能在台账定位。
---

# evidence-atlas：材料清点与事实溯源（写得准）

## 1. 用途与适用条件

本 Skill 面向"方法与实验章节"写作/改写任务。核心流程：不直接通读材料写作，
而是先用纯标准库脚本把 /input 的全部材料建成两份台账产物——
`atlas.json`（机器读：文件清单 + 参数候选 + 冲突清单 + 未解析清单）与
`atlas.md`（人读摘要）——模型随后**只基于台账与台账指向的原文行**写作，
正文中的每个数值都标注台账 ID（形如 `[[P003]]`）；完稿后用校验脚本
`ledger_check.py` 逐一核对正文数值是否都能在台账定位，未定位者必须删除或
标注 `[待确认]`。

适用条件：

- 输入材料以文本类文件为主（yaml/json/ini/toml/log/txt/md/csv、代码、脚本）；
- 任务要求事实与来源一致、需要来源定位与修改记录；
- 模型预算紧张（本流程把"读材料"的工作转移给确定性脚本，模型只读台账）。

不适用或需降格使用的情形见第 7 节（限制与边界）。

## 2. 运行时契约（必须遵守）

1. **读实际内容，不凭标签猜内容**：必须打开并阅读 `/input/case.json` 与
   `/input/task.md` 的真实内容，据其确定任务要求与输出契约；不得依据文件名、
   目录名或任何标签臆测材料内容。
2. **目录约定**：中间工作文件放 `/app/work`；最终产物放 `/app/output`。
   台账建议放 `/app/work/atlas/`。
3. **result.json 契约**：`/app/output/result.json` 必须包含 `case_id` 和
   `case.json` 中 `output_contract` 声明的**全部字段**——字段名从 case.json
   如实读取，逐个填充；**不要猜字段名，不要新增契约外字段冒充契约字段**。
4. **诚实状态**：材料缺失、无法判断、运行失败须分别说明；partial 结果必须
   标明局限与缺口；**不得编造软件状态、实验结果或任何科学数据**。正文中
   无法在台账定位的数值，要么删除，要么标注 `[待确认]` 并列入人工确认项。
5. **尽早保存**：先把诚实的部分产物（哪怕只完成材料清单与台账）写入
   `/app/output`，再逐步改进；任何一步失败时，已保存的部分产物与失败说明
   必须留在结果中。
6. **溯源与记录**：产物须包含来源定位（file:line 级）、修改记录
   （相对原稿改了什么、依据哪条台账）、不确定性说明、人工确认项清单。
7. **六类要素**：章节须覆盖——方法步骤、实验设置、参数与来源、数据集与划分、
   对照实验、可复现性与限制条件。材料中缺失的要素如实写"材料未提供"，
   不得编造补齐。

## 3. 调用步骤（编号流水线）

以下命令中的 `/input`、`/app/work`、`/app/output` 按运行时实际路径使用；
所有脚本仅依赖 Python 3 标准库，无网络访问，同输入必得同输出。

**脚本路径**：本 Skill 安装后位于 `/skills/weekly-skill`，下文命令中的
`scripts/atlas_scan.py`、`scripts/ledger_check.py` 均指
`/skills/weekly-skill/scripts/` 下的文件；运行前可用
`ls /skills/weekly-skill/scripts/` 确认，或以绝对路径调用，例如：

```bash
python3 /skills/weekly-skill/scripts/atlas_scan.py --input /input --out /app/work/atlas
```

### ① 扫描材料，建台账

```bash
mkdir -p /app/work/atlas /app/output
python3 scripts/atlas_scan.py --input /input --out /app/work/atlas
```

产物：`/app/work/atlas/atlas.json` 与 `/app/work/atlas/atlas.md`。
先读 `atlas.md` 建立全局认识（哪些文件、哪些参数、哪些冲突、哪些未解析），
再按需查 `atlas.json` 的精确坐标。台账中每条参数形如：

```json
{"id": "P003", "name": "learning_rate", "value": "0.0003", "unit": "",
 "kind": "parameter", "source": {"file": "config.yaml", "line": 5},
 "evidence": "learning_rate: 0.0003"}
```

若 `conflicts` 非空（同名参数多处取值不一致），**不得擅自二选一**：
正文中只能写"材料间存在冲突（config.yaml:5 与 train.log:3），
以 XX 为准的理由是 …"并将裁决列入人工确认项；无法裁决时写"待确认"。

**台账阅读要点**：

- `kind` 含义：`parameter`（键值参数）、`flag`（命令行参数）、
  `version`（软件/环境版本）、`url`、`path`（来源线索类，一般不直接
  写入正文数值）。
- `evidence` 是该参数被提取时的原文行；写作引用某条参数前，若其
  `evidence` 看起来不像配置语境（例如散文中误提的片段），应回到
  `source` 指向的原文行确认其确为有效设置。
- `unparsed` 列出的文件（PDF、权重、图片等）脚本未读；若 task.md 表明
  关键事实在其中（如 PDF 论文中的实验细节），须列入人工确认项，
  不得假装已覆盖。
- `meta.notes` 记录了解析降级（无 PyYAML、JSON 语法错误、大文件截断），
  出现降级时对相应文件的关键数值应人工抽查原文。

### ② 基于台账写作，正文数值标注台账 ID

- 通读 case.json 与 task.md 的实际要求；按六要素组织章节。
- 正文中的**每一个数值**（参数值、版本号、划分比例、指标、seed 等）
  必须来自台账，并在首次出现处标注台账 ID，如
  "初始学习率 0.0003 [[P003]]"。同时建议在文末附"来源定位表"，
  把关键数值映射到 `file:line`。
- 需要台账未覆盖的细节时，可回到 `evidence` 指向的原文行核对；
  原文也没有的，写"材料未提供"或标注 `[待确认]`，**严禁凭常识补数值**
  （如"均为默认设置""标准划分"之类无来源断言一律禁止）。
- 写完即保存一版到 `/app/output`（尽早保存原则），再迭代。

**正文标注规范**：

- 台账 ID 标注格式为 `[[P003]]`，写在数值首次出现处；同一数值后文
  重复出现可不重复标注。
- 文末附"来源定位表"，至少覆盖关键参数，格式建议：

  ```text
  | 数值 | 含义 | 台账 ID | 来源 |
  | --- | --- | --- | --- |
  | 0.0003 | 初始学习率 | P003 | config.yaml:5 |
  ```

- 修改记录建议按"位置 — 原表述 — 新表述 — 依据（台账 ID / file:line）"
  逐条列出；改写任务中相对原稿删除的无来源断言也要记录。
- ledger_check 会排除 `[[P003]]` 与 `file:line` 形式的标注本身，
  不会因标注产生误报。

### ③ 校验正文数值可溯源

```bash
python3 scripts/ledger_check.py /app/output/methods.md /app/work/atlas/atlas.json \
    --out /app/work/check
```

- 退出码 0：全部数值 BOUND（已在台账定位）。
- 退出码 1：存在 UNSOURCED。逐条处理：回到材料中找到来源则改写并保留；
  找不到来源则**删除该数值或标注 `[待确认]`**，并在人工确认项中登记。
  处理后重跑本步，直到退出码 0 或剩余 UNSOURCED 均为有意保留的
  `[待确认]` 项（此时在 result.json 中如实说明校验未全部通过及原因）。
- 报告含 BOUND/UNSOURCED 清单（含行号）与覆盖率，写入修改记录。

### ④ 按契约装配 /app/output/result.json

1. 从 `/input/case.json` 读取 `case_id` 与 `output_contract` 声明的字段名；
2. 逐个字段如实填充（章节正文、来源定位、修改记录、不确定性、
   人工确认项、状态等按契约要求组织）；
3. 状态字段诚实填写：complete / partial（注明局限）/ failed（注明失败点）；
4. 确认 `/app/output` 中章节文件、result.json 均已落盘且编码为 UTF-8。

装配骨架（字段名仅为示意，实际以 case.json 的 output_contract 为准）：

```json
{
  "case_id": "<从 case.json 原样复制>",
  "status": "complete | partial | failed",
  "chapter_path": "/app/output/methods.md",
  "source_map": [{"value": "0.0003", "ledger_id": "P003",
                  "source": "config.yaml:5"}],
  "change_log": [{"where": "…", "before": "…", "after": "…",
                  "basis": "P003 / config.yaml:5"}],
  "uncertainties": ["…"],
  "human_check_items": ["learning_rate 冲突：config.yaml:5 与 train.log:3"],
  "limitations": ["train.log 中 … 未覆盖"]
}
```

装配完成后自检：output_contract 的每个字段名都能在 result.json 中
找到且取值非空（或按契约允许的空值），多一个字段、少一个字段都算失败。

## 4. result.json 契约说明

- `case_id`：从 case.json 原样复制。
- `output_contract` 的字段名与结构**以 case.json 中的实际声明为准**；
  本 Skill 不预设字段名。装配前先打印/阅读该声明，逐字段核对填充，
  不缺字段、不造字段。
- 无论契约如何声明，产物集合应能回答：写了什么（章节）、依据什么
  （file:line 来源定位与台账 ID）、改了什么（修改记录）、哪里没把握
  （不确定性与 `[待确认]`）、哪些要人看（人工确认项）、做到了什么程度
  （诚实状态）。

## 5. 异常处理

| 情形 | 处置 |
| --- | --- |
| 材料缺失（task.md 引用的文件不存在） | 在 result.json 中标记"材料缺失：文件名"，相关章节要素写"材料未提供"，列入人工确认项；不得编造。 |
| 配置冲突（台账 conflicts 非空） | 正文如实描述冲突及其 file:line，写明采用某一取值的理由或标 `[待确认]`，列入人工确认项。 |
| 权限不足（/input 不可读、/app 不可写） | 记录失败点与报错；尝试将产物写到可写目录并在 result.json 中说明实际路径；状态标 failed/partial。 |
| 解析失败（二进制、非 UTF-8、JSON/YAML 语法错误） | atlas_scan 已将该文件列入 `unparsed` 并注明原因；PDF 等二进制需人工阅读时，在人工确认项中说明"未经脚本解析"；JSON/YAML 语法错误自动降级为行解析并在 notes 注明。 |
| 无 PyYAML | atlas_scan 自动降级为行解析并在 notes 注明降级，嵌套 YAML 键可能丢失，需人工补查。 |
| ledger_check 退出码 2（文件缺失/台账损坏） | 检查路径后重跑；仍失败则按运行失败如实记录。 |
| 预算不足 | 优先保证：台账已建、章节覆盖六要素的诚实骨架（缺失要素写明"材料未提供"）、result.json 字段齐全，再润色文字。 |

## 6. 最小示例

`examples/` 提供一组**合成示例（非正式案例结果）**，可一键复跑：

```bash
bash examples/run_example.sh
```

它扫描 `examples/case/`（含 config.yaml、与配置故意冲突的 train.log、
含一个编造数值的 draft.md），在 `examples/expected/` 生成真实产物：
台账中可看到 `learning_rate` 冲突条目；`ledger_report.md` 中编造的
dropout 值被判为 UNSOURCED，其余数值均 BOUND。详见 `examples/README.md`。

## 7. 限制与边界

- 台账是**候选**清单：行解析可能漏提（非常规格式、表格内数值、嵌套
  YAML 在无 PyYAML 时）或误提（散文中形似键值的片段）。关键数值存疑时
  必须回看 `source` 指向的原文行确认。
- 二进制材料（PDF、模型权重、图片）一律不解析，只登记哈希与状态；
  其中的实验事实需人工或专门工具读取，本 Skill 不声称覆盖。
- ledger_check 只校验"数值可溯源"，不校验语义正确性（数值与参数的
  对应关系、单位换算、要素完整性仍需模型与清单把关，
  见 `references/checklist.md`）。
- 数值比对按字符串与浮点等价进行；"0.8"与"80%"互认为等价，
  但"0.0003"与"3e-4"仅在浮点相等时互认；不同精度写法（0.1 与 0.10）
  视为等价。
- 冲突检测按规范化参数名分组，写法不同但语义相同的参数
  （如 `lr` 与 `learning_rate`）不会自动归并，需在写作时人工归并。
- 提取规则与降级行为的完整说明见 `references/extraction_rules.md`。
