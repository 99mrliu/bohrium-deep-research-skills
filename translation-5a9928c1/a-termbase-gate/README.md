# termbase-gated-translation

科技论文英译中技能：把术语库变成**可执行工件**——抽取候选术语、锁定唯一译法与禁用变体、逐段翻译、脚本机器审计，术语违规（term-drift / forbidden-variant）阻断交付。

## 文件地图 / File map

```
skill/
├── SKILL.md                      # 技能说明与运行时契约
├── README.md                     # 本文件
├── GITHUB_URL.txt                # 仓库地址 + 入口文件
├── scripts/
│   ├── extract_terms.py          # 抽取候选术语 → termbase_draft.json
│   ├── lock_termbase.py          # 合并译法并锁定 → termbase.locked.json
│   ├── audit_translation.py      # 审计 pairs.jsonl，违规 exit 1
│   └── make_result.py            # 幂等生成/就地改进 result.json
├── references/
│   ├── termbase_format.md        # 三个 JSON 工件的模式与生命周期
│   └── enforcement_rules.md      # 匹配规则、违规代码、示例
└── examples/
    ├── minimal_example.md        # 最小可复现示例（合成数据）
    └── data/                     # source_en.txt / pairs_good.jsonl / pairs_bad.jsonl
```

## 环境要求

- Python 3.8+（仅标准库，无第三方依赖）
- `pdftotext`（poppler）可选：仅当 `--src` 直接给 PDF 时需要；否则先自行抽成 .txt

## 快速上手 / Quickstart

```bash
cd examples
python3 ../scripts/extract_terms.py --src data/source_en.txt --out /tmp/termbase_draft.json
# 人工（agent）填写译法 → translations.json
python3 ../scripts/lock_termbase.py --draft /tmp/termbase_draft.json \
    --translations translations.json --out /tmp/termbase.locked.json
python3 ../scripts/audit_translation.py --termbase /tmp/termbase.locked.json \
    --pairs data/pairs_good.jsonl --out /tmp/audit.json --md /tmp/audit.md   # exit 0
python3 ../scripts/audit_translation.py --termbase /tmp/termbase.locked.json \
    --pairs data/pairs_bad.jsonl --out /tmp/audit_bad.json                  # exit 1, 2 violations
python3 ../scripts/make_result.py --case case.json --out /app/output/result.json --status partial
```

详见 `examples/minimal_example.md`。

## 维护说明 / Maintenance

- 术语库锁定后不得改译法；改 translations.json 后重新 lock（sha256 会变，属预期）并复审。
- 抽取器是启发式的：宁可多抽（用 `_drop` 弃掉），不要漏抽高频术语；输出确定性，可 diff 审计。
