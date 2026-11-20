# 缺口分类学（gap taxonomy）与缺失三级语义

## §0 缺失三级语义判定伪代码（map_fields.py 实现口径）

对每条记录 `r`、每个归一字段 `f`、来源 `s`：

```
function status(r, f, s):
    if f ∈ STATIC_NOT_PROVIDED[s]:           # 映射表静态清单（schema 层）
        return not_provided
    if path(r, f) 存在:                       # 源字段路径在本条记录中可寻址
        v = extract_and_clean(r, f)
        if v 为空或解析失败:
            warnings.append("[f] 解析告警")   # 告警留痕，不静默
            return unknown
        return present, value=v
    # 路径在本条记录中缺失：
    if f 曾出现在同一响应载荷的其他记录中:     # 载荷级观察集 observed
        return missing                        # 载荷有、本条无 → 记录级缺失
    return not_provided                       # 整个载荷都不含该字段 → 不提供
```

三态口径（与 SHARED_CONTRACT §2 对齐）：
- **missing**：来源具备该字段，但本条记录键缺失（载荷内其他记录有）；
- **unknown**：来源具备该字段，本条记录字段存在但为空 / 无法解析；
- **not_provided**：来源 schema 本身不提供（静态清单），或本响应载荷整体不含
  该字段（动态判定）。三者必须区分记录，不得混写；任一字段在**全部来源的
  全部记录**上均无 `present` 值时，升级定义为**系统性缺口字段**（见 §2）。

归一字段全集 FIELDS（17 个）：
`identifiers.doi / identifiers.pmid / identifiers.pmcid / title / authors /
container / year / volume / issue / pages / type / abstract / pub_date /
cited_by / references / license / status`。

聚类口径（最小必要）：`cluster_key = doi:<小写DOI>`（优先），无 DOI 时
`ty:<归一题名>::<年份>`（小写、去标点压缩空白），再退 `pmid:<PMID>`。
仅用于覆盖统计，不做模糊匹配。

## 缺口类别总表

| # | 类别 | 定义 | 判定依据 | 处置 | result.json 落点 |
|---|---|---|---|---|---|
| 1 | 单库独有文献 | 某论文仅在一个来源出现 | cluster_key 的 sources 集合大小 = 1 | 正常交付并单列，提示补检索或确认收录差异 | `single_source_unique` |
| 2 | 系统性字段缺口 | 某归一字段在所有来源全部记录上均无 present 值 | coverage_matrix：Σ present = 0 | 写入报告 §3；若为业务必需字段（如 license），记入 uncertainty | `systematic_gaps` |
| 3 | 库不可用 | 某来源材料含 HTTP 错误/超时/限流痕迹，快照不完整 | status_ledger 原始文本模式匹配 | 该库降级 partial，覆盖结论注明“下限”性质 | `status_ledger` + `status.reason` |
| 4 | 零结果 | 某来源本次查询零命中（total-results/hitCount = 0） | status_ledger 结构化判定 | 不推断文献不存在；写入 uncertainty | `status_ledger` + `uncertainty` |
| 5 | 限流/配额 | 材料含 rate limit / quota / 429 痕迹 | status_ledger 模式匹配 | 同类别 3，partial + 注明截断风险 | `status_ledger` |
| 6 | schema 漂移 | 记录字段结构与映射表不符（如 journalInfo.journal 嵌套缺失） | map_fields.py 逐记录 drift 日志 | 字段按伪代码降级判定；逐条写入 drift 日志与 uncertainty | `status_ledger`(schema_drift) + `uncertainty` |
| 7 | 撤回/更正 | 记录含 retracted / withdrawn / correction 标记 | pubTypeList / relation / status / 题名前缀匹配 | **单列入结果并置 status 标记**，人工确认是否纳入分析集，不得静默剔除 | `retracted_records` + `status_ledger`(withdrawn_retracted) |
| 8 | 无法解析文件 | 嗅探失败（unknown）、坏 JSON、装载失败 | parse_case 逐文件 notes + map_report skipped_files | 逐名列入台账；若其为唯一来源证据则该字段按缺口处理并人工确认 | `unparsed_files` + `status_ledger`(unparsed_file) |
| 9 | 记录级丢弃 | 记录无法提取标识信息或提取异常 | map_report dropped_records（逐条原因） | 不计入覆盖统计，但计入库间对账的丢弃数 | `status_ledger`(parse_drop) + 对账表 |
| 10 | 导入冲突 | 本地已导入记录与新材料标识符相同但字段值不一致 | import_reconcile.py 字段逐一比对（volume/issue/year/pages/container/title） | 单列为 conflicting_updates，**人工裁决**以何者为准，不自动覆盖 | `import_reconcile.conflicting_updates` |

## 处置词表（status_ledger.disposition）

- `partial`：相应库/文件降级为部分覆盖，result.json.status 注明原因；
- `uncertainty`：写入 result.json.uncertainty 供复核；
- `manual_review`：进入人工确认队列（撤回记录、导入冲突），不自动处置。
