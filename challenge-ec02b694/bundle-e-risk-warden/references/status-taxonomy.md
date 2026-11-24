# status-taxonomy.md — 诚实状态判据与状态转移规则

result.json 的 status 只允许四个取值。状态是**对交付物的诚实声明**，不是对努力程度的
评价。判据如下，互相互斥，按表自检后取唯一值。

## 一、四状态判据

| status | 判据（全部满足） |
|---|---|
| success | output_contract 全部字段填齐且无占位残留；每条推荐参数值均有证据引用或已获确认；final_audit verdict=pass；不存在未消解的 handoff/terminate 信号 |
| partial | 已产出部分内容（至少一个契约字段有实质内容），但存在以下任一：占位残留、证据缺口、未消解的降级、等待人工裁决、预算耗尽被迫收尾 |
| unable_to_determine | 无法给出任何可信结论：case.json 不可读、关键数据全缺、无可行解被 terminate、或流水线早期中断 |
| refused | 任务本身越权/违规/不安全（如要求绕过安全约束、伪造数据），Agent 明确拒绝执行 |

**诚实优先原则**：拿不准 success 还是 partial 时，一律 partial，并在
partial_reason 写清缺口。声称 success 后被 final_audit 检出违例，会被强制回退
partial 并留下 change_log 记录——这比一开始写 partial 更差。

## 二、状态转移规则

```
[启动] --warden_boot--> partial            （首份落盘；case 不可读则 unable_to_determine）
partial --主体工作顺利 + audit pass--> success
partial --triage=proceed_with_degradation--> partial（降级记录在 uncertainty；
                                              消解全部缺口且 audit pass 后才可升 success）
partial --triage=handoff_to_human--> partial（锁定，附待裁决清单；不得自行升 success）
partial --triage=terminate--> unable_to_determine（写明终止理由）
任意 --发现任务违规--> refused（写明拒绝理由，不再执行）
success --final_audit 检出违例--> partial（强制回退，change_log 留痕）
```

强制规则：
1. **首份 partial 不变量**：warden_boot 在任何实质计算之前写出首份 partial；
   之后所有改进都是增量改写同一文件。
2. **升级需审计**：partial → success 的唯一合法路径是 final_audit verdict=pass。
3. **降级无条件**：出现更严信号（handoff/terminate/违例）时立即降级，不需审计。
4. **refused 不可逆**：一旦 refused，不再产出任何参数建议。
5. **change_log 留痕**：每次状态转移追加一条 {ts, event, detail}。

## 三、partial_reason 写作规范

- 写缺口，不写过程："缺少历史实验数据，参数置信度未验证"，而不是"我尽力了"。
- 写定位：说明缺口属于数据 / 约束 / 设备 / 权限 / 预算哪一类，
  使复核者能区分"数据问题"与"模型问题"。
- 写下一步：human 需要做什么才能解除该 partial（补哪份材料、裁决哪个冲突）。

## 四、与 uncertainty 字段的分工

- status/partial_reason：对整个交付物的总结性声明（一个值）。
- uncertainty：逐条不确定项清单（数组），每项 {kind, detail, impact}；
  缺失材料、降级假设、指标矛盾各占一条，便于机器消费。
两者必须一致：uncertainty 非空且含未消解关键项时，status 不得为 success。
