# xlang-langid-view-router

跨语言文献检索的**语言识别与视图路由** Skill：用真实正文判定语种（置信度＋可复核证据），
把同工作的多语种记录聚成 work，分类 original / translation / bilingual / abstract_only /
duplicate，输出逐视图查询语言路由与去重计数规则。

- 入口说明：[SKILL.md](SKILL.md)
- 方法策略：[references/langid_policy.md](references/langid_policy.md)
- 可运行合成示例：[examples/example_walkthrough.md](examples/example_walkthrough.md)
  （`python3 scripts/langid_views.py --roots examples/data --out examples/out`）

运行环境：Python 3.8+，仅标准库；PDF 经平台 `pdftotext` 抽取。完全离线。
