# 模板：检索式版本迭代留痕（query log）

每次修改检索式后复制一段填写，随 /app/work 保存（如 /app/work/query_log.md）。
停止判据见 rules/topic_query_construction.md 第 5 节。

---

## 版本 v<版本号>（<ISO 时间>）

- mode：topic | number_lookup
- 概念块数：<n>；分面：classification=<...> applicant=<...> year_range=<...>
- 人读布尔式：<(a OR b) AND (c OR d) ...>
- 本轮改动：<新增/删除/替换的词项及 intent 理由；分面调整；阈值调整>
- 执行结果：identified=<?> duplicates=<?> screened=<?> included=<?> excluded=<?>
- 零命中块：<块名 + 原因判断（语料无此写法/词太窄/语言问题），或"无">
- 误检观察：<哪些命中是偶然共现，下轮如何处理（加 NOT/提阈值/收窄分面）>
- 下一步：<继续迭代 / 达到停止判据（说明满足哪两条）>

---

## 填写示例（虚构，illustrative only）

## 版本 v1.0（2026-01-01T00:00:00Z）

- mode：topic
- 概念块数：3；分面：classification=["C12M 1/00"] year_range=["2015","2026"]
- 人读布尔式：(fermentation OR reactor) AND (membrane aeration OR aeration) AND (microbial OR cell culture) [分面] IPC/CPC=(C12M 1/00) AND 年份=2015-2026
- 本轮改动：首版，查全优先，每块含上位词兜底（aeration）。
- 执行结果：identified=5 duplicates=1 screened=2 included=1 excluded=1
- 零命中块：无。
- 误检观察：无偶然共现；1 篇论文因缺"应用对象"块被 E7 排除，符合预期。
- 下一步：命中集合稳定 + 无零命中块 + PRISMA 一致，达到停止判据。
