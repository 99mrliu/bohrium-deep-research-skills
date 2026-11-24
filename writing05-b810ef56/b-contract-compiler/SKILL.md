---
name: contract-first-deliverable-engineering
description: 文献证据驱动写作——下游交付契约工程。当任务以 /input/case.json 的 output_contract 定义交付物（成稿、证据表、引用核验结果等结构化产物），且评分要求 result.json 含 case_id 与全部契约键、诚实标注 partial 时使用。本 Skill 的重心在"交付的最后一公里"：写作前先把 case.json 编译成交付契约清单，写作后由确定性脚本组装并终验 result.json，从机制上消灭缺键、键名走样、case_id 不一致、引用悬空文件、空值冒充完成这五类高频失分。适用于一切以结构化 result.json 为终态的写作/改稿/证据表任务。
---

# 交付契约工程（Contract-First Deliverable Engineering）

## 这个 Skill 解决什么问题

基础 Agent 在这类任务上的失败常常不在写作质量，而在**交付合规**：result.json 缺 output_contract 声明的键、键名凭记忆拼错、case_id 抄写走样、status 写 complete 却有空值、result.json 里引用了不存在的文件。本 Skill 把契约处理从"最后凭印象填"改成"先编译、后组装、再终验"的确定性流水线：契约键集合来自脚本解析而非记忆，组装只认真实存在的部件文件，终验不过不许收工。

## 何时使用

- 任何以 `/app/output/result.json` 为终态、且 case.json 含 `output_contract` 的任务；
- 尤其适合多键交付（成稿 + 证据表 + 引用核验 + 双语版本等）或材料可能不全、需要诚实 partial 的情形。

不适用：无结构化输出契约的开放式任务（此时本 Skill 退化为通用键交付，仍可运行）。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、材料文件；先读实际文件内容。
- 工作区 `/app/work`；最终产物与 `result.json` 放 `/app/output`。
- `result.json` 含原样 `case_id` 与 `output_contract` 全部键；缺件键填 null 并入 `missing`，`status` 强制 `partial`，`limits` 逐项说明。
- 预算意识：契约解析与组装都在脚本内完成（不耗模型请求）；先交付一个全键的 partial，再随写作进展重跑组装升级。

## 依赖

- Python ≥3.9 标准库，无网络依赖。
- 脚本：`scripts/contract_inspect.py`（契约编译）、`scripts/assemble_result.py`（确定性组装）、`scripts/validate_output.py`（终验）。

## 工作流（严格按序执行）

**步骤 0 — 编译契约（脚本，写作前必做）**
```bash
mkdir -p /app/work/result_parts /app/output
python3 /skills/weekly-skill/scripts/contract_inspect.py /input/case.json /app/work/contract.json --task /input/task.md
```
读 `/app/work/contract.json`：`contract_keys` 就是本任务的交付清单（含 required 与期望形态），`case_id` 原样照抄。warnings 非空时按其提示处理（契约缺失 → 按 `references/contract_playbook.md` 第 3 节通用键交付）。

**步骤 1 — 读材料与写作（模型）**
按 task.md 阅读 `/input` 材料并写作。每完成一个契约键的内容，就把它写入部件文件：
- 契约键 `deliverable` → `/app/work/result_parts/deliverable.md`（JSON 类键用 `.json`）；
- 同步把可编辑终稿复制到 `/app/output/`（result.json 的值可以是内联文本，也可以是"见 /app/output/xxx.md"的引用，但引用的文件必须真实存在）；
- 材料不足无法完成的键：**不要造内容**，留空并在 `limits.md` 记一项。

**步骤 2 — 组装（脚本）**
```bash
printf 'partial' > /app/work/result_parts/status.txt   # 或 complete/failed
python3 /skills/weekly-skill/scripts/assemble_result.py /app/work/contract.json /app/work/result_parts /app/output/result.json
```
组装器只认部件文件：契约键没有部件 → null + `missing`；required 键缺失 → status 强制 `partial`。`uncertainty.md` / `change_log.md` / `limits.md` / `sources.json` 作为元信息并入。

**步骤 3 — 终验（脚本，不过不许收工）**
```bash
python3 /skills/weekly-skill/scripts/validate_output.py /app/output --case /input/case.json --report /app/output/validation_report.md
```
- 任一 FAIL：按 `references/contract_playbook.md` 第 4 节修复矩阵逐项修复后重跑步骤 2–3；
- 全 PASS 才允许结束。`validation_report.md` 留在 /app/output 供评审复核。

**步骤 4 — 增量升级**
预算允许时，继续补足 `missing` 中的键：写部件 → 重跑步骤 2–3。每次组装都是幂等的，覆盖式更新 result.json。

## 异常处理

见 `references/contract_playbook.md` 第 4 节修复矩阵。要点：case.json 缺 case_id → 组装器填 `"unknown"` 并在 limits 记录；契约键名含特殊字符 → 部件文件名原样使用键名（含点号时脚本按 `.json/.md/.txt` 后缀匹配）；写作中途时间不足 → 当前 result.json 已是合法 partial，可直接收工。

## 最小调用示例（合成示例，非正式案例结果）

`examples/` 下含合成 case.json（output_contract 声明 `deliverable` 与 `evidence_map` 两键）与部件目录（`evidence_map` 部件刻意缺失，用于演示诚实 partial）。执行：
```bash
python3 scripts/contract_inspect.py examples/input/case.json /tmp/cc-contract.json
python3 scripts/assemble_result.py /tmp/cc-contract.json examples/input/result_parts /tmp/cc-out/result.json
python3 scripts/validate_output.py /tmp/cc-out --case examples/input/case.json
```
结果：contract 编译出 2 个键；组装输出 status=partial、missing 含 evidence_map；终验全 PASS（partial + limits 非空即合规）。真实输出见 `examples/minimal_example.md` 与 `examples/output/`。

## 限制与维护

- 本 Skill 保证交付合规与诚实状态，不判断写作内容本身的质量——内容质量由上游证据流程与模型写作保证。
- required/形态推断是启发式（`contract_inspect.py` 的 classify_spec），拿不准的键按 required 处理并在 limits 说明口径。
- 维护：契约键候选名集中在 `contract_inspect.py` 的常量；终验规则集中在 `validate_output.py`；通用键兜底口径在 `references/contract_playbook.md` 第 3 节。
