# translation-fidelity-audit

对 EN→ZH 科技文献译文做忠实度机器核验与人工接管：数字、单位、引文、图表/公式引用、否定、模糊/转折语气等不变量在翻译中不得丢失或被篡改；阻断项清零前不得交付，未决项全部进入显式人工确认队列。

## 文件结构
- `SKILL.md` — 技能说明与运行时契约（Runtime contract / Workflow / 异常处理 / 自检清单）
- `scripts/extract_invariants.py` — 仅从 source 侧挖掘不变量 → `invariants.json`
- `scripts/check_fidelity.py` — 源不变量 vs 译文逐段比对 → `fidelity_report.json`(+`.md`)，有 blocker 时退出码 1
- `scripts/review_queue.py` — 报告 → `human_review_queue.md` 人工确认清单
- `scripts/finalize_result.py` — 生成/就地更新 `result.json`（保底、不覆盖非空字段、记录 change_record）
- `references/invariant_taxonomy.md` — 五类不变量的正则/词典/归一化规则与已知误报来源
- `references/severity_and_queue.md` — blocker vs warning 判据、人工队列关闭契约
- `examples/minimal_example.md` + `examples/data/` — 合成示例（pairs_bad / pairs_fixed）与复现命令

## 环境要求
- Python 3.8+，仅标准库（json / re / argparse / unicodedata 等），无第三方依赖。
- 所有文件 UTF-8 纯文本。

## 快速上手
```bash
cd skill
python3 scripts/extract_invariants.py --pairs examples/data/pairs_bad.jsonl --out invariants.json
python3 scripts/check_fidelity.py --invariants invariants.json --pairs examples/data/pairs_bad.jsonl \
    --out fidelity_report.json --md fidelity_report.md   # 预期退出码 1（4 个 blocker）
python3 scripts/review_queue.py --report fidelity_report.json --out human_review_queue.md
python3 scripts/finalize_result.py --case case.json --out result.json --status partial \
    --field fidelity_report=fidelity_report.json
```
详见 `examples/minimal_example.md`。

## 维护说明
- 单位词典与语气提示词集中在 `extract_invariants.py` 顶部常量中，扩展时同步更新 `references/invariant_taxonomy.md`。
- 新增检查代码时同时更新 `references/severity_and_queue.md` 的判据表与示例数据的预期结果。
- 任何逻辑变更后用 `examples/minimal_example.md` 中的命令回归验证（bad→exit 1 且恰为 4 个 blocker；fixed→exit 0）。
