# number-recompute-core

引用与事实核验的**数值与统计重算**中枢：全文数字账本 + 五类确定性重算检查（百分比、p 值措辞、组量合计、同名计数交叉、表格合计），硬矛盾退出码 1。详见 [SKILL.md](SKILL.md)。

## 布局

- `SKILL.md` — Skill 本体（运行契约、工作流程、异常处理、result.json schema）
- `scripts/ingest_text.py` — 材料解析
- `scripts/number_ledger.py` — 数字账本（计数/百分比/p 值/mean±SD/CI/表格行）
- `scripts/recompute.py` — N1–N5 重算矛盾引擎
- `references/` — 检查语义与容差、非机械统计审查清单
- `examples/` — **合成示例**（`bash examples/run_example.sh`）

## 快速自检

```bash
bash examples/run_example.sh
# 期望：recompute 退出码 1；contradictions.json 含
# N1: 52.5% vs 55/120=45.83%；N2: p=0.049 却写 highly significant；
# N2: p=0.083 却写 significant；N3: 组量 60+62=122 ≠ 声明总数 {118,120}；
# N4: participants 取值 {118,120} 交叉提示；N5: Total 行 999 ≠ 58+62=120
```

无第三方依赖：Python ≥3.8 标准库；PDF 用系统 `pdftotext`（可回退纯文本）。
