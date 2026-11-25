---
name: "construct-blueprint-forge"
description: "当任务要求从实际研究段落和表格设计四题 benchmark-DRAFT、构念蓝图、题项蓝图测量覆盖、答案不变量、0/1/2 评分规则或题库版本快照时使用；也用于排查答案泄题、重复构念、边界不清与不可比较修订。不用于通用证据子串核验、自动评测/打分流水线、盲审、重跑台账，也不用于脱离原始任务批量造题。"
---

# 构念蓝图与题库锻造

目标是把**实际任务意图**转成四个可作答、能区分理解水平的来源条件题，而不是找四句话抄答案。每题恰承担一种认知操作：`locate_extract`、`table_relation_calculation`、`comparison_boundary`、`synthesis_conflict`。先读 `references/construct_design.md`，字段格式查 `references/item_schema.md`。

## 最短可靠运行路径

以下命令均从本技能解包目录用**相对路径**调用；运行时只依赖 Python 3 标准库，无第三方依赖、无需网络。不要从 `examples/` 复制任何科学内容。

1. 读 `/input/case.json`（保存原始 `case_id`，解析 `output_contract`）、`/input/task.md`，再逐个打开 `case.json` 指向的**真实材料文件**全文和表格。材料缺失、表格不可读、任务本身不足四构念时如实记录，绝不补常识。
2. 在任何长时间设计之前先创建工作目录并落一个合法的部分结果：

   ```bash
   mkdir -p /app/work /app/output
   python3 scripts/finalize.py --case /input/case.json \
     --output /app/output/result.json --partial-only --allow-partial
   ```

   此命令先保证 `/app/output/result.json` 存在：原 `case_id` 不变，且 `output_contract` 的**每个字段都在 JSON 顶层**；`items` 为空、`status` 为 `partial`，并保留 `sources`、`uncertainty`、`change_records`、`defects`。它不是可提交的成功结果。

3. 在 `/app/work` 阅读材料并先写蓝图，不先写题。可先获取纯结构骨架，但其中占位符永远无法通过校验：

   ```bash
   python3 scripts/blueprint.py --skeleton /app/work/blueprint.json
   # 用实际任务、材料范围、答案不变量和许可依据替换所有占位符后：
   python3 scripts/blueprint.py /app/work/blueprint.json \
     --case /input/case.json --output /app/work/blueprint_audit.json
   ```

4. 蓝图通过后编写 `/app/work/item_bank.json`。答案必须只来自实际材料；`input_material` 给作答者足够上下文，`evidence` 按蓝图的 claim_id 分工，rubric 与答案不变量一致。不要把答案词、数值答案、选项结论或冲突解决方向写进 `task`。然后执行：

   ```bash
   python3 scripts/item_audit.py /app/work/item_bank.json \
     --blueprint /app/work/blueprint.json --case /input/case.json \
     --output /app/work/item_audit.json
   ```

   审计的通过只表示结构、覆盖、泄题、算术等检查通过；仍须回到真实材料整体核读每题，**不能因一条引文命中便认定语义答案正确**。无把握的推断保留在 `uncertainty`，不得改写成确定事实。材料若只支持少于四题，保持不足四题并导出部分结果，不能凑题。

5. 仅有实际版本时才做版本差异；不存在旧版就不要伪造对比：

   ```bash
   # 初版：
   python3 scripts/snapshot.py /app/work/item_bank.json \
     --output /app/work/snapshot.json
   # 若确有先前实际保存的题库（也可是本工具生成的快照）：
   python3 scripts/snapshot.py /app/work/item_bank.json \
     --previous /app/work/item_bank.previous.json \
     --output /app/work/snapshot.json --diff-output /app/work/diff.json
   ```

6. 最后一次严格导出会重新执行蓝图和题项审计，不信任过期报告：

   ```bash
   python3 scripts/finalize.py --case /input/case.json \
     --blueprint /app/work/blueprint.json --items /app/work/item_bank.json \
     --output /app/output/result.json
   ```

   只有全部检查通过且恰好四题时才为 `status: success`；任何缺陷仍写出结果，但为 `partial`，默认退出 2。确实需要保留部分交付时加 `--allow-partial`，它只是允许退出 0，**不会清除缺陷或升级状态**。

## 动态输出合同与结果语义

`finalize.py` 把 `case_id`、`items`、`status`、`sources`、`uncertainty`、`change_records`、`defects` 置于顶层，再并入合同声明字段，不把结果藏进 `result` 或 `output` 包装层。支持：

- `output_contract: ["case_id", "items", ...]`；
- `output_contract: {"fields": ["case_id", {"name":"items","type":"list"}, ...]}`；
- 直接映射 `{"case_id":"string", "items":{"type":"array"}, "status":"string"}`，以及等价 `properties` 映射；
- 字段同义名作 `questions`、`item_bank` 等映射到实际题项，`uncertainties`/`changes` 同理；可用字段描述中的 `semantic` 显式指定。

无法安全映射的字段按类型给空值、加 `defects` 并强制 `partial`，不编造答案。`sources` 取自 case 的真实材料清单；`uncertainty` 合并 case、题库和题项的未决限制；`change_records` 只导出实际提供的变更记录。四个完整题项是标准 `items` 的语义值，不是预先填好的答案模板。

## 工作纪律

- 所有草稿、审计、快照只在 `/app/work`；最终只在 `/app/output/result.json`。真实科学答案只能来自当前 case 材料，不使用本技能的合成示例，不调用记忆补齐，不预写通用答案。
- 四题分别测量四种不同操作，不能只换问法或用同一答案重复制造四题。每题至少两个可独立检查的 claim，完整证据链和评分档不可被一条引文替代。
- 数据不足就明确缺源、不可判定、许可不足或任务不齐，用 `uncertainty` 保存限制；不得把“可能/未报告”改成事实。
- 不声称提高 benchmark 分数，不生成或推测任何 benchmark 实测分。0/1/2 是作答评分规则，不是 benchmark 得分。
- 表算术应声明 `arithmetic.expression`、`bindings` 和独立 `expected`；工具用安全 AST 仅支持数字、绑定名、括号、一元正负与 `+ - * /`，并核对来源数值、重算值和舍入容差。没有来源数值不算真表算术。

## 工具契约与非零退出

| 工具 | 用途 | 退出码 |
|---|---|---|
| `blueprint.py` | 四题蓝图、操作互补、具体范围/claim/rubric 校验 | 0 通过；2 审计缺陷；1 参数/IO/JSON 错误 |
| `item_audit.py` | 完整字段、构念对齐、答案泄题、重复题、rubric、算术、不确定性 | 0 通过；2 审计缺陷；1 参数/IO/JSON 错误 |
| `snapshot.py` | 内容寻址快照、实际版本答案/rubric 变化与可比性 | 0 成功；1 参数/IO/JSON/内容地址错误 |
| `finalize.py` | 重审并动态顶层导出成功或部分结果 | 0 成功（或显式允许 partial）；2 严格模式 partial；1 无法读 case 或写结果等错误 |

所有 JSON 报告包含具体 `code`、字段 `path`、`item_id`（适用时）和诊断消息。不要忽略非零退出。

## 独立合成自检

`examples/synthetic` 的段落、表格、答案、版本均完全合成，不表示外部科学主张，也不能用于真实 case。输出目录由调用者给定，或在系统临时目录创建，技能包内不保存运行输出：

```bash
bash examples/synthetic/run_example.sh /app/work/example-check
# 省略目录亦可：bash examples/synthetic/run_example.sh
```

脚本产出蓝图审计、题项审计、内容快照、版本 diff、最终结果和负例审计；负例必须因答案泄题显式拒绝，否则自检失败。
