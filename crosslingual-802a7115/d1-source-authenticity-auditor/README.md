# xlang-source-authenticity-auditor

跨语言文献检索的**上游数据真实性核验** Skill：语料发现（含 PDF 经 pdftotext 真实抽文）、
声明语种 vs 正文语种核对、内容指纹与近重复检测、缺失归因显式化，输出溯源台账与人读审计报告。

- 入口说明：[SKILL.md](SKILL.md)
- 方法策略：[references/authenticity_policy.md](references/authenticity_policy.md)
- 可运行合成示例：[examples/example_walkthrough.md](examples/example_walkthrough.md)
  （`python3 scripts/corpus_audit.py --roots examples/data --out examples/out`）

运行环境：Python 3.8+，仅标准库；PDF 抽取使用平台预装 `pdftotext`（缺失时降级并记录）。
全部脚本离线运行，不访问网络，不生成或修改任何文献数据。
