# 答题纸行格式规范

每题一个文件 `sheets/Q<n>.md`，五种行指令，其余行忽略（可作笔记）。

## 行指令

| 指令 | 格式 | 说明 |
|-|-|-|
| `STATUS:` | `STATUS: answered` | 四枚举之一；与内容自洽（answered 时不得有 UNANSWERED 行） |
| `ANSWER:` | `ANSWER:` 起，续行直到下一个指令 | 连贯中文回答；可多行；以 `（` 开头的续行视为注释 |
| `CONDITIONS:` | 分号分隔的条件列表 | 每个数值对应的实验条件；无则留空 |
| `CLAIM:` | `CLAIM: reported\|inferred \| 中文论断 \| P段号 "逐字引文" ; P段号 "引文2"` | 每行一条；引文逐字摘自所引段落 |
| `UNANSWERED:` | `UNANSWERED: 缺口子问 \| 原因` | 每行一条；无缺口则不写 |

## 填写纪律

1. 引文必须逐字（空白可不同）；`finalize` 逐字校验，错一词即整次失败、
   产物不覆盖。
2. 作者解释类论断 text 中带"作者"字样；自己比较/换算的论断 kind 用
   inferred 且 text 写明推断措辞。
3. "材料未报告"子问：STATUS 可为 `insufficient_evidence`，ANSWER 写明
   "已核对 P…，材料未报告 X"；原文有明确否定句时挂为 CLAIM 证据。
4. STATUS 是声明，渲染器会按题目间一致性推导顶层 status；
   声明与实际内容（有无 CLAIM、有无 UNANSWERED）由 finalize 校验。

## 最小示例（节选自合成示例）

```text
STATUS: answered
ANSWER:
ECAP 四道次后 UTS 为 385 MPa、断后延伸率 14.2%（初始应变速率 1e-3 per s）。
CONDITIONS: 室温 ECAP 四道次; 初始应变速率 1e-3 per s
CLAIM: reported | 四道次后 UTS 385 MPa、延伸率 14.2%，粗晶态 312 MPa、21.5% | P2 "an ultimate tensile strength of 385 MPa and an elongation to failure of 14.2 percent"
```
