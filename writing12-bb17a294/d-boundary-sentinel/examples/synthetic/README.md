# 合成示例 / synthetic example

本目录是一个**完全虚构**的小型工作示例（synthetic worked example），所有
"研究内容"均为编造，仅用于演示 boundary-sentinel 的流程，不对应任何真实
研究、人物或数据。

## 文件

- `source.txt` — 虚构英文源文（12 句正文 + 2 条参考文献），刻意埋入：
  否定（did not include / not definitive / no / none）、两处以上 hedge
  （may / suggest / could / appears / might / Approximately）、一处强因果
  （demonstrated）对一处弱因果（is associated with）、`only`、`up to`、
  数字引用 `[12]`、作者-年份引用 `(Smith, 2020)`、`et al.` 归属
  （According to Lee et al. / Smith et al. (2021)），以及 2 条
  References 条目（一条编号制、一条作者-年份制）。
- `translation_zh.md` — 手写中文译文，完整保留上述全部标记
  （没有/并非/无/不能；可能/或/似乎/约；表明 vs 与……相关；仅；至多；
  [12] 原样；Smith 等 (2021)；(Smith, 2020)）。
- `boundary_ledger.jsonl` — 由 `extract_markers.py` 生成（随后加入
  `_label` 字段标注"合成示例"）。共 12 条带标记记录：negation 5、
  hedge 8、causal_strength 3（strong×2, weak×1）、quantifier 4、
  attribution 4、citation 3。
- `boundary_audit.json` — 由 `audit_boundary.py` 生成：0 errors、
  0 warnings、status=pass（exit 0）。
- `citation_report.json` — 由 `citation_check.py` 生成：3 个文内引用
  全部 preserved、2 条参考文献各出现一次且顺序一致、无编造条目
  （exit 0）。

## 复现

```bash
cd /path/to/d-boundary-sentinel
python3 scripts/extract_markers.py examples/synthetic/source.txt \
    -o examples/synthetic/boundary_ledger.jsonl
python3 scripts/audit_boundary.py examples/synthetic/boundary_ledger.jsonl \
    examples/synthetic/translation_zh.md -o examples/synthetic/boundary_audit.json
python3 scripts/citation_check.py examples/synthetic/source.txt \
    examples/synthetic/translation_zh.md -o examples/synthetic/citation_report.json
```

（重跑会重新生成不含 `_label` 的原始输出；目录内文件为已标注版本。）

## 负例验证（在临时目录进行，不属于本 bundle）

- 译文删去否定（"没有设置对照组"→"设置了对照组"）→
  `negation_at_risk` error，exit 1。
- 译文删去 `[12]` → `citation_lost` error（audit，exit 1）+
  `intext_citation_lost` error（citation_check，exit 1）。
