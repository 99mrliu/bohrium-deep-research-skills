# result.json 字段说明（交付契约）

| 字段 | 含义 | 完成标准 |
|-|-|-|
| case_id | 原样取自 case.json | 与输入一致 |
| skill | `cocitation-parallel-discovery` | 固定 |
| status | ok / partial / failed | 空结果且阈值正常时为 ok 并配 uncertainty 说明"真实空结果" |
| seed | 种子元数据＋locator | 找不到为 null，attempts 非空 |
| seed_resolution_attempts | DOI/arXiv/标题/模糊标题尝试 | 全部记录 |
| parameters | top、min_support | 与运行一致 |
| candidates | 排名列表：rank、doi/arxiv/title/year/authors/venue/cited_by/locator、score、score_parts、support、association_evidence（co_citation / bibliographic_coupling / shared_authors / shared_title_tokens / same_venue）、excluded_direct_relation | 每个候选 ≥1 条结构证据，证据含双定位 |
| direct_neighbors | 直接邻居计数与排除说明 | 非空 |
| stats | 语料规模、候选数 | 与 candidates 一致 |
| sources | 解析过的数据文件 | 可定位 |
| evidence_records | 运行日志 | 时间顺序 |
| uncertainty | 覆盖局限、缺失、空结果说明 | 如实 |
| change_records | 更正记录（默认空） | 有更正才填 |
| output_contract_fields | output_contract 镜像字段名 | 未覆盖字段为 null 且不得删除 |

镜像规则同方向 1 规范：contract 字段只增不删，无内容置 null 并在 uncertainty 说明。
