# lint 报告（field_lint.py L1–L8）

- records 文件: `records.json`（9 条）
- 往返对照: 未执行
- 结论: error 0 / warning 1 / info 1 → 退出码 0

| 规则 | 级别 | 记录 | 字段 | 说明 |
| --- | --- | --- | --- | --- |
| L7 | warning | cnki3-1 | title | 中文条目 `题名` 检出 CJK 紧邻半角标点: `GB/T 7714—2015 应用中的标点问题:兼论混排`，lint 不改写原文，请人工确认是否应全角化 |
| L4 | info | zhang2023survey | authors | 作者共 4 名，GB/T 7714 渲染将列前 3 名后加 等/et al.，导出格式保留全部作者 |
