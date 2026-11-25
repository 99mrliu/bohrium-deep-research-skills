# 增量导入治理差异报告(delta report)

- case_id:`synthetic-import-gov-001`
- 状态方言:`a`;基线建立:`False`
- 在场来源库:crossref, europepmc;缺席来源库:publisher

## 1. 分类计数

| 类别 | 数量 |
| --- | ---: |
| 上一状态记录数 | 11 |
| 当前响应记录数 | 10 |
| 新增 `new` | 2 |
| 不变 `unchanged` | 7 |
| 变更 `changed` | 1 |
| 撤回(源在场而记录消失) `withdrawn` | 1 |
| 不可核验撤回(源亦缺席) `unverifiable_withdrawal` | 1 |
| 状态不一致 `inconsistent_state` | 1 |
| **标识符并集** | **13** |

分区校验:通过(六类之和 = 并集大小,互不重叠、无一遗漏)。

## 2. 新增记录(new)

| 标识符 | 来源库 | 证据 |
| --- | --- | --- |
| `10.99988/gov.0005` | crossref | `message.items[4]` |
| `10.99988/gov.0006` | crossref | `message.items[5]` |

## 3. 变更记录(changed,field 级 before→after)

### `10.99988/gov.0004`(来源库:crossref)

| 字段 | before(上一状态) | after(当前响应) |
| --- | --- | --- |
| year | 2020 | 2021 |
| venue | journal of bio-adhesion letters | journal of bionic interface mechanics |

## 4. 撤回与不可核验撤回

| 标识符 | 声称来源库 | 子类 | 说明 |
| --- | --- | --- | --- |
| `pmid:39000009` | europepmc | `source_present_but_record_gone` | 来源库 europepmc 的响应在场,但该记录已不在其中;作为'导入治理事实'登记为撤回。是否为撤稿/删除的语义判定不属于本技能,应移交专门的撤回分析流程 |
| `pub:JBA-1042` | publisher | `source_absent_too` | 其来源库 publisher 的响应本次缺席,无法区分'记录被撤回'与'源未提供',不可核验 |

> 边界声明:此处仅登记「记录已不在响应中」的**导入治理事实**;撤稿/删除的语义判定(retraction analysis)不属于本技能,应移交专门流程。

## 5. 状态不一致(inconsistent_state)

| 标识符 | 声称来源库 | 说明 |
| --- | --- | --- |
| `10.99988/gov.0090` | crossref | 状态行自相矛盾(identifier(10.99988/gov.0090) 与 fields.doi(10.99988/gov.0091) 冲突),且该标识符未出现于 crossref 响应;状态本身不可信,需人工裁定 |

## 6. 水印推进提案(requires_approval=true,未写回)

| 数据库 | 上一水印 | 提议水印 | 动作 | 保持原因/证据 |
| --- | --- | --- | --- | --- |
| crossref | `{"cursor":"AoJ9Z292LWN1cnNvci0wMDE=","offset":20}` | `{"cursor":"AoJ9Z292LWN1cnNvci0wMDI=","offset":26}` | advance | cursor←响应 next-cursor;offset←20+6 |
| europepmc | `{"cursorMark":"AoEPMzkwMDAwMDA="}` | `{"cursorMark":"AoEPMzkwMDAwMDc="}` | advance | cursorMark←响应 nextCursorMark |
| publisher | `{"last_seq":1042}` | `∅` | hold | response_absent:本次材料中无 publisher 响应 |

水印提案:2 个库推进(crossref,europepmc),1 个库保持(publisher)。本提案 requires_approval=true,未经组织者显式批准绝不写回。

## 7. 批准清单(approval checklist)

- [ ] 审阅第 3 节全部 changed 条目的 before→after 是否正确
- [ ] 审阅第 4 节撤回/不可核验撤回条目的处置决定
- [ ] 裁定第 5 节 inconsistent_state 条目
- [ ] 显式批准或拒绝第 6 节水印提案(批准前状态文件保持原值)
- [ ] 确认本报告的撤回条目已按需移交撤回语义分析流程

## 8. 已应用的处置决定(dispositions)

| 标识符 | 类别 | 处置 | 理由 |
| --- | --- | --- | --- |
| `10.99988/gov.0004` | changed | accept_change | 变更仅为出版方元数据更新:期刊更名(Bio-Adhesion Letters → Bionic Interface Mechanics)且年份 2020→2021,标题与作者完全一致,采纳当前响应的新值。 |
| `pmid:39000009` | withdrawn | exclude_withdrawn | EuropePMC 响应在场而该 PMID 已消失,作为导入治理事实从治理状态移除;是否构成撤稿的语义判定不属于本技能,应移交专门的撤回分析流程。 |
| `10.99988/gov.0090` | inconsistent_state | escalate | 状态行自相矛盾(identifier 为 gov.0090 而自带 fields.doi 为 gov.0091),且两者均不在当前 crossref 响应中;脚本无权猜测,升级由组织者人工裁定。 |
| `pub:JBA-1042` | unverifiable_withdrawal | keep_previous | publisher 响应本次缺席,无法区分记录被撤回与源未提供;保留原记录并标注待下轮核验。 |

