# 事实 grounding 规则 — source-fidelity-firewall

本文件是 `extract_facts.py` / `ground_evidence.py` / `fact_diff_guard.py`
三个脚本行为的文字规范，供模型在执行编辑与人工复核时遵循。

## 1. 事实类型（extract_facts.py 提取）

| type | 定义 | 例 |
|-|-|-|
| `number_with_unit` | 带单位数字，含范围 | `2.4 V`、`85%`、`1.2 mS/cm`、`60 °C`、`4~6 h` |
| `term_definition` | 术语/缩写首次定义，"全称（ABBR）"模式，每缩写只记首次 | `固态电解质（SSE）` |
| `citation` | `[n]` 数字引文（参考文献小节内不提取） | `[1]` |
| `figure_ref` | 图/表/Fig./Table 编号引用 | `图1`、`表2`、`Fig. 3` |

每条事实含 `id`（F0001…）、`type`、`value`、`context`（所在句子）、
`file`、`line`。代码块与"参考文献/References"小节内的内容不提取。

## 2. 证据定位策略（ground_evidence.py）

逐条事实按以下顺序回源，取第一个逐字命中（空白折叠后包含匹配，容忍
PDF 折行；记录的 quote 保持原文）：

1. **材料文本**（`--materials` 目录）：`.txt`/`.md` 直接读取；`.pdf`
   先用 `pdftotext -enc UTF-8` 转入缓存目录再读。命中 → `origin=materials`。
2. **原始工作稿章节自身**（`--chapters`）：W16 设定下原始工作稿即事实
   底稿，命中 → `origin=working_chapters`。
3. 两处都不命中 → `origin=unresolved`、`verification=FAIL`，进入
   uncertainty，必须由模型处理（换引文/删除论断/标【待确认】）。

`verification` 由脚本在写出前对 quote 重新做包含校验写回，
**不信任任何人工声明**；人工声称"已核对"不构成证据。

## 3. origin 语义

- `materials`：论断可直接回溯到题目提供的上游材料，保真度最高。
- `working_chapters`：论断只存在于原始工作稿。它是本案例的事实底稿，
  编辑时**允许保留但不得改数**；它不构成"新材料"，编辑不得据此引入
  改前文本中不存在的数字。
- `unresolved`：无法回源。禁止带着 unresolved 事实交付 complete。

## 4. 编辑后把关（fact_diff_guard.py）

- **闸 A（token 级）**：改后文本的每个数字 token、全大写缩写、`[n]`
  引文，必须出现在 改前文本 ∪ 材料文本 ∪ evidence_map 语料 中，
  否则 `fabrication_token`。
- **闸 B（句子级）**：改后新增的含数字/引文的句子，其每个数字/引文
  token 必须被 evidence_map 的 claim/quote/value 覆盖，否则
  `unverified_new_sentence`。
- 任何 flag → `guard_report.json` 状态 FAIL、退出码 1。**FAIL 时禁止
  交付**：修复编辑或删除/标注该论断后重跑，直至 PASS 或如实 partial。

## 5. 人工确认标注格式

模型无法判定、需人复核的事实，在正文中原地标注：

```
【待确认：<原因，含涉及的事实值与建议动作>】
```

例：`【待确认：循环保持率 85% 在材料中仅见于实验记录草稿，建议作者核对原始数据】`

`make_result.py` 会自动收集所有【待确认：…】进入 result.json 的
`uncertainty`。带待确认标注的交付必须是 `status=partial`。

## 6. 编辑纪律（模型必须遵守）

1. 任何进入改后文本的事实必须可回溯：改前文本、材料、或 evidence_map
   三者之一。
2. 改写可以重组语句，但**数字、单位、缩写、引文编号不得创造**。
3. 引文逐字回源：新增/移动 `[n]` 前，确认该编号在参考文献小节存在
   且论断与原句一致。
4. 发现改前文本自身有事实错误时：不得"顺手改数"，标【待确认：…】。
