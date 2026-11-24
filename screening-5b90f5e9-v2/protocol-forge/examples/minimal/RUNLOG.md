# 最小示例运行记录（合成示例）

> 本示例的研究问题、标准表与全部输出均为**合成数据**，不对应真实检索任务。

## 输入

- `research_question.json`：合成问题（GLP-1 受体激动剂 vs 安慰剂/标准治疗对
  2 型糖尿病成人 MACE 的影响），3 个概念块（P/I/O）、3 个数据库方言、
  日期 2015-01-01..2026-12-31、语种 en、search_date 2026-11-24；
- `criteria.json`：4 条纳入、2 条排除；I4/E1/E2 故意不挂概念块以演示 M2 WARN。

## 实际执行与结果（2026-11-24，Python 3，macOS arm64）

```text
PROTOCOL 3 queries -> output/search_protocol.json
LINT PASS (3 queries) -> output/lint_report.json
LINT FAIL (1 queries) -> output/negative/lint_report.json   # 负向演示，预期失败
negative-demo: bad query rejected as expected: True
MAP WARN (6 criteria, 3 issues) -> output
EXAMPLE PASS (lint=True negative=True map=True)
```

退出码 0。`search_protocol.json` 两次重跑逐字节一致（已用 cmp 验证）。

## 产物目检结论

- `search_protocol.json`：pubmed 检索式为块内 OR、块间 AND、尾部
  `("2015/01/01"[Date - Publication] : "2026/12/31"[Date - Publication])`；
  scopus 用 `TITLE-ABS-KEY(...)` + `PUBYEAR`；wos 用 `TS=(...)` + `DOP`；
  每条带 block_trace（P/I/O 子句原文）。
- `lint_report.json`：三条生成检索式全 PASS。
- `negative/lint_report.json`：坏查询
  `("metformin"[tiab] AND ("prediabetes"[tiab] OR ) AND NOT [xx]`
  命中 L1（括号深度 1）、L5（`[xx]` 非白名单）、L9（`OR )`），exit 3。
- `criteria_map.json/md`：总体 WARN；M2×3（I4 随机对照试验、E1 动物实验、
  E2 非英文——这些标准本就靠筛选阶段兜底，WARN 为预期提示）；无 M1/M4 ERROR。

## 负向验证

除上述坏查询演示外，本地另验证：把 criteria.json 中某条 blocks 改成不存在的
块标识，map_criteria.py 报 M1 ERROR 并 exit 3（临时副本上完成，未改动随包文件）。
