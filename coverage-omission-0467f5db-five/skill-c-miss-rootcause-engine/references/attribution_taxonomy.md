# 漏检归因分类体系与探针判定逻辑

## 分类体系（与引擎 PROBES 一一对应）

| 类别 | 定义 | 可操作修复 |
|---|---|---|
| query_term_missing | 查询式未覆盖该文献的同义/变体表达 | 新增含鉴别词的查询式 |
| field_too_narrow | 匹配词只存在于未检字段（摘要/主题词） | 扩展检索字段 |
| time_window_cutoff | 记录年份落在所有查询声明窗口之外 | 扩展时间窗 |
| source_not_covered | 记录所属来源未被任何已检来源覆盖 | 新增来源库 |
| identifier_missing | 记录无 DOI/PMID | 人工修复标识符 |
| identifier_conflict | 标识符解析到不同文献 | 核验并改正题录 |
| identifier_unresolvable | 本地响应无法解析该标识符 | 补充响应或人工核验 |
| unresolved | 五探针均无结论 | 人工复核 |

一条漏检允许多个类别并存（真实漏检常有复合原因）；每类只保留证据最强的一条。

## 证据三要素

每条归因证据必须同时具备：

1. **claim**：可证伪的陈述（如"鉴别词 X 不在任何查询式中"），禁止"覆盖不足"类措辞；
2. **定位**：`file` + `line N`（文本）或 `doi:/query_id:` 等 JSON 语义定位；
3. **excerpt**：原文摘录（≤200 字符），足以让复核者无需打开文件即可判断。

定位失败时显式写 "not found in local materials"；写不出三要素的归因降级为 unresolved。

## 探针决策树

```
miss 记录
├─ 无 DOI 且无 PMID ───────────────→ identifier_missing
├─ DOI 在本地响应解析到不同标题 ───→ identifier_conflict
├─ DOI 不在任何本地响应 ───────────→ identifier_unresolvable（与下列并存）
├─ 年份在全部查询窗口之外 ─────────→ time_window_cutoff
├─ 高鉴别标题词不在任何查询式 ─────→ query_term_missing
├─ 匹配词仅见于摘要且查询未检摘要 ─→ field_too_narrow
├─ 期刊未见于已检来源材料 ─────────→ source_not_covered
└─ 以上均无 ───────────────────────→ unresolved → 人工复核
```

## 反模式（禁止输出）

- "数据库覆盖不足"——必须指出哪个来源、哪条证据；
- "关键词选择不当"——必须指出缺哪个词、该词出现在哪份材料；
- "时间原因漏检"——必须给出年份与窗口边界的数值比较；
- 补检"已降低遗漏"但 omission_delta.measured=false。
