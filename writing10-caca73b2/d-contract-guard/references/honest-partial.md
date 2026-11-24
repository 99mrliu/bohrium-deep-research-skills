# 诚实 Partial 写作规范

评测条款明确: 平台保留运行时产物, 即使最终 JSON 无效; 诚实的不完整结果优于虚假的完整结果 ("A partial result must identify its limits")。本规范定义如何写出合格的 partial / failed。

## status 判定决策树

```
材料目录为空或全部不可读?
├─ 是 → failed (零材料, 任何正文都是编造)
└─ 否 → 内容工作是否覆盖了 task.md 的全部要求, 且无缺图/缺统计量/单位不明等未决缺口?
        ├─ 是 → complete (要求 limits 中无未解决条目)
        └─ 否 → partial (必须在 limits/uncertainty 写明缺什么)
```

- complete 的附加条件: final_check 通过且 limits 无未解决条目。
- 中途被预算截断: 一律 partial, 并在 limits 写明"因预算于阶段 sX 冻结, sY/sZ 未执行"。
- 绝对禁止: 为拿 complete 而删除 limits 条目或补写未核实内容。

## limits / uncertainty 的写法

分工: **limits 记客观缺口** (缺材料、缺图、缺数据点、预算冻结), **uncertainty 记主观不确定** (机制推断、读数不清、解释有歧义)。

好例子 (具体、可定位、说明影响):

- `"缺失材料: fig1.png (case.json 字段 materials 引用, 但材料目录中不存在)。"`
- `"图 2 的误差棒数值在材料中未给出, 结果节仅转述定性趋势, 未引用任何读数。"`
- `"因预算于阶段 s3 后越过 90% 线, s4_polish 按降级阶梯跳过; 正文未经语言润色。"`
- (uncertainty) `"48 h 硬度下降归因为过时效属机制推断, 缺 48 h TEM 直接证据。"`

坏例子 (空泛、推卸、伪诚实):

- `"部分内容未完成。"` — 没说缺什么、为什么。
- `"时间不够。"` — 没有量化, 无法复核; 应写"剩余 X 请求 / Y 秒, 不足完成 sZ 计划配额"。
- `"材料可能有问题。"` — 应给出 material_check 的具体标记与 sha256/大小。
- 把编造内容写进正文再在 uncertainty 里说"可能不准" — 这是伪造, 不是诚实。

## 人工确认项格式

需要人介入的事项, 在 uncertainty 中用统一句式:

`"人工确认: <事项>; 现状: <已做的核查>; 建议: <下一步>。"`

例: `"人工确认: /input 是否打包完整; 现状: case.json 引用 fig1.png 而目录中不存在 (sha256 无从计算); 建议: 重传材料后重跑阶段 2。"`

## 平台"runtime artifacts retained"条款的利用

既然平台保留运行时产物, 中间产物写盘本身就是证据链:

1. 每阶段的草稿版本、material_inventory.json、budget_ledger.json 一律写入 /app/work 并保留到运行结束, 不清理。
2. final_check 的终端输出用 `| tee /app/output/final_check.txt` 留档。
3. result.json 的 stage_log 记录每阶段时间戳, 与台账中的用量互相印证; 评审可据此重建"何时因何冻结"。
4. 失败分支同样写"失败说明件"作为 deliverable 占位: 评审打开输出目录即可看到失败原因, 而不是一个空目录。
