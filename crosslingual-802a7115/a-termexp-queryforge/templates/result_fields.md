# result.json 字段说明（交付契约）

| 字段 | 类型 | 含义 | 完成标准 |
|-|-|-|-|
| case_id | string | 原样取自 case.json | 与输入一致 |
| skill | string | `xlang-termexpansion-queryforge` | 固定 |
| status | string | ok / partial / failed | ok=全部声明语种有有效命中；partial=有语种零命中（已附显式说明）或查询被降级；failed=术语表为空或 case 不可读。必须与实际完成情况一致 |
| term_table_summary | object | concept_count / variant_count / languages_declared / roundtrip{checked,passed,downgraded} / to_translate_count | 与 /app/work/term_table.json 一致 |
| queries | object | 键=语种码；值={lang, query, template, completeness(full/partial), uncovered_concepts, variants_used(逐变体含 term/type/source/verified/confidence), generation_basis}；无法生成的语种值为 null | 每声明语种恰好一条；布尔结构为概念内 OR、概念间 AND |
| hits | array | 每条：{hit_id, title, attribution{doi,language,version,translation_of,relation,record_type,source,url,year}, attribution_note, recalled_by[{lang, completeness, matched_concepts[{concept_id, matched_variants[{term,type,source,verified}]}]}], locator{file,pointer}} | attribution 全部转写自记录原文，未声明字段缺失而非推测；每个召回语种可追溯到具体术语变体 |
| coverage | object | 键=语种码；值={lang, n_hits, status(ok/missing), explanation 或 caveat} | 每个声明语种都有条目；missing 必须带证据化说明（query-not-emittable / query-partial / no-record-matched 三类之一） |
| sources | array | 全部解析过的语料文件（{file}） | 复核人可定位每个文件 |
| evidence_records | array | 运行日志逐条 | 时间顺序 |
| uncertainty | array | to_translate 缺失、回译降级、零命中语种、unverified 变体参与查询、解析异常 | 如实；无则空数组 |
| change_records | array | 运行后对术语表/结果的人工更正记录（默认空） | 有更正才填，格式 {action, target, reason, at} |
| output_contract_fields | array | case.json 中 output_contract 的字段名 | 全部镜像；无对应内容的字段置 null 并在 uncertainty 说明 |

镜像规则：`output_contract` 中出现的字段若在结果中没有对应内容，置 null 并在 uncertainty 中说明原因；不得删除字段。

## 配套输出文件

| 文件 | 内容 |
|-|-|
| /app/work/term_table.json | 合并后术语表全量：逐变体 source/confidence/verified/verification/provenance；to_translate；candidate_concepts；roundtrip 统计；run_log |
| /app/output/query_log.json | 全部语种查询式（同 result.json.queries，独立文件便于复核） |
| /app/output/hit_alignment.md | 人读命中—术语对齐表：语种覆盖统计表＋逐条命中的定位、归因、逐概念命中变体 |
| /app/work/run_log.json, term_table_runlog.json | 两脚本运行日志 |
