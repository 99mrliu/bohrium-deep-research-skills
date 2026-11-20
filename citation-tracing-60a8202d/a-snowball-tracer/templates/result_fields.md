# result.json 字段说明（交付契约）

| 字段 | 类型 | 含义 | 完成标准 |
|-|-|-|-|
| case_id | string | 原样取自 case.json | 与输入一致 |
| skill | string | `dir-aware-snowball-tracer` | 固定 |
| status | string | ok / partial / failed | 与实际完成情况一致；部分完成必须配 uncertainty 说明 |
| seed | object/null | 种子文献元数据＋locator | 找不到时为 null 且 seed_resolution_attempts 非空 |
| seed_resolution_attempts | array | 每次解析尝试（by/value/hit） | 覆盖 DOI、arXiv、标题、模糊标题四类 |
| parameters | object | 实际生效的追踪参数 | 与运行日志一致 |
| nodes | array | 全部访问节点：key/doi/arxiv/title/year/authors/venue/type/cited_by_hint/locator/stub/layer/direction/via | stub 节点不带推测字段 |
| edges | array | from/to/direction/layer/meaning/source{file,pointer} | 每条边可回指原始记录 |
| layers | array | 每层节点数、后向/前向计数 | 与 nodes 一致 |
| pruning_log | array | 被剪分支与理由 | 非空时逐条可解释 |
| stop_log | array | 停止判据 | 非空时逐条可解释 |
| stats | object | 边数、stub 数、语料规模 | 与 nodes/edges 一致 |
| sources | array | 全部解析过的数据文件（＋可选 live API 记录） | 复核人可定位每个文件 |
| evidence_records | array | 运行日志逐条 | 时间顺序 |
| uncertainty | array | 缺失、冲突、stub、解析异常 | 如实；无则空数组 |
| change_records | array | 运行中对结果的更正（默认为空） | 有更正才填 |
| output_contract_fields | array | case.json 中 output_contract 的字段名 | 全部镜像，未覆盖字段为 null |

镜像规则：`output_contract` 中出现的字段若在结果中没有对应内容，置 null 并在 uncertainty 中说明原因；不得删除字段。
