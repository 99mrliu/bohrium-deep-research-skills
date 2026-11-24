# bundle-a-corpus-coverage-gate

**语料真实性与覆盖审计门禁**（corpus coverage gate）— Playground challenge-073af7d3
「研究前沿与趋势分析：文献综述」投稿技能包。论点：语料不过关，一切趋势皆空。
在任何趋势/演化/代表作/空白判断之前，先把语料规范化、去重、年份溯源，
并用计数闭合法则（`records_total == kept + duplicates + excluded`）做机器可检的门禁。

## 目录结构

```
SKILL.md                      技能主文档（YAML frontmatter: name/description）
GITHUB_URL.txt                仓库链接
scripts/
  ingest_corpus.py            摄入引擎：json/jsonl/csv/bib/ris/txt/md → canon.jsonl + duplicates.json + ingest_report.json
  coverage_ledger.py          覆盖台账：coverage.json（逐年计数/右删失/排除日志/闭环块）
  gate_check.py               审计门禁：五项检查 → gate_verdict.json（fail 时 exit 1）
references/
  date_policy.md              print/online/preprint 日期策略与溯源规范
  coverage_contract.md        coverage.json 契约、闭环方程、排除原因分类
examples/
  run_example.sh              端到端自证（GOOD pass / BAD fail，断言退出码）
  synthetic_case/             合成数据（标注 synthetic；植入重复/缺年/右删失 + 篡改台账）
  example_output/             自证脚本真实产出的工件
```

## 运行示例

```bash
bash examples/run_example.sh
```

预期：GOOD 运行 `gate=pass`（exit 0，2 条植入重复被移除、缺年记录仅留痕）；
BAD 运行注入不闭环台账，`gate=fail`（exit 1，违规 `coverage_closure_mismatch`）。

## 性质

- 仅 Python 3 标准库，无网络，确定性输出（键排序、无时间戳）；
- 单文件损坏容错，计入 ingest_report.errors；
- 全部示例数据为合成数据。

## 许可

本包内容可自由使用、修改与再分发，无需授权（public domain / CC0 等价意图）。
