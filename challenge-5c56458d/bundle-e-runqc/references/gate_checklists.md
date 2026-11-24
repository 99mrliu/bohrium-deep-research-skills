# 门禁清单（gate checklists）

每一门通过才进入下一门；`gate.py` 逐步执行并留 checkpoint。预算紧张时
（900 s / 64 次请求）门序列保证"随时中断都有已交付的诚实部分结果"。

## G0 输入盘点（10% 预算内完成）

- [ ] 列出 /input 全部文件（路径、大小、角色）
- [ ] case.json 解析成功，case_id 与 output_contract 字段已提取
- [ ] **partial result.json 已写入 /app/output（契约兜底，最高优先）**
- [ ] 数据库文件以只读方式可打开

## G1 模式与口径

- [ ] 每表行数、每列类型与空值计数已记录（schema 卡片）
- [ ] 分析口径一句话成文（分组粒度、筛选、单位）
- [ ] 缺失/重复预审计完成，处置方式已声明

## G2 查询执行

- [ ] 每条 SQL 原文落盘，执行日志含行数与耗时
- [ ] 连接查询完成行数对账（无未声明的膨胀）
- [ ] 报错查询有"错误→原因→修复"记录

## G3 结果核验

- [ ] 报告中的每个数字能回指某次有日志的执行
- [ ] 关键聚合有独立复算或行数对账支撑
- [ ] 空结果/异常已定位原因并记录（不静默修复）

## G4 交付完成

- [ ] result.json 含 case_id 与 output_contract 全部字段
- [ ] status=complete；若为 partial，limitations 写明限制
- [ ] selfcheck.py 判定 GO
- [ ] analysis_notes.md 含异常清单与未覆盖部分
