# a-source-verifier

**上游来源真实性核验（upstream-source-verifier）**：在做出任何文献质量判断之前，
先核验材料本身。建立 provenance ledger：指纹登记每个输入文件 → 解析离线
Crossref/EuropePMC 快照 → 快照元数据 × 正文交叉核对 → 检测重复/改名/版本冲突/
元数据不一致 → 每个来源判定 `verified` / `mismatch` / `unverifiable`。
下游论断只允许绑定 verified 来源；mismatch 如实上报，绝不静默修复。

## Quickstart

```bash
B=/path/to/a-source-verifier
W=$(mktemp -d); O=$(mktemp -d)

python3 "$B/scripts/fingerprint.py"  --input-dir /input --workdir "$W" \
    --output-dir "$O" --case /input/case.json
python3 "$B/scripts/crosscheck.py"   --workdir "$W"
python3 "$B/scripts/build_result.py" --workdir "$W" --output-dir "$O" \
    --case /input/case.json
```

产出：`$O/result.json`（机器可读台账 + status + uncertainties）与
`$O/provenance_report.md`（人类可读表格）。

- 仅 Python 3 标准库；PDF 文本层可选依赖 `pdftotext`（缺失则该 PDF 判
  unverifiable）。
- 完全离线，绝不发起网络请求。
- 退出码：0 正常 / 1 校验失败 / 2 用法错误。

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 技能说明与运行时契约（中文） |
| `references/snapshot_fields.md` | Crossref/EuropePMC 快照字段与常见不一致模式 |
| `references/veracity_rules.md` | 归一化规则、匹配阈值、判定阶梯、弃权条件 |
| `scripts/fingerprint.py` | 指纹登记 + 骨架 result.json |
| `scripts/crosscheck.py` | 快照 × 正文交叉核对 |
| `scripts/build_result.py` | 汇总最终 result.json / provenance_report.md |
| `examples/` | 完全合成的可运行示例（含真实输出节选） |
