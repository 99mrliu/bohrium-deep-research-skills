# claim-citation-aligner

引用与事实核验的**引用支持语义对齐**协议：子主张 × 引文对齐矩阵 + 四态判定 + 四维范围比对，机器校验矩阵完整性与摘录逐字性。详见 [SKILL.md](SKILL.md)。

## 布局

- `SKILL.md` — Skill 本体（运行契约、四阶段流程、异常处理、result.json schema）
- `scripts/ingest_pages.py` — 材料解析
- `scripts/citation_scan.py` — 正文引文标记 ↔ 参考文献条目机械对账（未解析标记/未引条目）
- `scripts/matrix_check.py` — 对齐矩阵机检（schema、词表、逐字性、完整性；违例退出码 1）
- `references/` — 四态判定规则（R1–R6 + over-claim 四维分类）与子主张分解协议
- `examples/` — **合成示例**（`bash examples/run_example.sh`）

## 快速自检

```bash
bash examples/run_example.sh
# 期望：scan 报 6 个含引文句、1 个未解析标记 [9]；
# 好矩阵 matrix_check 通过（exit 0）；
# 坏矩阵被拦下（exit 1，C2 词表 / C4 逐字 / C6 完整性 / C7 整句复制违例）
```

无第三方依赖：Python ≥3.8 标准库；PDF 用系统 `pdftotext`（可回退纯文本）。
