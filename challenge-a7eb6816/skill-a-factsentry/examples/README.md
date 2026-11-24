# examples/ — 最小合成示例

> **本目录为合成示例，非正式案例结果。** source.md 中「Co3O4/CeO2 催化剂研究」的全部
> 内容（数字、结论、引用）均为虚构，仅用于端到端演示与测试 ledger_extract.py →
> fact_check.py 的核验流程。

## 文件

| 文件 | 角色 |
| --- | --- |
| `source.md` | 虚构源文（含 10 个数字条目、3 个图表引用、3 个引用标记、5 个论断强度词） |
| `draft_bad.md` | 负向改写稿：故意引入数字漂移、图表/引用丢失、论断强度升格 |
| `draft_good.md` | 正向改写稿：保留全部数字与单位、图表编号、引用标记，论断强度同级 |
| `expected/` | 脚本**真实运行输出**（非手工编写） |

## 真实运行命令（在 bundle 根目录执行）

```bash
# 1) 源文 → 证据台账（退出码 0）
python3 scripts/ledger_extract.py examples/source.md -o examples/expected/evidence_ledger.json

# 2) 负向稿核验（退出码 3 = 发现 drift）
python3 scripts/fact_check.py --ledger examples/expected/evidence_ledger.json \
  --draft examples/draft_bad.md \
  --json-out examples/expected/fact_check_report_bad.json \
  --md-out examples/expected/fact_check_report_bad.md

# 3) 正向稿核验（退出码 0 = PASS）
python3 scripts/fact_check.py --ledger examples/expected/evidence_ledger.json \
  --draft examples/draft_good.md \
  --json-out examples/expected/fact_check_report_good.json \
  --md-out examples/expected/fact_check_report_good.md
```

## 真实结果摘要

**台账**（21 条）：number=10，figure_ref=3，citation=3，strength=5。

**draft_bad：FAIL，退出码 3**，共 13 条发现（12 条计入失败判定）：

- `unsupported_number` ×2（数字漂移）：180 °C → **160 °C**；99.2% → **99.8%**；
- `dropped_evidence` ×9：7 个数字（112 m2/g、180 °C、36000 mL、95.1%、99.2%、n=5、p<0.05）、
  1 个图表引用（**表1**，mandatory）、1 个引用标记（[2]，recommended，默认不阻断）；
- `strength_upgrade` ×2：初步表明(1) → **证实(3)**；相关(1.5) → **导致/因果断言(4)**（相关→因果）。

**draft_good：PASS，退出码 0**，0 条发现（改写稿 10 个数字全部命中台账，图表/引用齐全，论断强度同级）。

**确定性**：相同命令重复运行输出字节一致（无时间戳、无随机）。
