# xlang-morph-match-engine

跨语言**表面形式匹配引擎**：NFKD 变音折叠、德语变元音转写与复合词包含匹配、轻量词形还原、
假名↔罗马字交叉通道、CJK 子串、混排标题多通道；每条命中归因到概念/语种变体/规则/偏移/上下文。

- 入口说明：[SKILL.md](SKILL.md)
- 匹配规则：[references/matching_rules.md](references/matching_rules.md)
- 可运行合成示例：[examples/example_walkthrough.md](examples/example_walkthrough.md)
  （`python3 scripts/xmatch.py --terms examples/data/terms.json --roots examples/data --out examples/out`）

运行环境：Python 3.8+，仅标准库；PDF 经平台 `pdftotext` 抽取。完全离线，不自造术语。
