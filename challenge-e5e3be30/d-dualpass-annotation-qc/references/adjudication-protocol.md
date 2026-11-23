# 仲裁协议：双通道分歧的保守合并规则（v1.0）

本协议由 `scripts/adjudicate.py` 机械执行，任何通道不得绕过脚本直接改最终判定。设计原则：**宁可低估，不可高估**——分歧存在时，终判向更不乐观的方向收敛，并把不确定性显式留给复核人。

## 1. 悲观方向序

```
supported  >  partially_supported  >  insufficient_evidence
（更乐观）                                  （更不乐观）
```

`contradicted` 不在序内：它断言"原文明确反对"，与任何其他判定的分歧都按冲突特例处理（见 §3）。

## 2. 一致项处理

| 情形 | 处理 |
|---|---|
| verdict 一致 且 页码有重合（或双方均为空页码） | 直接采纳；needs_review=false |
| verdict 一致 但 页码无任何重合 | 采纳 verdict；页码取并集；needs_review=true，理由 location_divergence |

页码并集策略：宁可多给复核人一页，不可漏掉一方看到的证据位置。

## 3. 分歧项保守默认表

| Pass A vs Pass B | provisional 终判 | conflict | 说明 |
|---|---|---|---|
| supported vs partially_supported | partially_supported | 否 | 向悲观方向降一级 |
| supported vs insufficient_evidence | partially_supported | 否 | 一方有证据一方无：折中取"部分支持"，禁止直接采信 supported |
| partially_supported vs insufficient_evidence | insufficient_evidence | 否 | 证据存疑时按"证据不足"处理 |
| contradicted vs 其他任何判定 | partially_supported | **是** | 冲突特例：不降为 contradicted（怕误伤），也不采信对方（怕漏报反驳）；双方原话并列，必须人工/仲裁复核 |

所有分歧项：needs_review=true，provisional=true，附仲裁理由字符串。

## 4. 仲裁环节的模型行为约束

允许：
- 针对 needs_review 项回查原文，补充证据页码与引句（更新 sources）；
- 在 change_records 中记录复核动作与依据。

禁止：
- 绕过 adjudicate.py 直接改写 final_verdict；
- 删除 conflict 标记；
- 以"仲裁"名义把低 kappa 从 uncertainty 中抹去。

若回查原文后确有压倒性依据推翻保守默认（例如发现某通道引句系页码错位所致），允许修正该条判定，但必须：(1) 保留原双方记录；(2) 在 change_records 写明推翻理由；(3) 该论断仍保留 needs_review=true。

## 5. 质量门槛与报告义务

| kappa | 解释 | result.json 义务 |
|---|---|---|
| ≥ 0.8 | 判定标准高度稳定 | uncertainty 报告数值即可 |
| 0.6 – 0.8 | 可接受 | uncertainty 报告数值 + needs_review 计数 |
| < 0.6 | 判定标准不稳定（agreement.py 打印警告） | status ≤ partial；uncertainty 必须写明"双通道一致性低，结论可信度受限"；全部仲裁项保留 needs_review |
| 无定义（完全一致且单类别） | 样本退化 | uncertainty 注明 kappa 无定义的原因 |

定位一致率（平均 Jaccard、至少一页精确重合比例）无论高低都必须进入 uncertainty。

## 6. 仲裁日志

adjudicate.py 生成 `adjudication-log.md`：质量指标头部 + 逐条明细表（双方判定、证据页、原文引句、理由并列）。日志是 result.json 的佐证工件，评测中应保留在 /app/work，复用场景下随清单一并归档。
