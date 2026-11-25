---
name: miss-rootcause-engine
description: 漏检根因诊断引擎。用于"检索覆盖率与遗漏分析"类任务：把每条未命中文献当作一个待诊断案例，执行五条可复核探针（P1 查询词未覆盖同义表达 / P2 检索字段过窄 / P3 时间窗截断 / P4 来源库未收录 / P5 记录标识异常），每条归因都带 "文件+行号或JSON路径+原文摘录" 三要素证据，再由归因反向生成定向补检式；若材料中含补检轮结果则复算遗漏下降量与残余遗漏解释。当任务要求漏检归因落到具体查询式、字段、时间窗、来源时使用。边界：探针只基于案例本地材料取证，不做实时数据库覆盖声明；无证据时输出 unresolved 并升级人工复核，不编造归因。
---

# 漏检根因诊断引擎（miss-rootcause-engine）

## 重心与适用条件

重心是**归因的可证伪性**。"数据库覆盖不足""关键词不好"这类归因无法被检验，等于没有归因。本引擎的每条归因都是一次探针执行的结果：

| 探针 | 诊断的漏检类别 | 判定证据 |
|---|---|---|
| P1 vocabulary | query_term_missing | 标题高鉴别词（长度>5）不在任何查询式中；附该词在本地语料的出现位置 |
| P2 field | field_too_narrow | 查询声明字段不含摘要，而本地响应记录显示匹配词只出现在摘要；附响应文件与摘录 |
| P3 time_window | time_window_cutoff | 记录年份与每条查询声明窗口的数值比较；附查询式出处 |
| P4 source | source_not_covered | 记录所属期刊未出现于已检来源的材料中；附正/反两面的定位证据 |
| P5 identifier | identifier_missing / conflict / unresolvable | 无标识符；或 DOI 在本地响应中解析到不同文献；或本地响应完全不含该 DOI |

探针无结论时输出 `unresolved` 并升级人工复核——**不允许**为了"分全类型"而硬凑归因。探针自身异常记 `probe_error`，不静默吞掉。

## 运行环境

- 输入 `/input/case.json`、`/task.md`；材料递归扫描。工作 `/app/work`，交付 `/app/output`。
- Python 3 标准库，零依赖，不联网。预算 ≤64 请求 / ≤900 秒，一条命令跑完全程。

## 调用方式

```bash
python3 /skills/weekly-skill/scripts/rootcause_engine.py \
  --input /input --work /app/work --output /app/output
```

退出码 `0` 完成 / `2` partial / `3` 契约字段缺失。先 `ls /skills/weekly-skill/scripts/` 确认安装路径。

## 产物

| 产物 | 内容 |
|---|---|
| /app/output/result.json | case_id、output_contract 全字段、status、sources、uncertainty、change_log |
| /app/output/coverage_report.md | 逐条漏检的诊断书（类别、探针、证据三要素） |
| /app/work/miss_diagnosis.json | 机器可复算的诊断台账 |
| /app/work/supplement_queries.json | 由归因反向生成的定向补检式（目标文献、新查询式或新来源、预期收益） |
| /app/work/omission_delta.json | 补检轮结果存在时：miss_before/recovered/miss_after 与残余解释；否则诚实标注未测量 |

## 补检式的生成规则（防空转）

每条补检式必须满足：① 锚定具体 ref_id 与归因类别；② 与已有查询式有实质差异（新增鉴别词、扩展窗口、新增来源、标识符修复之一），禁止同义词替换式重跑；③ 写明预期收益。补检执行后把结果以 `*supplement*.json` 放入材料重跑本引擎，`omission_delta.json` 自动给出遗漏下降量；下降量为零时在报告中如实说明。

## 异常处理

- 材料缺参考集或检索结果：status=partial，change_log 记录，已有产物照交；
- 本地无 API 响应文件：P2/P4/P5 中依赖响应的探针降级为无结论，不影响其他探针；
- 证据定位失败：该条证据标注 "not found in local materials"，不虚构行号。

## 最小调用示例（合成示例）

`examples/input/` 为**合成**数据：8 条参考题录、2 条查询、1 份合成 Crossref 响应（含摘要字段）、1 份合成补检轮结果。运行：

```bash
python3 scripts/rootcause_engine.py --input examples/input --work examples/run/work --output examples/run/output
```

预期（合成示例，非正式案例结果）：漏检 3 条，分别诊断出 query_term_missing（附语料定位）、time_window_cutoff（附查询出处）、identifier_missing；omission_delta 测得补检后漏检 3→1。详见 examples/README.md。

## 自查方法

1. result.json 含 case_id 与契约全部字段；
2. miss_diagnosis.json 每条 findings 至少一条 evidence 带 file+locator+excerpt（unresolved/probe_error 除外）；
3. supplement_queries.json 每条 new_query 与既有查询式字符串不同；
4. omission_delta.measured=true 时 miss_after = miss_before − recovered。
