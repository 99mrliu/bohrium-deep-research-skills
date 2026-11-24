---
name: contract-pilot
description: 面向思维导图类科研案例的运行契约合规技能：通过尽早写出诚实 partial、预算感知检查点与交付前最终对账，保证 result.json 的状态、契约字段、证据与变更记录在任何中断点均如实可用；当任务要求在受限预算内产出可审计、状态诚实的结果时使用。
---

# contract-pilot：运行契约与诚实性控制层

## 定位声明

本技能**不构建思维导图本身**。导图的内容提取、结构设计与排版由代理人所选用的任意导图流水线完成；本技能是包裹在该流水线之外的**契约与诚实层**：负责输入清点、尽早落盘诚实 partial、预算感知检查点、状态转移校验与交付前最终对账。凡涉及 result.json 状态、契约字段填充、证据登记与不确定性披露的判断，均以本技能为准。

## 何时使用

- 评测或生产环境约定固定输入（/input/case.json、/input/task.md、材料文件）与固定输出（/app/output/result.json 及产物）的运行契约时；
- 存在严格资源预算（约 900 秒、约 64 次模型请求、单次响应 16384 token），必须保证任何中断点都留有可用结果时；
- 案例要求状态诚实（success/partial/unable_to_determine/refused）、来源可溯、不确定性显式列出、变更留有记录时；
- 材料可能缺失、相互冲突或需要人工确认，且这些情况必须被显式标注而非静默忽略时。

不适用场景：

- 无结构化输出契约的开放式写作任务（无 result.json 要求）；
- 允许无限时长的离线任务，且不要求过程可审计；
- 案例本身要求拒绝执行（此时仅写入 status=refused 并说明理由，不启动流水线）；
- 契约明确禁止任何中间文件落盘的环境。

## 固定运行方式

以下命令顺序固定，不可调换；所有脚本仅依赖 Python 3.10+ 标准库，无网络访问。

1. 引导（boot，流水线开始前必做）：

```bash
python3 scripts/contract_boot.py --case /input/case.json --task /input/task.md --out /app/output --work /app/work
```

2. 检查点（checkpoint，流水线每完成一个阶段执行一次；参数按需组合，可多次调用）：

```bash
python3 scripts/checkpoint.py --out /app/output \
  [--status STATUS] [--set FIELD=VALUE ...] [--artifact NAME=PATH ...] \
  [--uncertainty TEXT ...] [--resolve-uncertainty INDEX ...] \
  [--source PATH ...] [--note TEXT]
```

3. 最终对账（final_audit，交付前必做；exit 0 方可宣告完成）：

```bash
python3 scripts/final_audit.py --case /input/case.json --out /app/output --report /app/output/contract_audit.json
```

## 工作流程

1. **引导与清点（0–60 秒内完成）**：运行 contract_boot.py。该步骤即刻写出首份 partial 状态的 result.json——**首份 partial 必须在任何实质计算之前落盘**，此为本技能的核心不变量。随后人工（代理人）核对 intake_manifest.json 中的缺失材料与已播种的 uncertainty。
2. **提取与设计（60–300 秒）**：阅读材料、提取要点、设计导图结构。每完成一个子步骤即调用 checkpoint.py 登记 source 与不确定性；材料冲突或缺口必须当场写入 uncertainty，不得延后。
3. **构建（300–650 秒）**：生成导图及契约要求的各产物文件，逐一以 `--artifact NAME=PATH` 登记；同名契约字段仍为占位时将被自动填充。
4. **停止改进、转入收尾（约 650–700 秒，或模型请求剩余约 8 次时，以先到者为准）**：此后不再启动新的内容生成，仅做字段填齐、不确定性消解或如实保留、状态校正。宁可交付诚实的 partial，不可交付虚假的 success。
5. **验证与对账（700–850 秒）**：填齐全部契约字段后将状态置为 success（若仍有占位字段，checkpoint 会强制回退 partial，此为预期保护行为）；运行 final_audit.py；若审计失败，仅修复其指出的违例，不再扩写内容。
6. **交付（850 秒内完成）**：确认 contract_audit.json verdict 为 pass，或 result.json 为附精确限制说明的 partial/unable_to_determine。

预算分配建议（总量约 900 秒 / 64 次请求）：intake 约 7%、extract 约 25%、design 约 15%、build 约 30%、verify 约 15%、deliver 约 8%。细节见 references/budget-playbook.md。

## 输出物说明

| 路径 | 生成者 | 语义 |
| --- | --- | --- |
| /app/output/result.json | boot 创建，checkpoint 更新 | 契约结果：case_id、status、全部契约字段、sources、uncertainty、contract_fields、artifacts、partial_reason（partial 时） |
| /app/output/change_record.md | checkpoint 追加 | 每次 checkpoint 一行，`- seq N \| status: X \| artifacts: ... \| uncertainty: ... \| note: ...`，N 为单调序号，不含时间戳 |
| /app/output/contract_audit.json | final_audit 写出 | 七项检查逐条结果、契约覆盖率与 verdict |
| /app/work/work_plan.md | boot 创建 | intake→extract→design→build→verify→deliver 六步勾选清单 |
| /app/work/intake_manifest.json | boot 创建 | 逐项材料的 path、exists、size、sha256、readable、note |

## 异常处理表

| 异常 | 行为 |
| --- | --- |
| case.json 缺失或不可解析 | boot 仍写出 result.json（case_id="unknown"、status="unable_to_determine"、uncertainty 说明原因），exit 2；不尝试猜测契约 |
| case.json 缺少 output_contract 等字段 | boot 正常完成（exit 0），contract_fields 为空列表，result.json 仅含保留字段；代理人须自行在 uncertainty 中声明契约不完整并请求人工确认 |
| output_contract 缺失 | 同上：审计时 contract_coverage 为 0/0，status 永远不得置为 success，除非代理人已从任务描述重建契约并如实记录依据 |
| 材料路径不存在 | boot 在 intake_manifest.json 记 exists=false，并向 uncertainty 播种一条缺失说明，stderr 警告；绝不崩溃；后续流水线须将该材料视为不可用 |
| 预算耗尽 | 立即停止内容生成；用一次 checkpoint 把当前状态、已完成 artifact 与剩余限制写实；运行 final_audit；交付既有 partial |
| 状态与占位符不一致（请求 success 但仍有 "__pending__"） | checkpoint 拒绝该转移，强制回退 partial，并把拒绝理由追加到 partial_reason 与 change_record |
| artifact 路径不存在 | checkpoint 登记 exists=false、bytes=0 并警告；final_audit 第 4 项判 fail；交付前必须修正或移除该登记 |
| 同案例重跑 | boot 幂等覆盖 result.json、work_plan.md、intake_manifest.json，但 change_record.md 序号继续追加不复位；如需全新对账，先人工清空 /app/output 再重跑 |

## 最小合成示例说明

examples/ 目录为**合成示例**（synthetic demo，非真实科研材料）：synthetic-input/ 给出一份玩具 case.json（契约字段 mindmap_file、evidence_map、status、uncertainty）、一份玩具 task.md 与一份玩具材料文本；synthetic-output/ 是一次真实脚本化运行（boot → 三次 checkpoint，含一次被强制回退的 success 请求 → final_audit）的最终落盘状态，其 contract_audit.json verdict 为 pass。完整命令序列见 examples/README.md。该示例仅用于验证脚本行为，不得作为内容质量参照。

## 限制

- 本技能不评估导图的内容质量、结构合理性或学术正确性，仅保证运行契约与状态诚实；
- checkpoint 的契约字段填充以"同名且仍为占位"为唯一触发条件，命名不一致的字段须用 --set 显式填写；
- final_audit 检查 artifact 存在性与非空，不校验其内容是否与契约语义相符；
- 材料可读性校验基于引导时刻的文件系统状态，运行期被外部删除的文件须依赖 final_audit 捕获；
- 输出为确定性文本（单调序号、无时间戳），跨次运行的对账差异须由 change_record.md 人工比对；
- 脚本仅支持 UTF-8 文本环境；二进制材料仅清点（大小与 sha256），不做内容解析。
