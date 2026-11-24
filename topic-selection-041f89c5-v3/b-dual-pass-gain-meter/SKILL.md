---
name: dual-pass-gain-meter
description: 增益自证取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与科研材料，要求完成文献综述、选题或创新性评估并在 /app/output 交付结构化 result.json，且评估方关心"加载技能相对基础 Agent 是否真有增益"时使用。核心立场：增益不能自述，必须对照测量——先用 ≤4 次请求的限时快速通道写一份"基础 Agent 会写的那种"基线稿（pass0），再用完整协议写严谨稿（pass1），最后由 scripts/gain_meter.py 对两稿做确定性指标差分（填充率、证据锚点、越界断言、不确定性、冲突登记），gain_report 随结果一并交付；overclaim_lint.py 在起草期拦截无边界新颖性断言。不适用：预算不足以跑两遍草稿的极窄场景（此时只跑严谨稿并如实说明）。
---

# dual-pass-gain-meter：增益不是写出来的，是对照出来的

## 核心主张

"加载技能后质量更好"若只靠文字自述，评审无法复核。本技能把增益变成**受控对照实验**：同一输入、同一契约下，快速基线稿与严谨稿并行存在，差分指标由脚本确定性计算——基线稿刻意保留基础 Agent 的典型毛病（无边界"尚无人研究"、结论无锚点、不确定性空白），严谨稿按协议消除它们，报告里的每个差值都可独立重算。增益报告本身就是交付物。

## 运行时契约（必须先读）

1. 输入在 `/input`：`task.md`、`case.json`（含 `case_id`、`output_contract`）、材料文件（PDF/TXT/JSON/CSV）。逐文件读真实内容，不依据文件名或标签猜测；PDF 用运行环境实际可用的解析工具从原始 PDF 提取，不假设有预提取文本层。
2. 若存在 `/input/environment/resources.yaml`，先读它确认可用工具。
3. 中间产物写入 `/app/work`，最终交付写入 `/app/output`。
4. `/app/output/result.json` 必须含 `case_id`（与 case.json 逐字一致）与 `output_contract` 声明的**全部原始字段**，字段名逐字照抄。
5. 预算：约 64 次模型请求、900 秒、单次响应 16384 token。**第一时间写出 result.json 骨架**（契约字段置 null、status=in_progress），逐阶段回填。
6. 诚实状态：`status` 只能是 `success` / `partial` / `failed`；partial 写明缺什么、为什么。
7. 禁止伪造：检索不到写检索不到并给出检索范围；不依据错误的领域标签补造数据。

## 工作流程

### 阶段 0：骨架与基线稿（pass0，≤4 次请求，严格限时）

1. 清点 `/input`（`/app/work/inventory.md`），按 output_contract 写 `/app/output/result.json` 骨架。
2. **在不调用任何脚本、不做逐篇精读的前提下**，凭任务书与材料的第一印象写基线稿 `/app/work/pass0_result.json`：字段同契约，写法模拟基础 Agent——综述式段落、少定位、无冲突登记。基线稿规则见 `references/baseline_protocol.md`：**公平性是本技能的生命线**——pass0 必须与 pass1 面对同一输入、同一契约，不许故意写得比基础 Agent 更差（稻草人），只许省略协议步骤。

### 阶段 1：严谨稿（pass1，完整协议）

1. 研究问题结构化：对象、变量、基线、预期结论方向、可证伪条件。
2. 检索与筛选留痕：每条候选记录判 纳入/排除/待定 并写理由；**覆盖边界声明**落盘——"未见"类结论永远带边界。
3. 证据表：每篇纳入文献提取可比较字段，每条证据带 `[来源:文件名+定位]`。
4. 四项交付起草：已有工作比较（含不可比对象及原因）、创新点逐条判定（已被覆盖/部分覆盖/未见覆盖/无法判定，"未见覆盖"同句写边界）、可行性前提逐条标 `[来源]` 或 `[假设]`、不确定性与冲突证据（双方均列出）。
5. 起草中随时运行：

   ```
   python3 /skills/weekly-skill/scripts/overclaim_lint.py /app/work/pass1_result.json
   ```

   命中无边界越界断言（exit 1）必须当场修复：加边界限定或删除。

### 阶段 2：差分与交付

```
python3 /skills/weekly-skill/scripts/gain_meter.py \
    --baseline /app/work/pass0_result.json \
    --final /app/work/pass1_result.json \
    --contract /input/case.json --out /app/work/gain
```

1. 读 `gain_report.json`：任一判定为 ✗，说明严谨稿在该维度没有可证明增益——回到阶段 1 修，不许带着 ✗ 交付。
2. pass1 内容回填 `/app/output/result.json`；把 `gain_report.json/md`、`overclaim_lint` 末次输出、`pass0_result.json` 一并复制到 `/app/output`：评审可独立重算每个数字。
3. 预算不足以跑基线稿时：只跑严谨稿，在 result.json 的不确定性字段写明"未做对照通道，增益不可核"，不许事后补造一份 pass0。

## 异常处理

| 情形 | 处置 |
|-|-|
| overclaim_lint exit 1 | 逐条修复后重跑；不许提交带违规的稿件 |
| gain_meter 判 ✗ | 回阶段 1 补强对应维度后重测；连续两轮仍 ✗ 则在不确定性中如实登记"该维度增益未证实" |
| pass0 不小心写得过好 | 不重写（避免人为放大增益）；在报告中注明"基线质量高于预期" |
| 材料为空/全部排除 | status=partial；两稿照常产出（内容为空 + 说明），差分报告照常生成 |
| 预算危急 | 立即把当前最好稿件回填 result.json（partial），gain_report 能出则出，出不了写明原因 |

## 红线

- 不许把 pass0 写成稻草人（故意漏掉显而易见的内容）；不许先写 pass1 再倒推 pass0；不许只报告有利指标；gain_report 五项判定任一 ✗ 不许宣称"有增益"。

## 最小示例

`examples/` 内有**合成示例**：虚构案例 `SYNTH-GAIN-001`，pass0（故意保留 4 处无边界越界断言、0 锚点）与 pass1（协议修复后）→ `overclaim_lint` 对两稿分别 exit 1 / exit 0，`gain_meter` 五项判定全过。命令与预期输出见 `examples/minimal_example.md`，实跑产物在 `examples/output/`。
