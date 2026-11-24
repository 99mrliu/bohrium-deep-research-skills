# source-truth-gate

引用与事实核验的**上游数据真实性**门禁协议：先做参考文献真实性/撤稿/版本核验，再做完整的六类审查。详见 [SKILL.md](SKILL.md)。

## 布局

- `SKILL.md` — Skill 本体（运行契约、四阶段流程、异常处理、result.json schema）
- `scripts/ingest_text.py` — 材料解析（pdftotext 优先，纯文本回退）
- `scripts/extract_refs.py` — 参考文献抽取、DOI 语法校验、正文引文标记索引
- `scripts/verify_sources.py` — 七态来源核验状态机（硬报警退出码 1；可选 `--online` 查 Crossref）
- `references/` — 来源可靠性规则与状态机精确定义
- `examples/` — **合成示例**（`bash examples/run_example.sh` 一键复跑）

## 快速自检

```bash
bash examples/run_example.sh
# 期望：gate 退出码 1；example_output/source_report.json 中
# ref 1、2 = verified；ref 3 = metadata_conflict（年份）；
# ref 4 = version_mismatch（预印本 vs 正式版）；
# ref 5 = suspected_fabricated；ref 6 = retraction_flagged
```

无第三方依赖：Python ≥3.8 标准库；PDF 解析用系统 `pdftotext`（无则回退纯文本）。
