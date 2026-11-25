# 证据定位与前瞻决策规范

## 1. 证据记录不是装饰性台账

每条证据必须实际支持一个假设、对照、读数、步骤或决策对象：

```json
{
  "id":"E1",
  "source_class":"case_json",
  "locator":"$.protocol_assumptions.initial_rate_window_min",
  "supports":["H1","R1","S5"],
  "quote":"[3,8]"
}
```

必需字段：`id`、`source_class`、`locator`、`supports`。有原文时提供完全一致的短 `quote`。compile对case JSONPath作机械解析；材料文本在可读时检查精确子串。它不联网核实外部论文，也不把一条证据变成“已确认机制”。

## 2. case JSONPath与规范quote

支持的形式：

```text
$.mechanism_context.objective
$.protocol_assumptions.initial_rate_window_min
$.candidate_plans[0].version
```

`case_json` 的quote必须是定位值的 **canonical JSON**：UTF-8字符直接保留、无多余空格。可用下列本地命令计算，避免手误：

```bash
python3 - <<'PY'
import json
case=json.load(open('/input/case.json',encoding='utf-8'))
value=case['protocol_assumptions']['initial_rate_window_min']
print(json.dumps(value,ensure_ascii=False,separators=(',',':')))
PY
```

例子：

| 定位值 | 正确quote |
|---|---|
| 数组 `[3, 8]` | `[3,8]` |
| 数 `30` | `30` |
| 字符串 `低背景` | `"低背景"`（含JSON双引号） |

路径不存在或quote不匹配是 `FAIL`，结果必须partial。仅路径定位但不给quote会产生警告，因为值虽定位到了却未由智能体留下可追溯摘录。

## 3. 实际提供文本/PDF

提供Markdown时：

```json
{
  "id":"E2", "source_class":"provided_markdown",
  "locator":"source_note.md#section-label",
  "supports":["H2","R2"],
  "quote":"源文件中逐字存在的一句话"
}
```

`#`后片段用于人读定位，脚本以第一个`#`前路径寻找文件并检查原文子串。没找到文件只警告“未核验”；找到却引文不匹配是FAIL。不要引用示例case中不存在的论文、DOI、仪器型号或参数。

inspect会读取实际文本材料，并在可用时执行：

```text
pdftotext -layout actual.pdf /app/work/pdf_text/....txt
```

抽取文本标记为 `extracted_unverified`；没有PDF、没有pdftotext或抽取失败分别保留限制。compile不会因此杜撰PDF结论。官方任务需要PDF细节时，智能体只能使用实际抽取内容并保留定位与不确定性。

## 4. 证据等级与参数声明

区分：

- `实际case值`：参数域、期限、预算或任务明确给定的协议条件；
- `实际材料原文`：可追溯输入，仍需判断适用性；
- `前瞻协议假设`：为了让方案可判定而预设的阈值/方向，尚未得到实验观测；
- `外部研究`：只有实际存在并核验的来源才可引用；
- `实测结果`：本工作流不会生成，不得把合成数值包装成实测。

若来源没有说明某个阈值，就直接把阈值写入 `criterion` 并在 `uncertainty` 标为协议假设，不要制造证据ID来假装有外部支持。

## 5. 决策规则模板

主要读数必须同时给出方向、指标、单位、判据与动作。推荐显式三支：

```text
支持分支：若A对照通过QC、B条件出现预设方向/幅度且n个独立重复一致，
         则只作出本实验可识别的结论，并进入下一个机制分流。
不支持分支：若系统窗口/QC有效而预测不成立，则报告未支持当前假设；
           不用更多技术复孔掩盖独立重复不一致。
不可判定分支：若背景超阈、阳性窗口失效、材料缺失或轨迹非线性，
             则为不可判定，保留原始数据、触发补救，不称为阴性或阳性。
```

### 合成示例：光学干扰优先级

- R1表观初速下降≥30%，但R2显示强X自身荧光：不能立即宣称真实抑制；先做逐浓度匹配背景校正。
- 校正后不再跨30%决策点：光学解释足够解释表观效应，H1未获支持。
- 背景轨迹非线性、仪器饱和或无法匹配：不可判定，不选择性删孔。
- R3洗涤剂使抑制率配对下降：支持“聚集相关可能性”，仍不单独证明聚集或直接结合。

上述30%是合成case协议假设，不是普适文献阈值。真实任务必须以实际case/材料为依据或清楚标为待确认假设。

## 6. 警告、FAIL与结果状态

- `PASS`：机械检查通过，不代表机制被证实或设备已预订。
- `PASS_WITH_WARNINGS`：可生成完整计划，但仍有未机械核验的外部来源、未声明参数域等限制，应写入uncertainty。
- `FAIL`：科学结构、数值域、算术、资源绑定、证据case定位等出现硬错误；`result.status=partial`。
- `missing_generator`：output_contract要求了未知字段；该字段明确为空并保留原因，result为partial。
- `blocked`：case本身不能读取/解析，无法形成可靠案例级计划。

候选方案的FAIL独立存放在 `candidate_assessment`。新修订方案即使无FAIL，也不能回写候选历史或宣称已有实验结果。

## 7. 动态结果字段

通用required_fields映射如下：

| required field | compile生成内容 |
|---|---|
| revised_plan | plan.json/plan.md/SVG指针、总成本、单轮/重复展开工作分钟、仪器预订分钟、日程及执行合同 |
| candidate_assessment | compile内部基于实际候选的全新Decimal/域审计 |
| validation | PASS/WARN/FAIL、错误、警告和validation.json指针 |
| status | complete / partial / blocked |
| uncertainty | 设计不确定性、证据/价格/型号/实测限制 |
| sources | 设计证据记录及定位/引文 |
| change_log | 设计的可追溯修订记录 |
| confirmation_items | 设计待确认项及价格/设备/预订通用确认 |

任何额外required field均得到显式 `missing_generator`，而不是猜测一个值。`case_id` 始终额外保留。
