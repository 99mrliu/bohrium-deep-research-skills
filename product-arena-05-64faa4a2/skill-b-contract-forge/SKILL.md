---
name: contract-forge
description: 契约优先的方法与实验章节写作 Skill——先解析 case.json/task.md 提取 output_contract，生成 result.json 骨架并增量填充，交付前门禁验收并渲染 SVG 预览，确保"交得对、看得见"。
---

# contract-forge：契约优先的章节写作交付工程

## 一、用途与适用条件

本 Skill 面向科研案例写作任务（"方法与实验章节写作"），核心思想是：**大多数失败不是写得差，而是"交付错位"**——result.json 缺字段、case_id 串案例、产物放错路径、正文数值不可回溯、预览缺失。本 Skill 把"契约优先"工程化为一条可执行的流水线：

1. 先解析 `/input/case.json` 与 `/input/task.md` 的实际内容，提取 `output_contract` 声明的全部字段与交付要求（不凭标签猜）；
2. 生成 `result.json` 骨架（case_id + 全部契约字段，初值诚实标记为 pending）；
3. 写作过程中增量填充骨架，尽早保存部分产物；
4. 交付前用门禁脚本逐字段验收，并抽查正文数值可回溯性，**不通过不交付**；
5. 用纯标准库生成章节 SVG 预览，使产物"看得见"。

### 适用条件

- 输入目录含 `case.json`（或等价 JSON）与 `task.md`；工作目录 `/app/work`，最终产物目录 `/app/output`。
- 运行环境仅有 Python 3 标准库、无网络。本 Skill 全部脚本均为纯标准库、确定性输出，可离线运行。
- 任务产出为文档类交付（章节正文 + 结构化 result.json + 渲染预览）。

### 不适用情形

- 要求真实训练模型、访问外部数据库、联网检索等超出本地材料能力的任务——此时应如实标记 `unavailable`，而非编造结果。
- 契约要求二进制 Office 产物（docx 等）：本 Skill 只产出文本与 SVG；docx 类需求按 `partial` 处理并说明，或用文本等价物 + 预览替代并记录 assumption。

## 二、运行时契约（必须遵守）

1. **读实际内容，不凭标签猜**：逐字读取 `/input/case.json` 与 `/input/task.md`，契约字段名以文件实际写法为准。目录名、文件名、案例标签一律不作为内容依据。
2. **路径约定**：工作文件一律写入 `/app/work`；最终产物（result.json、chapter.md、预览等）写入 `/app/output`。result.json 中引用产物时用相对于 `/app/output` 的路径。
3. **result.json 字段完整**：必须含 `case_id` 和 `case.json` 中 `output_contract` 声明的全部字段；如实读取字段名逐个填充；字段语义不明时保守填充并在该字段的 `assumptions`/`notes` 中说明，不猜不造。
4. **诚实状态**：材料缺失、无法判断、运行失败分别用 `unavailable` / `unknown` / `failed` 说明原因；`partial` 必须标明具体局限；不编造软件状态或科学数据。
5. **尽早保存**：每完成一个可交付片段即落盘（先骨架、后增量填充），防止预算耗尽导致零交付。任何时候 `/app/output/result.json` 都应存在且状态如实。
6. **溯源与审计**：产物含来源定位（sources：文件路径+定位符）、修改记录（changes）、不确定性（uncertainty）、人工确认项（needs_human_review）。
7. **可编辑产物附真实渲染预览**：chapter.md 等文档类产物须附 `chapter.preview.svg`（纯标准库真实渲染，禁止手工绘制冒充）。
8. **章节六要素**：正文须覆盖——步骤（procedures）、实验设置（setup）、参数与来源（parameters & provenance）、数据集与划分（dataset & splits）、对照（baselines/controls）、复现与限制（reproducibility & limitations）。

## 三、调用步骤（按序执行）

```bash
SKILL=/skills/weekly-skill   # 或本 bundle 实际安装路径

# ① 解析输入，提取契约 → /app/work/contract.json
python3 $SKILL/scripts/contract_probe.py --input-dir /input --work-dir /app/work

# ② 生成 result.json 骨架 → /app/work/result.skeleton.json
#    （加 --output-dir /app/output 则同时写入 /app/output/result.json 骨架，尽早占位）
python3 $SKILL/scripts/result_scaffold.py --contract /app/work/contract.json \
    --work-dir /app/work --output-dir /app/output

# ③ 模型写作：撰写 /app/work/chapter.md（覆盖六要素），并按 contract.json 的字段清单
#    增量填充骨架各字段的 value/sources/uncertainty/assumptions/notes，
#    导出为 /app/output/result.json。每完成一个字段即保存一次 result.json。

# ④ 生成预览 → /app/output/chapter.preview.svg
python3 $SKILL/scripts/preview_render.py --chapter /app/output/chapter.md \
    --output /app/output/chapter.preview.svg

# ⑤ 交付前门禁验收；退出码非零则回到 ③ 修复，不得交付
python3 $SKILL/scripts/delivery_gate.py --input-dir /input \
    --output-dir /app/output --chapter /app/output/chapter.md \
    --report /app/output/gate_report
```

顺序说明：④⑤可调换，但门禁必须是交付前的最后一步。若门禁 FAIL，按 `gate_report.md` 逐项修复后重跑门禁直至 PASS（允许 WARN，但需人工确认 WARN 项）。

### 各步骤的输入/输出与失败行为

| 步骤 | 输入 | 输出 | 失败行为 |
|---|---|---|---|
| ① contract_probe | /input/case.json、task.md、材料清单 | /app/work/contract.json | case.json 缺失/非法：记 unrecognized，contract_fields 为空，仍产出 contract.json |
| ② result_scaffold | contract.json | result.skeleton.json、WORKSPACE.md、（可选）/app/output/result.json 占位 | contract.json 非法：退出码 2，不产出 |
| ③ 模型填充 | 骨架 + 材料 | /app/output/chapter.md、填充后的 result.json | 材料缺失字段标 unavailable + 原因 |
| ④ preview_render | chapter.md | chapter.preview.svg | 渲染异常：输出降级合法 SVG + 失败注释，退出码 0 但 stderr 告警 |
| ⑤ delivery_gate | /input、/app/output | gate_report.json/md | 任一 FAIL：退出码 1，禁止交付 |

## 四、result.json 契约详解

### 4.1 顶层结构

- `case_id`：必须与 `case.json` 中的 `case_id` **逐字符一致**（门禁 G2 校验）。
- `output_contract` 声明的每个字段：以契约中**原始字段名**作为 result.json 的键，不得改名、不得漏项、不得新增同名近义键代替。
- 推荐每个字段使用统一填充结构（骨架已给出）：

```json
{
  "status": "done | partial | unavailable | unknown | failed | pending",
  "value": "实际内容或指向 /app/output 下产物文件的相对路径",
  "sources": [{"file": "材料相对路径", "locator": "行号/表号/字段路径", "note": "引用了什么"}],
  "uncertainty": ["不确定点及原因"],
  "assumptions": ["语义不明时采用的保守解释"],
  "notes": ""
}
```

- 若契约声明了扁平标量形态（如 `"status": {"type": "string"}`），仍以统一结构填充：把实际值放进 `value`，把状态放进 `status`，语义不丢失且门禁可机检。

### 4.2 字段语义不明时的保守填充规则

1. **不改字段名、不删字段**：语义不明也要保留键，给保守初值。
2. **保守初值**：数值/事实类填 `null` 并 `status:"unknown"`；文本类填保守说明并 `status:"partial"`。
3. **记录 assumption**：在该字段 `assumptions` 写明"将该字段理解为……，因契约未说明……"。
4. **请求人工确认**：加入 `needs_human_review` 清单（契约无此字段时写入该字段 `notes`）。
5. 禁止：把示例值当真实值、把别的字段内容复制充数、编造"系统默认"作为来源。

常见字段模式与填充示例详见 `references/contract_patterns.md`。

### 4.3 状态语义

| status | 含义 | 必须附带 |
|---|---|---|
| `done` | 完整且可回溯 | 非空 value；事实类附 sources |
| `partial` | 部分完成 | uncertainty 写明缺什么、为何缺、影响 |
| `unavailable` | 材料缺失 | 查找过的位置清单 |
| `unknown` | 无法判断 | 判断受阻的原因 |
| `failed` | 运行失败 | 错误摘要与发生步骤 |
| `pending` | 骨架初值 | **禁止出现在最终交付中**（门禁判 FAIL） |

## 五、门禁检查项（delivery_gate.py）

| 编号 | 检查 | 判据 |
|---|---|---|
| G1 | result.json 存在且合法 | 不存在或 JSON 非法 → FAIL，后续依赖检查跳过 |
| G2 | case_id 一致 | 与 case.json 逐字符比对；不一致即"串案例"→ FAIL |
| G3 | 契约字段完整 | 逐字段检查：缺失 → FAIL；pending 残留 → FAIL；unavailable/partial/unknown/failed 无原因 → FAIL；done 但 value 空 → FAIL |
| G4 | 引用文件存在 | result.json 中 value/sources 引用的文件须在 /app/output（产物）或 /input（材料）真实存在 |
| G5 | 预览存在 | 契约或 task.md 提到预览/渲染/svg/png/pdf 时，/app/output 须有对应预览文件 |
| G6 | 数值可回溯抽样 | 抽取 chapter.md 中前 40 个去重数值，在 sources 指向的材料文本中定位；定位不到记 WARN 并要求人工确认；来源全部不可读 → FAIL |

报告同时输出 `gate_report.json`（机读）与 `gate_report.md`（人读表格）。

## 六、异常处理

| 情形 | 处理 |
|---|---|
| `/input/case.json` 不存在或 JSON 非法 | contract_probe 记录 unrecognized 并继续；在 task.md 与日志中寻找等价信息；result.json 中 `case_id` 标 `unknown` 并说明 |
| 找不到 `output_contract` | contract_probe 自动尝试命名变体（`outputContract`/`output-contract`/嵌套于 `task` 等，深度优先）；仍无则 `contract_fields: []`，骨架退化为保守默认字段 artifact/status 并在 warnings 说明 |
| 契约字段类型无法猜测 | `type_guess: "unknown"`，骨架给通用占位结构，语义猜测标 unknown |
| 材料文件损坏/为空 | 对应字段 `unavailable` + 原因；章节中该来源处如实标注 |
| 预览渲染失败 | preview_render 输出最小合法 SVG 并以注释记录失败原因；绝不交付伪造预览 |
| 预算不足 | 骨架 + 已完成字段的 result.json 已在 /app/output，状态如实为 partial |

## 七、最小示例（合成）

`examples/` 提供完整可运行示例（**合成示例，非正式案例结果**）：

```bash
cd examples && bash run_example.sh
```

流程：`case/case.json`（含 case_id 与嵌套在 task 下的 output_contract：artifact、sources、uncertainty、status 四字段）→ contract_probe 提取契约 → result_scaffold 生成骨架 → 脚本内模拟填充最小 chapter.md 并填充骨架 → preview_render 出 SVG → delivery_gate 全 PASS → 再构造缺字段负例验证门禁判 FAIL。预期产物在 `examples/expected/`，详见 `examples/README.md`。

## 八、增量填充操作协议（步骤③的工作纪律）

骨架不是一次填完的表单，而是随写作推进的"账本"。推荐以下节奏：

1. **先建章节大纲**：在 `/app/work/chapter.md` 写入六要素的标题骨架，立即复制到 `/app/output/chapter.md`——即使预算在此时耗尽，也已有一个 partial 但形态完整的交付。
2. **逐节写作、逐字段填充**：每写完一节，把该节涉及的契约字段更新一次并保存 `/app/output/result.json`。例如写完"参数与来源"节，就把 parameters 类字段标 done 并附 sources locator。
3. **数值当场登记**：章节中每写一个数值，立即在对应字段的 `sources` 里加一条 `{file, locator, note}`。不要事后补登记——事后补录是数值不可回溯（失败模式 F8）的主要来源。
4. **修改留痕**：若任务提供了草稿而你在其基础上修改，每处实质性修改在 changes 类字段记录 `{target, before, after, reason}`。
5. **保存即校验**：每次保存 result.json 后用 `python3 -m json.tool` 或门禁 G1 验证合法性，防止手误累积到最后。
6. **交付前清点**：对照 contract.json 的 `field_order` 逐字段过目；确认无 pending、无空 assumptions 该填未填。

## 九、与评测运行时的对照清单

交付前用下表自查（门禁已覆盖的项注明编号）：

| 自查项 | 依据 | 工具 |
|---|---|---|
| 读的是 /input 实际内容而非标签 | 运行时契约 1 | contract_probe 输出 unrecognized 清单 |
| result.json 在 /app/output | 运行时契约 2 | G1 |
| case_id 与 case.json 一致 | 运行时契约 3 | G2 |
| output_contract 全部字段存在且填充 | 运行时契约 3 | G3 |
| 语义不明字段有 assumption 记录 | 运行时契约 3 | 人工 + G3 |
| partial/unavailable 附原因 | 运行时契约 4 | G3 |
| 产物引用路径真实存在 | 运行时契约 5/6 | G4 |
| sources/uncertainty/changes/人工确认项齐备 | 运行时契约 6 | 人工 + contract_patterns.md |
| 预览文件真实渲染且存在 | 运行时契约 7 | G5 + preview_render |
| 正文数值可回溯 | 运行时契约 6 | G6 |
| 章节覆盖六要素 | 运行时契约 8 | 人工（对照第八节大纲） |

## 十、边界

- 本 Skill 不生成科学结论，只保证交付形态正确、数值可回溯；正文的科学正确性依赖模型对材料的阅读理解。
- 门禁的数值回溯是**抽样定位**（在 sources 指向的材料文件中查找正文出现的数值），不是逐数真值验证；派生计算值（如由两个材料数值相减得到）会命中 WARN，需人工确认。
- SVG 预览是排版级预览（标题层级/段落/表格/列表/代码块），不模拟任何 Office 渲染引擎；中文字符按全角宽度估算换行。
- 不处理需要联网、第三方库或真实计算实验的交付物；遇此需求按 `unavailable`/`failed` 诚实上报。
- 资源约束：全部脚本纯标准库、无网络、确定性输出；单文件为 UTF-8 文本。
- 失败模式速查：`references/delivery_failures.md` 列出 10 类交付错位失败及本 Skill 的对治环节，写作前建议通读。

## 十一、Bundle 文件与角色

| 路径 | 角色 |
|---|---|
| `SKILL.md` | 本文件：契约、步骤、填充规则、异常处理、边界 |
| `scripts/contract_probe.py` | 步骤①：解析 /input，输出 contract.json |
| `scripts/result_scaffold.py` | 步骤②：生成骨架与工作目录约定 |
| `scripts/preview_render.py` | 步骤④：chapter.md → 自包含 SVG 预览 |
| `scripts/delivery_gate.py` | 步骤⑤：交付前门禁（G1–G6），FAIL 退出码 1 |
| `references/contract_patterns.md` | 契约字段模式与保守填充规则 |
| `references/delivery_failures.md` | 交付错位失败模式集（F1–F10） |
| `examples/` | 合成示例与端到端自检脚本（非正式案例结果） |
