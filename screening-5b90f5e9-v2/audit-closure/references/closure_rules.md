# 计数闭合规则（C1–C4）

审稿人问"为什么从 1832 条变成 47 条"时，答案必须能从台账里直接读出来。
闭合校验就是把这个追问变成自动硬门。

## 规则定义

| 规则 | 内容 | FAIL 意味着什么 |
|---|---|---|
| C1 | `identified − duplicates_removed = screened` | 去重环节吞了或多出了记录 |
| C2 | `screened = included + excluded + needs_human (+ unprocessed)` | 判定环节有记录下落不明；unprocessed 必须显式登记，不允许藏差额 |
| C3 | 每条台账记录计数非负；流式阶段 output ≤ input | 台账本身被手改或记录错误 |
| C4 | identified/dedup/screened/included/excluded/needs_human 六阶段齐备 | 流程缺环节，无法独立复核 |

## 差额处理纪律

- validate 打印每条规则的**算式与差额**，FAIL 时差额就是排查起点；
- 禁止为凑闭合回头改早期计数——正确做法是找到丢失/多出的记录，
  在对应阶段补一条带 basis 的更正记录，并在 notes 说明；
- unprocessed 只用于"时间预算耗尽、明确未判"的记录，且在 result.json 的
  uncertainty 中点名；用它吸收差异是作弊；
- 计数来源（basis）必须指向真实产物文件，复核者按 basis 重数应得同数。

## 与 PRISMA 2020 的对应

C1 覆盖 Identification→Screening 的流量守恒；C2 覆盖 Screening→Included；
台账的 operator/timestamp/basis 三字段支撑 PRISMA 之外的审计追问
（谁、什么时候、按什么依据）。流量图渲染属下游交付环节，本技能只保证
数字自身闭合且可证明。
